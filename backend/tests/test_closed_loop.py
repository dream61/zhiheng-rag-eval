import copy
import json
from datetime import timedelta
from types import SimpleNamespace
import pytest
from django.utils import timezone
from celery.exceptions import Retry
from apps.core.models import Asset, Experiment, Result, ExecutionAttempt, IndexJob
from apps.core.services import evaluate, ask, score
from apps.core.tasks import recover_jobs, run_result

pytestmark=pytest.mark.django_db

def experiment(api,assets,**config):
    response=api.post('/api/experiments/',{'name':'闭环测试','knowledge':assets[0],'dataset':assets[1],'config':dict(backend='mock',retries=0,**config)},format='json')
    assert response.status_code==201,response.data
    return Experiment.objects.get(pk=response.data['id'])

def test_audit_required_and_content_change_invalidates(api):
    sample={'id':'x','question':'问题','reference':'答案','type':'基础','should_refuse':True,'approved':True}
    response=api.post('/api/assets/',{'kind':'dataset','name':'审核','product':'订单','version':'1','content':[sample]},format='json')
    aid=response.data['id'];assert response.data['content'][0]['approved'] is False
    assert api.post(f'/api/assets/{aid}/publish/').status_code==400
    assert api.post(f'/api/assets/{aid}/approve/',{'sample_id':'x','approved':True,'reason':'人工审核'},format='json').status_code==201
    sample['reference']='修改后的参考答案'
    response=api.patch(f'/api/assets/{aid}/',{'content':[sample]},format='json')
    assert response.data['content'][0]['approved'] is False
    assert api.post(f'/api/assets/{aid}/publish/').status_code==400
    history=api.get(f'/api/assets/{aid}/approve/').data
    assert len(history)==1 and history[0]['reviewer']

def test_comparison_and_export(api,assets,settings):
    settings.CELERY_TASK_ALWAYS_EAGER=True
    a=experiment(api,assets,top_k=3);b=experiment(api,assets,top_k=5)
    for e,passed in [(a,False),(b,True)]:
        assert api.post('/api/reviews/',{'result':e.results.get().id,'passed':passed,'reason':'人工复核','attribution':'检索遗漏'},format='json').status_code==201
    data=api.get(f'/api/experiments/{a.id}/compare/?other={b.id}').data
    assert data['summary']['已修复']==1
    assert data['rows'][0]['left']['trace']['evidence']
    changed=copy.deepcopy(b.results.get().sample);changed['reference']='另一答案'
    b.results.update(sample=changed)
    data=api.get(f'/api/experiments/{a.id}/compare/?other={b.id}').data
    assert data['summary']['样本已修改']==1
    exported=api.get(f'/api/experiments/{a.id}/export/?format=json')
    assert exported.status_code==200
    assert json.loads(exported.content)['results'][0]['reviews']
    a.results.update(sample=dict(a.results.get().sample,question='  =HYPERLINK("危险")'))
    csv=api.get(f'/api/experiments/{a.id}/export/?format=csv')
    assert csv.status_code==200
    assert "'  =HYPERLINK" in csv.content.decode()

def test_regression_requires_confirmation_and_reapproval(api,assets,settings):
    settings.CELERY_TASK_ALWAYS_EAGER=True
    e=experiment(api,assets);item=e.results.get()
    target=api.post('/api/assets/',{'kind':'dataset','name':'回归','product':'订单','version':'1','content':[]},format='json').data
    payload={'dataset':target['id'],'source_result':item.id,'reason':'复现缺陷','expected_fix':'回答包含状态限制'}
    assert api.post('/api/regressions/',payload,format='json').status_code==400
    api.post('/api/reviews/',{'result':item.id,'passed':False,'reason':'已确认失败','attribution':'生成错误或遗漏'},format='json')
    assert api.post('/api/regressions/',payload,format='json').status_code==201
    assert api.post('/api/regressions/',payload,format='json').status_code==400
    assert api.post(f"/api/assets/{target['id']}/publish/").status_code==400
    assert Asset.objects.get(pk=target['id']).content[0]['approved'] is False

def test_scoring_retry_preserves_generation(api,assets,settings,monkeypatch):
    settings.CELERY_TASK_ALWAYS_EAGER=True
    with monkeypatch.context() as patch:
        patch.setattr('apps.core.tasks.evaluate',lambda *args:(_ for _ in ()).throw(ValueError('评分失败')))
        e=experiment(api,assets)
    item=e.results.get();original=copy.deepcopy(item.trace)
    assert item.status=='succeeded' and item.scoring_status=='failed'
    report=api.get(f'/api/experiments/{e.id}/report/').data
    assert report['execution_failed']==0 and report['scoring_failed']==1
    monkeypatch.setattr('apps.core.tasks.ask',lambda *args:(_ for _ in ()).throw(AssertionError('不应重新生成')))
    assert api.post(f'/api/experiments/{e.id}/retry/',{'phase':'scoring'},format='json').status_code==200
    item.refresh_from_db();assert item.trace==original and item.scoring_status=='completed'
    assert item.attempts.filter(phase='generation').count()==1
    assert item.attempts.filter(phase='scoring').count()==2

def test_transient_retry_record(api,assets,settings,monkeypatch):
    settings.CELERY_TASK_ALWAYS_EAGER=True
    calls=[]
    def transient(*args):
        calls.append(1)
        if len(calls)==1:raise TimeoutError('临时故障')
        return ask(*args)
    monkeypatch.setattr('apps.core.tasks.ask',transient)
    monkeypatch.setattr('apps.core.tasks.time.sleep',lambda _:None)
    response=api.post('/api/experiments/',{'name':'重试','knowledge':assets[0],'dataset':assets[1],'config':{'backend':'mock','retries':1}},format='json')
    item=Experiment.objects.get(pk=response.data['id']).results.get()
    assert item.status=='succeeded'
    assert list(item.attempts.filter(phase='generation').values_list('status',flat=True))==['failed','succeeded']

def test_lease_recovery_and_attempt_preservation(api,assets,settings):
    settings.CELERY_TASK_ALWAYS_EAGER=True
    e=experiment(api,assets);item=e.results.get()
    Result.objects.filter(pk=item.id).update(status='running',lease_token='过期令牌',lease_until=timezone.now()-timedelta(seconds=1))
    before=item.attempts.count()
    recover_jobs();item.refresh_from_db()
    assert item.status=='succeeded' and item.lease_token==''
    assert item.attempts.count()==before+1

def test_live_index_requires_current_snapshot(api,settings,monkeypatch):
    settings.CELERY_TASK_ALWAYS_EAGER=True
    monkeypatch.setattr('apps.core.tasks.build_index',lambda *args:None)
    a=api.post('/api/assets/',{'kind':'knowledge','name':'真实索引','product':'订单','version':'1','content':[{'name':'a.txt','text':'订单规则'}]},format='json').data
    aid=a['id']
    assert api.post(f'/api/assets/{aid}/publish/',{'backend':'live'},format='json').status_code==400
    job=api.post(f'/api/assets/{aid}/index/',{'backend':'live'},format='json')
    assert job.status_code==201 and job.data['status']=='succeeded'
    api.patch(f'/api/assets/{aid}/',{'content':[{'name':'a.txt','text':'修改后的规则'}]},format='json')
    assert api.post(f'/api/assets/{aid}/publish/',{'backend':'live'},format='json').status_code==400
    api.post(f'/api/assets/{aid}/index/',{'backend':'live'},format='json')
    assert api.post(f'/api/assets/{aid}/publish/',{'backend':'live'},format='json').status_code==200

def test_judge_evidence_validation(monkeypatch):
    trace={'answer':'不可取消','refused':False,'citations':['c1'],'evidence':[{'id':'c1','document':'a','text':'不可取消'}]}
    sample={'question':'能取消吗','reference':'不可取消','should_refuse':False,'required':['不可取消'],'evidence':[{'document':'a','text':'不可取消'}]}
    judgment={d:{'passed':True,'reason':'证据明确支持','evidence_ids':['c1']} for d in ['correctness','groundedness','citation_support']}
    def reply(**kwargs):return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(judgment)))],usage=None)
    monkeypatch.setattr('apps.core.services.client',lambda *args:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=reply))))
    config={'backend':'live','judge_mode':'model','judge':{'model':'测试评分器'}}
    assert evaluate(sample,trace,config)['passed'] is True
    judgment['groundedness']['evidence_ids']=['伪造证据']
    with pytest.raises(ValueError,match='不存在'):evaluate(sample,trace,config)

def test_evidence_across_overlapping_chunks():
    trace={'answer':'甲乙丙丁','refused':False,'citations':['a'],'evidence':[{'id':'a','document':'d','text':'甲乙丙','start':0,'end':3},{'id':'b','document':'d','text':'丙丁','start':2,'end':4}]}
    assert score({'should_refuse':False,'evidence':[{'document':'d','text':'乙丙丁'}]},trace)['evidence_recall']==1

def test_chat_history(api,assets):
    response=api.post(f'/api/assets/{assets[0]}/chat/',{'question':'能取消吗','backend':'mock'},format='json')
    assert response.status_code==200
    history=api.get(f'/api/assets/{assets[0]}/chat/').data
    assert history[0]['trace']['answer']==response.data['answer']

def test_no_live_for_mock_index(api,assets):
    response=api.post('/api/experiments/',{'name':'无索引','knowledge':assets[0],'dataset':assets[1],'config':{'backend':'live'}},format='json')
    assert response.status_code==400

def test_fifty_sample_two_experiments_and_regression(api,settings):
    from pathlib import Path
    settings.CELERY_TASK_ALWAYS_EAGER=True
    folder=Path(__file__).resolve().parents[2]/'examples'/'order-system'
    documents=[{'name':p.name,'text':p.read_text()} for p in folder.glob('*.md')]
    kb=api.post('/api/assets/',{'kind':'knowledge','name':'50条夹具知识','product':'模拟订单系统','version':'test','content':documents},format='json').data
    assert api.post(f"/api/assets/{kb['id']}/publish/").status_code==200
    draft=json.loads((folder/'dataset-draft.json').read_text());draft['version']='test'
    ds=api.post('/api/assets/',draft,format='json').data
    assert len(ds['content'])==50
    assert api.post(f"/api/assets/{ds['id']}/publish/").status_code==400
    for sample in ds['content']:
        assert api.post(f"/api/assets/{ds['id']}/approve/",{'sample_id':sample['id'],'approved':True,'reason':'自动化夹具模拟审核操作，不是真实人工批准'},format='json').status_code==201
    assert api.post(f"/api/assets/{ds['id']}/publish/").status_code==200
    first=experiment(api,(kb['id'],ds['id']),top_k=3)
    second=experiment(api,(kb['id'],ds['id']),top_k=5)
    assert first.results.count()==second.results.count()==50
    assert first.results.filter(status='succeeded').count()==50
    comparison=api.get(f'/api/experiments/{first.id}/compare/?other={second.id}').data
    assert len(comparison['rows'])==50
    source=first.results.first()
    api.post('/api/reviews/',{'result':source.id,'passed':False,'reason':'夹具模拟确认失败','attribution':'检索遗漏'},format='json')
    target=api.post('/api/assets/',{'kind':'dataset','name':'回归闭环','product':'模拟订单系统','version':'test','content':[]},format='json').data
    assert api.post('/api/regressions/',{'dataset':target['id'],'source_result':source.id,'reason':'夹具回归','expected_fix':'结论完整'},format='json').status_code==201
    api.post(f"/api/assets/{target['id']}/approve/",{'sample_id':source.sample_id,'approved':True,'reason':'自动化夹具模拟审核'},format='json')
    assert api.post(f"/api/assets/{target['id']}/publish/").status_code==200
    regression=experiment(api,(kb['id'],target['id']))
    assert regression.results.count()==1 and regression.results.get().status=='succeeded'

def test_roles_restrict_writes(api,assets):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group
    from rest_framework.test import APIClient
    viewer=get_user_model().objects.create_user('只读测试')
    client=APIClient();client.force_authenticate(viewer)
    assert client.get('/api/assets/').status_code==200
    assert client.post('/api/assets/',{},format='json').status_code==403
    viewer.groups.add(Group.objects.get_or_create(name='测试人员')[0])
    assert client.post('/api/reviews/',{},format='json').status_code==403
    viewer.groups.clear();viewer.groups.add(Group.objects.get_or_create(name='复核人员')[0])
    assert client.post('/api/assets/',{},format='json').status_code==403

def test_correctness_can_reference_answer_without_retrieval_id(monkeypatch):
    trace={'answer':'不可取消','refused':False,'citations':['c1'],'evidence':[{'id':'c1','document':'a','text':'不可取消'}]}
    sample={'question':'能取消吗','reference':'不可取消','should_refuse':False}
    judgment={d:{'passed':True,'reason':'已核对参考答案或证据','evidence_ids':([] if d=='correctness' else ['c1'])} for d in ['correctness','groundedness','citation_support']}
    response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(judgment)))],usage=None)
    monkeypatch.setattr('apps.core.services.client',lambda *args:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs:response))))
    result=evaluate(sample,trace,{'backend':'live','judge_mode':'model','judge':{'model':'测试评分器'}})
    assert result['correctness'] is True
    assert result['model_judgment']['correctness']['reference_answer']=='不可取消'
