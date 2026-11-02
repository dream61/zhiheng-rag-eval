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
    scoring_status = models.CharField(max_length=30, default="pending")
    scoring_error = models.TextField(blank=True)
    lease_token = models.CharField(max_length=40, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["experiment", "sample_id"], name="unique_experiment_sample")]

class Review(models.Model):
    result = models.ForeignKey(Result, on_delete=models.PROTECT, related_name="reviews")
    passed = models.BooleanField()
    reason = models.TextField()
    attribution = models.CharField(max_length=80, blank=True)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class SampleApproval(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="approvals")
    sample_id = models.CharField(max_length=80)
    content_hash = models.CharField(max_length=64)
    approved = models.BooleanField()
    reason = models.TextField()
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

class ExecutionAttempt(models.Model):
    result = models.ForeignKey(Result, on_delete=models.PROTECT, related_name="attempts")
    phase = models.CharField(max_length=20)
    status = models.CharField(max_length=20, default="running")
    error_type = models.CharField(max_length=100, blank=True)
    output = models.JSONField(default=dict)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)

class IndexJob(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="index_jobs")
    fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=20, default="pending")
    backend = models.CharField(max_length=20)
    snapshot = models.JSONField(default=dict)
    collection = models.CharField(max_length=100, blank=True)
    error = models.CharField(max_length=100, blank=True)
    lease_until = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class RegressionMembership(models.Model):
    dataset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="regression_memberships")
    source_result = models.ForeignKey(Result, on_delete=models.PROTECT)
    sample_id = models.CharField(max_length=80)
    reason = models.TextField()
    expected_fix = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["dataset", "source_result"], name="unique_regression_source")]

class ChatRecord(models.Model):
    knowledge = models.ForeignKey(Asset, on_delete=models.PROTECT)
    question = models.TextField()
    config = models.JSONField()
    trace = models.JSONField(default=dict)
    error = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
