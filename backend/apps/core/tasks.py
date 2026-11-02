from celery import shared_task
from .models import Experiment, Result
from .services import ask, score

@shared_task
def run_experiment(experiment_id):
    # 原子认领避免重复投递；崩溃恢复与逐样本并发将在下一迭代实现。
    if not Experiment.objects.filter(pk=experiment_id, status="pending").update(status="running"):
        return
    experiment = Experiment.objects.get(pk=experiment_id)
    for result in experiment.results.order_by("id"):
        if result.status == "succeeded":
            continue
        try:
            result.trace = ask(result.sample["question"], experiment.snapshot["chunks"], experiment.config)
            result.scores = score(result.sample, result.trace)
            result.status = "succeeded"
        except Exception as exc:
            # 只保存异常类型，避免供应商异常文本带出密钥或原始请求。
            result.error = type(exc).__name__
            result.status = "execution_failed"
        result.save()
    experiment.status = "completed"
    experiment.save(update_fields=["status"])
