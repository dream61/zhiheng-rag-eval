from rest_framework import serializers
from .models import Asset, Experiment, Result, Review
from .services import PROMPT
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
        if not isinstance(content, list):
            raise serializers.ValidationError("内容必须是数组")
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
                identifier = item["id"]
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
        config = attrs.get("config", {})
        k = config.get("top_k", 3)
        if type(k) is not int or not 1 <= k <= 20:
            raise serializers.ValidationError("Top K须为1到20的整数")
        backend = config.get("backend", settings.RAG_BACKEND)
        if backend not in ("mock", "live"):
            raise serializers.ValidationError("无效的执行模式")
        attrs["config"] = {"top_k": k, "backend": backend, "model": config.get("model", os.getenv("LLM_MODEL", "qwen-plus")), "prompt": PROMPT, "prompt_version": "v1", "rule_version": "v1"}
        return attrs
