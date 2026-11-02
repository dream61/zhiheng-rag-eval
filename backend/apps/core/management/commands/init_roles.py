from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
class Command(BaseCommand):
    help='创建空的测试、复核和只读角色，由管理员分配成员'
    def handle(self,*args,**kwargs):
        for name in ('测试人员','复核人员','只读用户'):Group.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS('角色已创建，未自动给现有用户新增权限。'))
