import os

os.environ.setdefault("SECRET_KEY", "x" * 32)
os.environ.setdefault("ADMIN_PASSWORD", "admin-pass")

import boto3

from app.core.config import Settings


def test_default_s3_endpoint_is_a_hostname_boto3_accepts(monkeypatch) -> None:
    """botocore rejects underscores in hostnames (e.g. the container name v3_minio)."""
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    s = Settings(_env_file=None)
    boto3.client("s3", endpoint_url=s.s3_endpoint_url, region_name="us-east-1",
                 aws_access_key_id="a", aws_secret_access_key="b")
