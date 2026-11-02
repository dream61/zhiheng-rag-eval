#!/usr/bin/env bash
# 从工程根目录运行，验证离线业务与前端构建。
set -euo pipefail
cd "$(dirname "$0")/.."
export DB_ENGINE=sqlite
export CELERY_TASK_ALWAYS_EAGER=1
.venv/bin/python backend/manage.py check
(cd backend && ../.venv/bin/python -m pytest -q)
npm run build --prefix frontend
