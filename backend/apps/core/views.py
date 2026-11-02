from copy import deepcopy
from django.db import transaction
from django.db.models import Count
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Asset, Experiment, Result, Review
from .serializers import AssetSerializer, ExperimentSerializer, ResultSerializer, ReviewSerializer
from .services import split_documents, ask, PROMPT
from .tasks import run_experiment

@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok", "service": "知衡RAG评测平台"})

class AssetViewSet(viewsets.ModelViewSet):
    queryset = Asset.objects.all().order_by("-id")
    serializer_class = AssetSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.method in ("PUT", "PATCH", "POST") and transaction.get_connection().in_atomic_block:
            qs = qs.select_for_update()
        return qs.filter(kind=self.request.query_params["kind"]) if "kind" in self.request.query_params else qs
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def upload(self, request, pk=None):
        asset = self.get_object()
        file = request.FILES.get("file")
        if asset.kind != "knowledge" or asset.published or not file or file.size > 2*1024*1024:
            return Response({"detail": "仅草稿知识库可上传不超过2MB的文件"}, status=400)
        try:
            content = asset.content + [{"name": file.name, "text": file.read().decode("utf-8-sig")}]
        except UnicodeDecodeError:
            return Response({"detail": "文件必须使用UTF-8编码"}, status=400)
        serializer = self.get_serializer(asset, data={"content": content}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        with transaction.atomic():
            asset = Asset.objects.select_for_update().get(pk=self.get_object().pk)
            if asset.published or not asset.content:
                return Response({"detail": "版本已发布或内容为空"}, status=400)
            if asset.kind == "dataset" and any(not s.get("approved") or (not s["should_refuse"] and not s.get("evidence")) for s in asset.content):
                return Response({"detail": "所有样本须人工审核，非拒答样本须提供证据"}, status=400)
            if asset.kind == "knowledge":
                try:
                    chunks = split_documents(asset.content, int(asset.settings.get("chunk_size", 500)), int(asset.settings.get("overlap", 80)))
                except (ValueError, TypeError):
                    return Response({"detail": "分段参数无效"}, status=400)
                asset.settings = dict(asset.settings, chunks=chunks)
            asset.published = True
            asset.save()
        return Response(self.get_serializer(asset).data)
    @action(detail=True, methods=["post"])
    def chat(self, request, pk=None):
        asset = self.get_object()
        question = request.data.get("question")
        if not asset.published or asset.kind != "knowledge" or not isinstance(question, str) or not question.strip():
            return Response({"detail": "请选择已发布知识库并输入问题"}, status=400)
        config = {"backend": request.data.get("backend", "mock"), "top_k": request.data.get("top_k", 3), "model": request.data.get("model", "qwen-plus"), "prompt": PROMPT}
        if config["backend"] not in ("mock", "live") or type(config["top_k"]) is not int or not 1 <= config["top_k"] <= 20:
            return Response({"detail": "问答配置无效"}, status=400)
        try:
            return Response(ask(question, asset.settings["chunks"], config))
        except Exception as exc:
            return Response({"detail": "问答执行失败", "error_type": type(exc).__name__}, status=502)

class ExperimentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Experiment.objects.all().order_by("-id")
    serializer_class = ExperimentSerializer
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            experiment = serializer.save(created_by=request.user)
            experiment.snapshot = deepcopy({"knowledge": experiment.knowledge.content, "dataset": experiment.dataset.content, "chunks": experiment.knowledge.settings["chunks"]})
            experiment.save()
            Result.objects.bulk_create([Result(experiment=experiment, sample_id=s["id"], sample=s) for s in experiment.snapshot["dataset"]])
        try:
            run_experiment.delay(experiment.id)
        except Exception:
            experiment.status = "dispatch_failed"
            experiment.save(update_fields=["status"])
            return Response({"id": experiment.id, "detail": "任务入队失败，请检查Redis和Worker后重新创建实验"}, status=503)
        experiment.refresh_from_db()
        return Response(self.get_serializer(experiment).data, status=201)
    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        queryset = self.get_object().results.order_by("id")
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(ResultSerializer(page, many=True).data)
    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        items = list(self.get_object().results.prefetch_related("reviews"))
        outcomes = []
        for item in items:
            latest = sorted(item.reviews.all(), key=lambda r:r.id)
            outcomes.append(latest[-1].passed if latest else item.scores.get("passed"))
        return Response({"total": len(items), "completed": sum(i.status in ("succeeded", "execution_failed") for i in items), "execution_failed": sum(i.status == "execution_failed" for i in items), "quality_passed": outcomes.count(True), "quality_failed": outcomes.count(False), "pending_review": sum(i.status == "succeeded" and o is None for i,o in zip(items,outcomes)), "mode": self.get_object().config.get("backend")})

class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all().order_by("-id")
    serializer_class = ReviewSerializer
    http_method_names = ["get", "post", "head", "options"]
    def perform_create(self, serializer):
        serializer.save(reviewer=self.request.user)
