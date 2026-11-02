import csv
import io
import json
import uuid
from copy import deepcopy
from django.db import transaction
from django.http import HttpResponse
from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Asset, Experiment, Result, Review, SampleApproval, IndexJob, RegressionMembership, ChatRecord
from .serializers import AssetSerializer, ExperimentSerializer, ResultSerializer, ReviewSerializer, RagConfigSerializer, freeze_config, ApprovalSerializer, IndexJobSerializer, RegressionSerializer, ChatSerializer
from .services import split_documents, ask, connection
from .tasks import run_experiment, run_index
from .fingerprints import knowledge_fingerprint, sample_fingerprint
from .reports import report as build_report, compare as compare_experiments, outcome

@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status":"ok","service":"知衡RAG评测平台"})

@api_view(["GET"])
def capabilities(request):
    return Response({"providers":["qwen","deepseek"],"prompt_versions":["v1","v2"],"models":{"qwen":list(dict.fromkeys([connection()["model"],"qwen-plus","qwen-turbo","qwen-max"])),"deepseek":list(dict.fromkeys([connection(provider="deepseek")["model"],"deepseek-chat","deepseek-reasoner"]))},"judge_model":connection("judge")["model"]})

class AssetViewSet(viewsets.ModelViewSet):
    queryset=Asset.objects.all().order_by("-id")
    serializer_class=AssetSerializer
    http_method_names=["get","post","put","patch","head","options"]
    def get_queryset(self):
        qs=super().get_queryset()
        if self.request.method in ("PUT","PATCH","POST") and transaction.get_connection().in_atomic_block:
            qs=qs.select_for_update()
        return qs.filter(kind=self.request.query_params["kind"]) if "kind" in self.request.query_params else qs
    @transaction.atomic
    def update(self,request,*args,**kwargs):
        return super().update(request,*args,**kwargs)
    @action(detail=True,methods=["post"])
    @transaction.atomic
    def upload(self,request,pk=None):
        asset=self.get_object();file=request.FILES.get("file")
        if asset.kind!="knowledge" or asset.published or not file or file.size>2*1024*1024:
            raise serializers.ValidationError("仅草稿知识库可上传不超过2MB的文件")
        try: content=asset.content+[{"name":file.name,"text":file.read().decode("utf-8-sig")}]
        except UnicodeDecodeError: raise serializers.ValidationError("文件必须使用UTF-8编码")
        serializer=self.get_serializer(asset,data={"content":content},partial=True)
        serializer.is_valid(raise_exception=True);serializer.save()
        return Response(serializer.data)
    @action(detail=True,methods=["post"])
    @transaction.atomic
    def clone(self,request,pk=None):
        asset=self.get_object()
        data={"kind":asset.kind,"name":request.data.get("name",asset.name),"product":asset.product,"version":request.data.get("version",""),"content":deepcopy(asset.content),"settings":{k:v for k,v in asset.settings.items() if k not in ("chunks","index")}}
        s=self.get_serializer(data=data);s.is_valid(raise_exception=True);s.save()
        return Response(s.data,status=201)
    @action(detail=True,methods=["get"])
    def preview(self,request,pk=None):
        a=self.get_object()
        if a.kind!="knowledge":raise serializers.ValidationError("仅知识库支持切分预览")
        try: chunks=split_documents(a.content,int(a.settings.get("chunk_size",500)),int(a.settings.get("overlap",80)))
        except (ValueError,TypeError):raise serializers.ValidationError("分段参数无效")
        return Response({"chunks":chunks,"documents":a.content})
    @action(detail=True,methods=["get","post"])
    def index(self,request,pk=None):
        asset=self.get_object()
        if request.method=="GET":return Response(IndexJobSerializer(asset.index_jobs.order_by("-id"),many=True).data)
        if asset.kind!="knowledge" or asset.published or not asset.content:raise serializers.ValidationError("请选择有内容的草稿知识库")
        backend=request.data.get("backend","mock")
        if backend not in ("mock","live"):raise serializers.ValidationError("无效索引模式")
        try: chunks=split_documents(asset.content,int(asset.settings.get("chunk_size",500)),int(asset.settings.get("overlap",80)))
        except (ValueError,TypeError):raise serializers.ValidationError("分段参数无效")
        job=IndexJob.objects.create(asset=asset,backend=backend,fingerprint=knowledge_fingerprint(asset),collection="kb_"+uuid.uuid4().hex,snapshot={"chunks":chunks,"embedding":connection("embedding")})
        try:run_index.delay(job.id)
        except Exception:
            return Response({"id":job.id,"detail":"索引任务已保存，等待恢复调度器重新投递"},status=503)
        job.refresh_from_db()
        return Response(IndexJobSerializer(job).data,status=201)
    @action(detail=True,methods=["get","post"])
    @transaction.atomic
    def approve(self,request,pk=None):
        asset=self.get_object()
        if request.method=="GET":return Response(ApprovalSerializer(asset.approvals.order_by("-id"),many=True).data)
        if asset.kind!="dataset" or asset.published:raise serializers.ValidationError("只能审核草稿数据集")
        s=ApprovalSerializer(data=request.data);s.is_valid(raise_exception=True)
        sample=next((x for x in asset.content if x["id"]==s.validated_data["sample_id"]),None)
        if not sample:raise serializers.ValidationError("样本不存在")
        if not s.validated_data["reason"].strip():raise serializers.ValidationError("必须填写审核理由")
        s.save(asset=asset,content_hash=sample_fingerprint(sample),reviewer=request.user)
        sample["approved"]=s.validated_data["approved"];asset.save(update_fields=["content"])
        return Response(s.data,status=201)
    @action(detail=True,methods=["post"])
    @transaction.atomic
    def publish(self,request,pk=None):
        asset=self.get_object()
        if asset.published or not asset.content:raise serializers.ValidationError("版本已发布或内容为空")
        if asset.kind=="dataset":
            for sample in asset.content:
                approval=asset.approvals.filter(sample_id=sample["id"],content_hash=sample_fingerprint(sample)).order_by("-id").first()
                if not approval or not approval.approved:raise serializers.ValidationError("所有样本须通过当前内容的人工审核")
                if not sample["should_refuse"] and not sample.get("evidence"):raise serializers.ValidationError("非拒答样本须提供参考证据")
        else:
            backend=request.data.get("backend","mock")
            if backend not in ("mock","live"):raise serializers.ValidationError("无效索引模式")
            job=asset.index_jobs.filter(status="succeeded",fingerprint=knowledge_fingerprint(asset),backend=backend).order_by("-id").first()
            if not job and backend=="mock":
                try:chunks=split_documents(asset.content,int(asset.settings.get("chunk_size",500)),int(asset.settings.get("overlap",80)))
                except (ValueError,TypeError):raise serializers.ValidationError("分段参数无效")
                job=IndexJob.objects.create(asset=asset,backend="mock",status="succeeded",fingerprint=knowledge_fingerprint(asset),snapshot={"chunks":chunks,"embedding":{}})
            if not job:raise serializers.ValidationError("请先完成与当前文档和切分配置一致的向量索引任务")
            asset.settings=dict(asset.settings,chunks=job.snapshot["chunks"],index={"backend":backend,"collection":job.collection,"embedding":job.snapshot["embedding"],"job_id":job.id})
        asset.published=True;asset.save()
        return Response(self.get_serializer(asset).data)
    @action(detail=True,methods=["get","post"])
    def chat(self,request,pk=None):
        asset=self.get_object()
        if request.method=="GET":return Response(ChatSerializer(ChatRecord.objects.filter(knowledge=asset).order_by("-id")[:50],many=True).data)
        question=request.data.get("question")
        if not asset.published or asset.kind!="knowledge" or not isinstance(question,str) or not question.strip():raise serializers.ValidationError("请选择已发布知识库并输入问题")
        s=RagConfigSerializer(data=request.data);s.is_valid(raise_exception=True)
        config=freeze_config(s.validated_data,asset)
        record=ChatRecord.objects.create(knowledge=asset,question=question,config=config,created_by=request.user)
        try:record.trace=ask(question,asset.settings["chunks"],config)
        except Exception as exc:
            record.error=type(exc).__name__;record.save()
            return Response({"id":record.id,"detail":"问答执行失败","error_type":record.error},status=502)
        record.save()
        return Response(dict(record.trace,chat_id=record.id))

class ExperimentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset=Experiment.objects.select_related("knowledge","dataset").all().order_by("-id")
    serializer_class=ExperimentSerializer
    def create(self,request):
        serializer=self.get_serializer(data=request.data);serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            e=serializer.save(created_by=request.user)
            e.snapshot=deepcopy({"knowledge":e.knowledge.content,"dataset":e.dataset.content,"chunks":e.knowledge.settings["chunks"]})
            e.save()
            Result.objects.bulk_create([Result(experiment=e,sample_id=s["id"],sample=s) for s in e.snapshot["dataset"]])
        try:run_experiment.delay(e.id)
        except Exception:
            Experiment.objects.filter(pk=e.id,status="pending").update(status="dispatch_failed")
            return Response({"id":e.id,"detail":"任务已保存，等待恢复调度器重新投递"},status=503)
        e.refresh_from_db()
        return Response(self.get_serializer(e).data,status=201)
    @action(detail=True,methods=["get"])
    def results(self,request,pk=None):
        queryset=self.get_object().results.prefetch_related("reviews","attempts").order_by("id")
        if request.query_params.get("status"):queryset=queryset.filter(status=request.query_params["status"])
        page=self.paginate_queryset(queryset)
        return self.get_paginated_response(ResultSerializer(page,many=True).data)
    @action(detail=True,methods=["get"])
    def report(self,request,pk=None):return Response(build_report(self.get_object()))
    @action(detail=True,methods=["get"])
    def compare(self,request,pk=None):
        other_id=serializers.IntegerField(min_value=1).run_validation(request.query_params.get("other"))
        other=get_object_or_404(self.get_queryset(),pk=other_id)
        try:data=compare_experiments(self.get_object(),other)
        except ValueError as exc:raise serializers.ValidationError(str(exc))
        return Response(data)
    @action(detail=True,methods=["get"])
    def export(self,request,pk=None):
        e=self.get_object()
        data=ResultSerializer(e.results.prefetch_related("reviews","attempts").order_by("id"),many=True).data
        fmt=request.query_params.get("format","json")
        if fmt not in ("json","csv"):raise serializers.ValidationError("仅支持json或csv")
        if fmt=="json":content=json.dumps({"report":build_report(e),"results":data},ensure_ascii=False,indent=2,cls=DjangoJSONEncoder);ctype="application/json; charset=utf-8"
        else:
            buffer=io.StringIO();writer=csv.writer(buffer);writer.writerow(["样本标识","问题","执行状态","质量判定","回答","评分","异常"])
            def safe(v):
                text=str(v)
                return "'"+text if text.lstrip().startswith(("=","+","-","@","\\t","\\r")) else text
            for row,item in zip(data,e.results.prefetch_related("reviews").order_by("id")):
                writer.writerow([safe(v) for v in [row["sample_id"],row["sample"]["question"],row["status"],outcome(item),row["trace"].get("answer",""),json.dumps(row["scores"],ensure_ascii=False),row["error"]]])
            content="\ufeff"+buffer.getvalue();ctype="text/csv; charset=utf-8"
        response=HttpResponse(content,content_type=ctype)
        response["Content-Disposition"]=f'attachment; filename="experiment-{e.id}.{fmt}"'
        return response
    @action(detail=True,methods=["post"])
    def retry(self,request,pk=None):
        e=self.get_object();phase=request.data.get("phase","execution")
        if phase not in ("execution","scoring"):raise serializers.ValidationError("无效重试阶段")
        ids=request.data.get("result_ids")
        if ids is not None and (not isinstance(ids,list) or any(type(i) is not int for i in ids)):raise serializers.ValidationError("结果标识必须是整数数组")
        with transaction.atomic():
            e=Experiment.objects.select_for_update().get(pk=e.id)
            qs=e.results.filter(status="execution_failed") if phase=="execution" else e.results.filter(status="succeeded",scoring_status="failed")
            if ids is not None:qs=qs.filter(id__in=ids)
            changed=qs.update(status="pending",error="",scoring_error="",lease_token="",lease_until=None)
            if not changed:raise serializers.ValidationError("没有可重试的失败样本")
            e.status="pending";e.save(update_fields=["status"])
        try:run_experiment.delay(e.id)
        except Exception:return Response({"detail":"已重置任务，等待恢复调度器投递","count":changed},status=503)
        return Response({"count":changed})

class ReviewViewSet(viewsets.ModelViewSet):
    queryset=Review.objects.all().order_by("-id")
    serializer_class=ReviewSerializer
    http_method_names=["get","post","head","options"]
    def perform_create(self,serializer):serializer.save(reviewer=self.request.user)

class RegressionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset=RegressionMembership.objects.all().order_by("-id")
    serializer_class=RegressionSerializer
    @transaction.atomic
    def create(self,request):
        s=self.get_serializer(data=request.data);s.is_valid(raise_exception=True)
        dataset=Asset.objects.select_for_update().get(pk=s.validated_data["dataset"].id)
        result=s.validated_data["source_result"]
        if dataset.kind!="dataset" or dataset.published:raise serializers.ValidationError("回归集必须是草稿数据集")
        if dataset.product!=result.experiment.dataset.product:raise serializers.ValidationError("产品不一致")
        reviews=list(result.reviews.order_by("-id"))
        if result.status!="execution_failed" and (not reviews or reviews[0].passed or reviews[0].attribution in ("", "待人工确认")):raise serializers.ValidationError("请先人工复核失败并确认归因")
        if not s.validated_data["reason"].strip() or not s.validated_data["expected_fix"].strip():raise serializers.ValidationError("必须填写原因与修复条件")
        sample=deepcopy(result.sample);sample["approved"]=False
        existing=next((x for x in dataset.content if x["id"]==sample["id"]),None)
        if existing and sample_fingerprint(existing)!=sample_fingerprint(sample):raise serializers.ValidationError("回归集中已有相同标识但不同内容的样本")
        if not existing:
            dataset.content.append(sample);dataset.save(update_fields=["content"])
        if RegressionMembership.objects.filter(dataset=dataset,source_result=result).exists():raise serializers.ValidationError("该失败样本已加入此回归集")
        s.save(sample_id=sample["id"],created_by=request.user)
        return Response(s.data,status=201)
