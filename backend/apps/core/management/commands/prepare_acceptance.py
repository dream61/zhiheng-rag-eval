"""仅根据已获用户确认的审核清单建立验收资产。"""
import json
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from apps.core.models import Asset,SampleApproval
from apps.core.serializers import AssetSerializer
from apps.core.fingerprints import fingerprint,sample_fingerprint

class Command(BaseCommand):
    help="读取已确认的审核记录，校验全部样本哈希后建立验收资产"
    def add_arguments(self,parser):
        parser.add_argument('--manifest',required=True)
    @transaction.atomic
    def handle(self,*args,**options):
        root=settings.BASE_DIR.parent
        manifest=json.loads(Path(options['manifest']).read_text())
        draft=json.loads((root/'examples/order-system/dataset-draft.json').read_text())
        if manifest.get('dataset_hash')!=fingerprint(draft['content']) or len(draft['content'])!=50:
            raise CommandError('审核清单与当前50条样本不一致，禁止沿用确认')
        for sample in draft['content']:
            if manifest['sample_hashes'].get(sample['id'])!=sample_fingerprint(sample):
                raise CommandError('样本审核哈希不一致：'+sample['id'])
        actor,_=get_user_model().objects.get_or_create(username='审核确认代录',defaults={'is_active':False})
        if actor.has_usable_password():actor.set_unusable_password();actor.save()
        knowledge,created=Asset.objects.get_or_create(kind='knowledge',name='订单验收知识库',product=draft['product'],version='acceptance-v1',defaults={'content':[{'name':p.name,'text':p.read_text()} for p in sorted((root/'examples/order-system').glob('*.md'))],'settings':{'chunk_size':350,'overlap':70}})
        dataset=Asset.objects.filter(kind='dataset',name='订单验收集',product=draft['product'],version='acceptance-v1').first()
        if not dataset:
            draft.update(name='订单验收集',version='acceptance-v1')
            serializer=AssetSerializer(data=draft);serializer.is_valid(raise_exception=True);dataset=serializer.save()
        if not dataset.published:
            if any(sample_fingerprint(s)!=manifest['sample_hashes'].get(s['id']) for s in dataset.content):
                raise CommandError('已存在验收集的内容不匹配')
            for sample in dataset.content:
                if not dataset.approvals.filter(sample_id=sample['id'],content_hash=sample_fingerprint(sample),approved=True).exists():
                    SampleApproval.objects.create(asset=dataset,sample_id=sample['id'],content_hash=sample_fingerprint(sample),approved=True,reason=manifest['confirmation']+'；审核者：'+manifest['reviewer']+'；'+manifest['recording_method'],reviewer=actor)
                sample['approved']=True
            dataset.published=True;dataset.save()
        self.stdout.write(json.dumps({'知识库ID':knowledge.id,'数据集ID':dataset.id,'样本数':len(dataset.content),'审核依据':'用户确认及逐条内容哈希'},ensure_ascii=False))
