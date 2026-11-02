from django.conf import settings
from django.db import models

class Asset(models.Model):
    """发布时冻结内容，草稿可编辑。"""
    KIND = [("knowledge", "知识库"), ("dataset", "数据集")]
    kind = models.CharField(max_length=20, choices=KIND)
    name = models.CharField(max_length=120)
    product = models.CharField(max_length=120)
    version = models.CharField(max_length=40)
    content = models.JSONField(default=list)
    settings = models.JSONField(default=dict)
    published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "product", "name", "version"], name="unique_asset_version")]

class Experiment(models.Model):
    name = models.CharField(max_length=120)
    knowledge = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="knowledge_experiments")
    dataset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="dataset_experiments")
    config = models.JSONField(default=dict)
    snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=30, default="pending")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

class Result(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name="results")
    sample_id = models.CharField(max_length=80)
    sample = models.JSONField()
    status = models.CharField(max_length=30, default="pending")
    trace = models.JSONField(default=dict)
    scores = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["experiment", "sample_id"], name="unique_experiment_sample")]

class Review(models.Model):
    result = models.ForeignKey(Result, on_delete=models.PROTECT, related_name="reviews")
    passed = models.BooleanField()
    reason = models.TextField()
    attribution = models.CharField(max_length=80, blank=True)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
