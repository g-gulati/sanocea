from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import MediaAsset
from sanocea.packages.domain_contract.store import Phase0Store
from sanocea.packages.object_storage import S3ObjectStorage


class ImageProcessingService:
    def __init__(self, store: Phase0Store, storage: S3ObjectStorage) -> None:
        self.store = store
        self.storage = storage
        self.audit = AuditLedger(store)

    def transform(self, merchant_id: str, path: Path, profile: str = "thumbnail") -> MediaAsset:
        source = self.storage.put(
            merchant_id=merchant_id,
            key=f"media/source/{path.name}",
            content=path.read_bytes(),
            content_type="image/png",
        )
        image = Image.open(path)
        if profile == "thumbnail":
            image.thumbnail((512, 512))
        output = BytesIO()
        image.save(output, format="WEBP")
        transformed = self.storage.put(
            merchant_id=merchant_id,
            key=f"media/{profile}/{path.stem}.webp",
            content=output.getvalue(),
            content_type="image/webp",
        )
        asset = MediaAsset(
            merchant_id=merchant_id,
            object_uri=transformed.uri,
            checksum=transformed.checksum,
            mime_type="image/webp",
            transforms={profile: transformed.uri, "source": source.uri},
            evidence_refs=[source.uri],
        )
        self.store.put(asset)
        self.audit.record(
            merchant_id=merchant_id,
            actor="media",
            source="imgproxy/libvips-boundary",
            action="media_transformed",
            object_type="MediaAsset",
            object_id=asset.id,
            evidence_ref=source.uri,
            result="created",
        )
        return asset

