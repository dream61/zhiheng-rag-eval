import os
from locust import HttpUser, task, between

class ReadOnlyUser(HttpUser):
    """仅压测只读API，避免产生模型调用费用。"""
    wait_time = between(1, 3)
    def on_start(self):
        self.client.headers.update({"Authorization": "Token " + os.environ["RAG_TEST_TOKEN"]})
    @task
    def list_assets(self):
        self.client.get("/api/assets/")
