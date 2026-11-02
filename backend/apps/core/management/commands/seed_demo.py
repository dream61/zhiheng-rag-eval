import json
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.core.models import Asset

class Command(BaseCommand):
    help = "导入模拟订单文档与50条待审核样本，不自动审核或发布"
    def add_arguments(self, parser):
        parser.add_argument("--refresh-drafts",action="store_true",help="更新同名草稿，变更样本的旧审核记录将失效")
    def handle(self, *args, **options):
        folder=settings.BASE_DIR.parent/"examples"/"order-system"
        documents=[{"name":p.name,"text":p.read_text()} for p in sorted(folder.glob("*.md"))]
        dataset=json.loads((folder/"dataset-draft.json").read_text())
        for kind,name,content,config in [("knowledge","订单知识库",documents,{"chunk_size":500,"overlap":80}),("dataset",dataset["name"],dataset["content"],{})]:
            asset,created=Asset.objects.get_or_create(kind=kind,name=name,product="模拟订单系统",version="v1.0",defaults={"content":content,"settings":config})
            if not created and options["refresh_drafts"]:
                if asset.published:
                    self.stdout.write(self.style.WARNING(name+"已发布，保持原样；请新建版本导入资料。"))
                else:
                    asset.content=content;asset.settings=config;asset.save()
        self.stdout.write(self.style.SUCCESS("演示资料已准备；50条样本全部待人工审核，未自动批准参考答案。"))
