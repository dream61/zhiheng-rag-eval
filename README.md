# 知衡 RAG 问答质量评测平台

基于React18、Django5.0、MySQL、LangGraph、Celery/Redis、Qdrant与通义兼容接口，建设可追溯的RAG评测闭环。

当前版本V0.2：版本化资产、人工审核、异步索引、批量实验、模型评分、人工复核、实验对比、明细导出与回归集已实现；真实向量服务与完整模型验收进度，详见[迭代计划](docs/06-迭代与测试计划.md)。

## 文档与启动

- [交付文档目录](docs/README.md)
- [需求规格说明书](docs/01-需求规格说明书.md)
- [概要技术设计](docs/02-概要技术设计.md)
- [开发部署指南](docs/05-开发部署指南.md)

Python包必须安装到工程.venv；VS Code已配置该解释器。标准环境使用MySQL+Redis+Qdrant；离线功能验证可显式选择SQLite和mock，不能据此判断真实RAG质量。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.lock.txt
npm ci --prefix frontend
cp .env.example .env
docker compose --env-file .env -f infra/compose.yaml up -d
cd backend
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

另开终端启动Worker与前端，完整步骤见部署指南。演示样本均为待审核草稿，发布前需要人工核对。
