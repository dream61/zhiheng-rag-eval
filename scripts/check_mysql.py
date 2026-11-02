"""使用现有数据库权限执行集成检查，全部测试数据在事务结束时回滚。"""
import os
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.db import transaction,connection
from django.test import override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

assert connection.vendor=='mysql','此脚本仅用于MySQL集成检查'
with override_settings(CELERY_TASK_ALWAYS_EAGER=True,ALLOWED_HOSTS=['testserver']),transaction.atomic():
    user=get_user_model().objects.create_user('事务测试-'+uuid.uuid4().hex,is_superuser=True)
    api=APIClient();api.force_authenticate(user)
    def post(path,data):
        response=api.post('/api/'+path,data,format='json')
        assert response.status_code in (200,201),response.data
        return response.data
    kb=post('assets/',{'kind':'knowledge','name':'事务知识库','product':'事务测试','version':'1','content':[{'name':'a.txt','text':'已发货订单不支持取消。'}]})
    post(f"assets/{kb['id']}/publish/",{})
    sample={'id':'s1','question':'已发货能取消吗','reference':'不支持取消','type':'状态','should_refuse':False,'approved':False,'required':['不支持取消'],'evidence':[{'document':'a.txt','text':'已发货订单不支持取消。'}]}
    ds=post('assets/',{'kind':'dataset','name':'事务评测集','product':'事务测试','version':'1','content':[sample]})
    post(f"assets/{ds['id']}/approve/",{'sample_id':'s1','approved':True,'reason':'集成测试夹具，事务结束回滚'})
    post(f"assets/{ds['id']}/publish/",{})
    e=post('experiments/',{'name':'事务实验','knowledge':kb['id'],'dataset':ds['id'],'config':{'backend':'mock','retries':0}})
    report=api.get(f"/api/experiments/{e['id']}/report/").data
    assert report['execution_success']==1 and report['execution_failed']==0,report
    assert api.get(f"/api/experiments/{e['id']}/export/?format=json").status_code==200
    transaction.set_rollback(True)
print('MySQL事务集成检查通过：资产、审核、发布、评测和导出，测试数据全部回滚。')
