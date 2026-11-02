import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.core.models import Asset

class Command(BaseCommand):
    help = "导入模拟订单资料与待审核样本，不自动审核或发布"
    def handle(self, *args, **options):
        folder = settings.BASE_DIR.parent / "examples" / "order-system"
        documents = [{"name": p.name, "text": p.read_text()} for p in sorted(folder.glob("*.md")) if p.name != "版本更新说明.md"]
        Asset.objects.get_or_create(kind="knowledge", name="订单知识库", product="模拟订单系统", version="v1.0", defaults={"content": documents, "settings": {"chunk_size": 500, "overlap": 80}})
        dataset = json.loads((folder / "dataset-draft.json").read_text())
        Asset.objects.get_or_create(kind=dataset["kind"], name=dataset["name"], product=dataset["product"], version=dataset["version"], defaults={"content": dataset["content"]})
        self.stdout.write(self.style.SUCCESS("已导入草稿；请人工审核样本后发布，未自动批准任何参考答案。"))
