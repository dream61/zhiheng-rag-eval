from rest_framework import serializers
from .models import Asset, Experiment, Result, Review, SampleApproval, ExecutionAttempt, IndexJob, RegressionMembership, ChatRecord
from .services import PROMPT, PROMPTS, connection
from .fingerprints import sample_fingerprint
from django.conf import settings
import os

class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = "__all__"
        read_only_fields = ["published", "created_at"]
    def validate(self, attrs):
        if self.instance and self.instance.published:
            raise serializers.ValidationError("已发布版本不可修改，请创建新版本")
        content = attrs.get("content", self.instance.content if self.instance else [])
        kind = attrs.get("kind", self.instance.kind if self.instance else None)
        if "settings" in attrs and not isinstance(attrs["settings"], dict):
            raise serializers.ValidationError("配置必须是对象")
        if not isinstance(content, list) or len(content) > 1000:
            raise serializers.ValidationError("内容必须是数组")
        if kind == "knowledge" and sum(len(str(x.get("text","" )).encode()) for x in content if isinstance(x,dict)) > 2*1024*1024:
            raise serializers.ValidationError("第一版单知识库原文总量上限2MB")
        ids = set()
        for item in content:
            if not isinstance(item, dict):
                raise serializers.ValidationError("条目必须是对象")
            if kind == "knowledge":
                if not isinstance(item.get("name"), str) or not item["name"].lower().endswith((".md", ".txt")) or not isinstance(item.get("text"), str) or not item["text"].strip():
                    raise serializers.ValidationError("文档须包含.md/.txt名称和非空text")
                identifier = item["name"]
            else:
                for key in ("id", "question", "reference", "type"):
                    if not isinstance(item.get(key), str) or not item[key].strip():
                        raise serializers.ValidationError("样本缺少非空字段：" + key)
                if type(item.get("should_refuse")) is not bool or type(item.get("approved")) is not bool:
                    raise serializers.ValidationError("拒答和审核字段必须是布尔值")
                for key in ("required", "forbidden"):
                    if not isinstance(item.get(key, []), list) or not all(isinstance(c, str) and c for c in item.get(key, [])):
                        raise serializers.ValidationError("条件必须是非空字符串数组")
                if not isinstance(item.get("evidence", []), list) or not all(isinstance(e, dict) and isinstance(e.get("text"), str) and e["text"] and isinstance(e.get("document"), str) for e in item.get("evidence", [])):
                    raise serializers.ValidationError("证据须包含document和text")
                if len(item["id"]) > 80:
                    raise serializers.ValidationError("样本标识不得超过80字符")
                identifier = item["id"]
                # 导入文件中的布尔值不构成审核证据，按内容哈希重新匹配审核记录。
                approval = self.instance.approvals.filter(sample_id=identifier,content_hash=sample_fingerprint(item)).order_by("-id").first() if self.instance else None
                item["approved"] = bool(approval and approval.approved)
            if identifier in ids:
                raise serializers.ValidationError("存在重复标识：" + identifier)
            ids.add(identifier)
        return attrs

class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = "__all__"
        read_only_fields = ["reviewer", "created_at"]
    def validate_result(self, value):
        if value.status != "succeeded":
            raise serializers.ValidationError("只能复核已成功执行的问答")
        return value
    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("复核理由不能为空")
        return value

class ResultSerializer(serializers.ModelSerializer):
    reviews = ReviewSerializer(many=True, read_only=True)
    attempts = serializers.SerializerMethodField()
    def get_attempts(self, obj):
        return list(obj.attempts.values("id","phase","status","error_type","output","started_at","finished_at"))
    class Meta:
        model = Result
        fields = "__all__"

class ExperimentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Experiment
        fields = "__all__"
        read_only_fields = ["snapshot", "status", "created_by", "created_at"]
    def validate(self, attrs):
        kb, ds = attrs["knowledge"], attrs["dataset"]
        if kb.kind != "knowledge" or ds.kind != "dataset" or not kb.published or not ds.published:
            raise serializers.ValidationError("请选择已发布的知识库与数据集")
        if kb.product != ds.product:
            raise serializers.ValidationError("知识库与数据集必须属于相同产品")
        config = RagConfigSerializer(data=attrs.get("config", {}))
        config.is_valid(raise_exception=True)
        attrs["config"] = freeze_config(config.validated_data, kb)
        return attrs

class RagConfigSerializer(serializers.Serializer):
    top_k = serializers.IntegerField(min_value=1,max_value=20,default=3)
    backend = serializers.ChoiceField(choices=["mock","live"],default="mock")
    provider = serializers.ChoiceField(choices=["qwen","deepseek"],default="qwen")
    model = serializers.CharField(max_length=120,required=False)
    prompt_version = serializers.ChoiceField(choices=["v1","v2"],default="v1")
    judge_mode = serializers.ChoiceField(choices=["manual","model"],default="manual")
    concurrency = serializers.IntegerField(min_value=1,max_value=5,default=1)
    timeout = serializers.IntegerField(min_value=5,max_value=60,default=45)
    retries = serializers.IntegerField(min_value=0,max_value=2,default=1)
    def validate(self, attrs):
        if attrs["backend"]=="mock" and attrs["judge_mode"]=="model":
            raise serializers.ValidationError("离线模式不能作为真实模型评分")
        if type(self.initial_data.get("top_k",3)) is bool:
            raise serializers.ValidationError("Top K必须为整数")
        return attrs

def freeze_config(config, knowledge):
    config=dict(config)
    generation=connection(provider=config["provider"])
    config["model"]=config.get("model",generation["model"])
    generation["model"]=config["model"]
    config.update(generation=generation,judge=connection("judge"),prompt=PROMPTS[config["prompt_version"]],rule_version="v2")
    config["index"]=knowledge.settings.get("index",{})
    if config["backend"]=="live" and config["index"].get("backend")!="live":
        raise serializers.ValidationError("请先为知识库构建并发布真实向量索引")
    return config

class ApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = SampleApproval
        fields = "__all__"
        read_only_fields = ["asset","content_hash","reviewer","created_at"]

class IndexJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndexJob
        exclude = ["snapshot"]
        read_only_fields = ["id","status"]

class RegressionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegressionMembership
        fields = "__all__"
        read_only_fields = ["sample_id","created_by","created_at"]

class ChatSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatRecord
        fields = "__all__"
