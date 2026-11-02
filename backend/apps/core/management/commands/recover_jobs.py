from django.core.management.base import BaseCommand
from apps.core.tasks import recover_jobs
class Command(BaseCommand):
    help="重新投递待执行任务，并恢复租约到期的样本"
    def handle(self,*args,**kwargs):
        recover_jobs()
        self.stdout.write(self.style.SUCCESS("恢复调度已执行"))
