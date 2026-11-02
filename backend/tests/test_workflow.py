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
    c=APIClient(); c.force_authenticate(get_user_model().objects.create_user('tester')); return c
@pytest.fixture
def assets(api):
    kb=api.post('/api/assets/',{'kind':'knowledge','name':'知识库','product':'订单','version':'1','content':[{'name':'手册.md','text':'已发货订单不支持取消。'}]},format='json').data
    assert api.post(f"/api/assets/{kb['id']}/publish/").status_code==200
    s={'id':'s1','question':'已发货能取消吗？','reference':'不支持取消','type':'状态','should_refuse':False,'approved':True,'required':['不支持取消'],'evidence':[{'document':'手册.md','text':'已发货订单不支持取消。'}]}
    ds=api.post('/api/assets/',{'kind':'dataset','name':'评测集','product':'订单','version':'1','content':[s]},format='json').data
    assert api.post(f"/api/assets/{ds['id']}/publish/").status_code==200
    return kb['id'],ds['id']
def test_auth():
    assert APIClient().get('/api/assets/').status_code==401
    assert APIClient().get('/api/health/').status_code==200
def test_immutable(api,assets):
    assert api.patch(f'/api/assets/{assets[0]}/',{'name':'篡改'},format='json').status_code==400
    assert api.delete(f'/api/assets/{assets[0]}/').status_code==405
def test_unapproved_and_duplicate(api):
    s={'id':'x','question':'问题','reference':'答案','type':'基础','should_refuse':True,'approved':False}
    d={'kind':'dataset','name':'未审','product':'订单','version':'1','content':[s]}
    r=api.post('/api/assets/',d,format='json')
    assert r.status_code==201
    assert api.post(f"/api/assets/{r.data['id']}/publish/").status_code==400
    d['name']='重复';d['content']=[s,s]
    assert api.post('/api/assets/',d,format='json').status_code==400

def test_workflow_snapshot_review_idempotency(api,assets,settings):
    settings.CELERY_TASK_ALWAYS_EAGER=True
    r=api.post('/api/experiments/',{'name':'实验','knowledge':assets[0],'dataset':assets[1],'config':{'top_k':3,'backend':'mock'}},format='json')
    assert r.status_code==201,r.data
    e=Experiment.objects.get(pk=r.data['id']); assert e.status=='completed'
    item=e.results.get(); assert item.status=='succeeded'; assert item.scores['passed'] is None
    old=copy.deepcopy(item.scores)
    assert api.post('/api/reviews/',{'result':item.id,'passed':False,'reason':'人工核对不达标','attribution':'生成遗漏'},format='json').status_code==201
    item.refresh_from_db();assert item.scores==old
    report=api.get(f'/api/experiments/{e.id}/report/').data
    assert report['quality_failed']==1;assert report['execution_failed']==0
    Asset.objects.filter(pk=assets[0]).update(content=[])
    e.refresh_from_db();assert e.snapshot['knowledge']
    run_experiment(e.id);assert e.results.count()==1

def test_execution_failure_separate(api,assets,settings,monkeypatch):
    settings.CELERY_TASK_ALWAYS_EAGER=True
    def fail(*args):raise TimeoutError('模拟超时')
    monkeypatch.setattr('apps.core.tasks.ask',fail)
    r=api.post('/api/experiments/',{'name':'异常','knowledge':assets[0],'dataset':assets[1]},format='json')
    report=api.get(f"/api/experiments/{r.data['id']}/report/").data
    assert report['execution_failed']==1;assert report['quality_failed']==0

def test_invalid_top_k(api,assets):
    assert api.post('/api/experiments/',{'name':'非法','knowledge':assets[0],'dataset':assets[1],'config':{'top_k':False}},format='json').status_code==400

def test_split():
    chunks=split_documents([{'name':'a.txt','text':'甲'*230}],100,20)
    assert [c['start'] for c in chunks]==[0,80,160]
    assert chunks[-1]['end']==230
    with pytest.raises(ValueError):split_documents([],100,100)

def test_citation():
    result=score({'should_refuse':False,'required':[]},{'answer':'回答','refused':False,'citations':['伪造'],'evidence':[]})
    assert result['passed'] is False
