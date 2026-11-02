"""用合成向量验证真实Qdrant写入、计数、检索，不代表语义Embedding验收。"""
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from qdrant_client import QdrantClient
from apps.core.services import build_index,retrieve
name='diagnostic_'+uuid.uuid4().hex
url=os.environ['QDRANT_URL']
client=QdrantClient(url=url,timeout=15,trust_env=False)
def embeddings(**kwargs):
    return SimpleNamespace(data=[SimpleNamespace(index=i,embedding=[1.0,0.0] if '取消' in text else [0.0,1.0]) for i,text in enumerate(kwargs['input'])])
fake=SimpleNamespace(embeddings=SimpleNamespace(create=embeddings))
chunks=[{'id':'cancel','document':'联调.txt','text':'已发货订单不支持取消。','start':0,'end':13},{'id':'refund','document':'联调.txt','text':'退款通常3个工作日到账。','start':14,'end':28}]
spec={'model':'合成测试向量','key_env':'不读取任何密钥','base_url':'不访问外部服务'}
try:
    with patch('apps.core.services.client',return_value=fake):
        build_index(chunks,name,spec)
        results=retrieve('是否支持取消',chunks,1,'live',{'backend':'live','collection':name,'embedding':spec})
    assert client.count(name,exact=True).count==2
    assert results[0]['id']=='cancel'
    print('真实Qdrant写入、计数与检索检查通过；向量为合成夹具，未验证语义Embedding。')
finally:
    if client.collection_exists(name):client.delete_collection(name)
    client.close()
