import copy
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.core.models import Asset, Experiment, Result
from apps.core.services import split_documents, score
from apps.core.tasks import run_experiment
pytestmark = pytest.mark.django_db
@pytest.fixture
def api():
    c=APIClient(); c.force_authenticate(get_user_model().objects.create_user('tester',is_superuser=True)); return c
@pytest.fixture
def assets(api):
    kb=api.post('/api/assets/',{'kind':'knowledge','name':'知识库','product':'订单','version':'1','content':[{'name':'手册.md','text':'已发货订单不支持取消。'}]},format='json').data
    assert api.post(f"/api/assets/{kb['id']}/publish/").status_code==200
    s={'id':'s1','question':'已发货能取消吗？','reference':'不支持取消','type':'状态','should_refuse':False,'approved':True,'required':['不支持取消'],'evidence':[{'document':'手册.md','text':'已发货订单不支持取消。'}]}
    ds=api.post('/api/assets/',{'kind':'dataset','name':'评测集','product':'订单','version':'1','content':[s]},format='json').data
    assert api.post(f"/api/assets/{ds['id']}/approve/", {"sample_id":"s1","approved":True,"reason":"人工核对测试夹具"},format="json").status_code==201
    assert api.post(f"/api/assets/{ds['id']}/publish/").status_code==200
    return kb['id'],ds['id']
