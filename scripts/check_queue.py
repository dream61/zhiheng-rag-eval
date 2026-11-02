"""提交离线诊断实验，验证真实Redis/Celery链路；不代表真实模型质量验收。"""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from apps.core.models import Asset
from rest_framework.test import APIClient
from django.test import override_settings
assert not settings.CELERY_TASK_ALWAYS_EAGER,'此检查必须使用真实队列'
actor=get_user_model().objects.get(username='审核确认代录')
from django.contrib.auth.models import Group
actor.groups.add(Group.objects.get_or_create(name='测试人员')[0])
dataset=Asset.objects.get(name='订单验收集',version='acceptance-v1')
knowledge=Asset.objects.get(name='订单验收知识库',version='acceptance-v1')
with override_settings(ALLOWED_HOSTS=['testserver']):
 api=APIClient();api.force_authenticate(actor)
 kb=api.post('/api/assets/',{'kind':'knowledge','name':'队列诊断知识库','product':knowledge.product,'version':'queue-v1','content':knowledge.content,'settings':{'chunk_size':350,'overlap':70}},format='json')
 if kb.status_code==400:
  target=Asset.objects.get(name='队列诊断知识库',version='queue-v1')
 else:target=Asset.objects.get(pk=kb.data['id'])
 if not target.published:
  response=api.post(f'/api/assets/{target.id}/publish/',{'backend':'mock'},format='json');assert response.status_code==200,response.data
 response=api.post('/api/experiments/',{'name':'真实队列诊断（离线生成，50条）','knowledge':target.id,'dataset':dataset.id,'config':{'backend':'mock','top_k':3,'concurrency':3,'retries':0}},format='json')
 assert response.status_code==201,response.data
 print('已通过真实Redis投递诊断实验，实验ID：'+str(response.data['id']))
