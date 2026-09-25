import os

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "admin-pass")

from arq.connections import RedisSettings

from workers.arq_app import WorkerSettings
from workers.tasks import run_ingestion_job


def test_worker_settings_are_what_arq_expects() -> None:
    assert isinstance(WorkerSettings.redis_settings, RedisSettings)
    assert run_ingestion_job in WorkerSettings.functions
