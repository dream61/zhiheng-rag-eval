import time
import uuid
from datetime import timedelta
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
from .models import Experiment, Result, ExecutionAttempt, IndexJob
from .services import ask, score, evaluate, build_index

RETRYABLE = {"TimeoutError", "APITimeoutError", "APIConnectionError", "RateLimitError", "InternalServerError", "ServiceUnavailableError"}

def finish_experiment(experiment_id):
    with transaction.atomic():
        e = Experiment.objects.select_for_update().get(pk=experiment_id)
        if not e.results.filter(status__in=["pending","running"]).exists():
            e.status="completed"
            e.save(update_fields=["status"])

def attempt_call(result, phase, function, retries):
    for number in range(retries+1):
        attempt=ExecutionAttempt.objects.create(result=result,phase=phase)
        try:
            output=function()
        except Exception as exc:
            attempt.status="failed";attempt.error_type=type(exc).__name__;attempt.finished_at=timezone.now();attempt.save()
            if type(exc).__name__ not in RETRYABLE or number==retries:
                raise
            time.sleep(min(2**number, 4))
        else:
            attempt.status="succeeded";attempt.output=output;attempt.finished_at=timezone.now();attempt.save()
            return output

@shared_task(bind=True, acks_late=True, soft_time_limit=540, time_limit=600)
def run_result(self, result_id):
    token=uuid.uuid4().hex
    with transaction.atomic():
        item=Result.objects.get(pk=result_id)
        e=Experiment.objects.select_for_update().get(pk=item.experiment_id)
        item=Result.objects.select_for_update().get(pk=result_id)
        if item.status!="pending":
            return
        active=e.results.filter(status="running").count()
        if active>=e.config.get("concurrency",1):
            raise self.retry(countdown=3,max_retries=None)
        item.status="running";item.lease_token=token;item.lease_until=timezone.now()+timedelta(minutes=15)
        item.save(update_fields=["status","lease_token","lease_until"])
        e.status="running";e.save(update_fields=["status"])
    # 对每阶段单独留存尝试，评分重试复用已成功的问答轨迹。
    try:
        if not item.trace:
            trace=attempt_call(item,"generation",lambda:ask(item.sample["question"],e.snapshot["chunks"],e.config),e.config.get("retries",0))
            if not Result.objects.filter(pk=item.id,lease_token=token).update(trace=trace):
                return
            item.trace=trace
        try:
            scores=attempt_call(item,"scoring",lambda:evaluate(item.sample,item.trace,e.config),e.config.get("retries",0))
            Result.objects.filter(pk=item.id,lease_token=token).update(scores=scores,scoring_status="completed",scoring_error="",status="succeeded",lease_until=None,lease_token="",error="")
        except Exception as exc:
            Result.objects.filter(pk=item.id,lease_token=token).update(scores=score(item.sample,item.trace),scoring_status="failed",scoring_error=type(exc).__name__,status="succeeded",lease_until=None,lease_token="")
    except Exception as exc:
        Result.objects.filter(pk=item.id,lease_token=token).update(status="execution_failed",error=type(exc).__name__,lease_until=None,lease_token="")
    finish_experiment(e.id)

@shared_task
def run_experiment(experiment_id):
    e=Experiment.objects.get(pk=experiment_id)
    for result_id in e.results.filter(status="pending").values_list("id",flat=True):
        run_result.delay(result_id)
    finish_experiment(e.id)

@shared_task(acks_late=True, soft_time_limit=540, time_limit=600)
def run_index(job_id):
    if not IndexJob.objects.filter(pk=job_id,status="pending").update(status="running",lease_until=timezone.now()+timedelta(minutes=15)):
        return
    job=IndexJob.objects.get(pk=job_id)
    try:
        if job.backend=="live":
            build_index(job.snapshot["chunks"],job.collection,job.snapshot["embedding"])
        job.status="succeeded"
    except Exception as exc:
        job.status="failed";job.error=type(exc).__name__
    job.lease_until=None;job.save()

@shared_task
def recover_jobs():
    now=timezone.now()
    # 只有租约到期才恢复；租约长于任务硬超时，旧Worker不能覆盖新认领结果。
    expired=Result.objects.filter(status="running",lease_until__lt=now)
    expired.update(status="pending",lease_token="",lease_until=None)
    IndexJob.objects.filter(status="running",lease_until__lt=now).update(status="failed",error="WorkerLeaseExpired",lease_until=None)
    for job_id in IndexJob.objects.filter(status="pending").values_list("id",flat=True):
        run_index.delay(job_id)
    for experiment_id in Experiment.objects.filter(results__status="pending").values_list("id",flat=True).distinct():
        run_experiment.delay(experiment_id)
