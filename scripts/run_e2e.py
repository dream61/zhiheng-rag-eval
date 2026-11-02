"""在临时数据库中运行界面测试，不使用或修改开发数据库。"""
import os
import secrets
import subprocess
import tempfile
from pathlib import Path

root=Path(__file__).resolve().parent.parent
python=str(root/".venv/bin/python")
with tempfile.TemporaryDirectory(prefix="zhiheng-e2e-") as directory:
    env=dict(os.environ,DB_ENGINE="sqlite",SQLITE_PATH=str(Path(directory)/"e2e.sqlite3"),CELERY_TASK_ALWAYS_EAGER="1",RAG_BACKEND="mock",E2E_USERNAME="界面测试用户",E2E_PASSWORD=secrets.token_urlsafe(24))
    subprocess.run([python,"manage.py","migrate","--noinput"],cwd=root/"backend",env=env,check=True,stdout=subprocess.DEVNULL)
    code="import os;from django.contrib.auth import get_user_model;get_user_model().objects.create_user(os.environ['E2E_USERNAME'],password=os.environ['E2E_PASSWORD'],is_superuser=True)"
    subprocess.run([python,"manage.py","shell","-c",code],cwd=root/"backend",env=env,check=True)
    subprocess.run(["npm","run","test:e2e"],cwd=root/"frontend",env=env,check=True)
