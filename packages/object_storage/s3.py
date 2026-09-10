from __future__ import annotations

import hashlib
from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class ObjectStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredObject:
    uri: str
    checksum: str
    size: int
    content_type: str


class S3ObjectStorage:
    def __init__(
        self,
        *,
        endpoint_url: str | None,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        region_name: str = "us-east-1",
    ) -> None:
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region_name,
        )

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, *, merchant_id: str, key: str, content: bytes, content_type: str) -> StoredObject:
        checksum = hashlib.sha256(content).hexdigest()
        object_key = self._tenant_key(merchant_id, key)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=object_key,
                Body=content,
                ContentType=content_type,
                Metadata={"sha256": checksum, "merchant_id": merchant_id},
            )
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageError(str(exc)) from exc
        return StoredObject(
            uri=f"s3://{self.bucket}/{object_key}",
            checksum=checksum,
            size=len(content),
            content_type=content_type,
        )

    def get(self, *, merchant_id: str, uri: str) -> bytes:
        bucket, key = self._parse_uri(uri)
        if bucket != self.bucket or not key.startswith(f"merchants/{merchant_id}/"):
            raise PermissionError(f"{merchant_id} cannot access object {uri}")
        try:
            response = self.client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            raise ObjectStorageError(str(exc)) from exc

    def health(self) -> dict[str, str]:
        self.client.list_buckets()
        return {"object_storage": "ok"}

    def _tenant_key(self, merchant_id: str, key: str) -> str:
        safe_key = key.replace("\\", "/").lstrip("/")
        return f"merchants/{merchant_id}/{safe_key}"

    def _parse_uri(self, uri: str) -> tuple[str, str]:
        if not uri.startswith("s3://"):
            raise ValueError(uri)
        bucket, key = uri[5:].split("/", 1)
        return bucket, key

