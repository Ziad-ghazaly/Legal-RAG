"""S3-compatible object storage (MinIO locally). boto3 is sync → run in a thread."""

import asyncio
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings


@lru_cache(maxsize=1)
def _client() -> Any:
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name="us-east-1",
    )


def _ensure_bucket(bucket: str) -> None:
    try:
        _client().head_bucket(Bucket=bucket)
    except ClientError:
        _client().create_bucket(Bucket=bucket)


def _put(key: str, data: bytes, content_type: str) -> None:
    bucket = get_settings().s3_bucket_uploads
    _ensure_bucket(bucket)
    _client().put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def _get(key: str) -> bytes:
    obj = _client().get_object(Bucket=get_settings().s3_bucket_uploads, Key=key)
    return obj["Body"].read()


async def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    await asyncio.to_thread(_put, key, data, content_type)


async def get_bytes(key: str) -> bytes:
    return await asyncio.to_thread(_get, key)
