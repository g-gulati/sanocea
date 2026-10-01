"""
SANOCEA Content Engine package.
Autonomous content generation, deduplication, QA validation, and multi-platform publishing.
"""

from packages.content_engine.models import (
    ContentPillar,
    ContentFormat,
    Platform,
    ContentStatus,
    OperationalTopic,
    ContentCopy,
    MediaAsset,
    PlatformAdaptation,
    QAResult,
    ContentRecord,
)


def __getattr__(name):
    # Lazy: importing the package (or packages.content_engine.seo) must not pull in the whole social engine
    # (formats, adapters, Postiz client). `from packages.content_engine import ContentEngine` still works.
    if name == "ContentEngine":
        from packages.content_engine.engine import ContentEngine
        return ContentEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ContentPillar",
    "ContentFormat",
    "Platform",
    "ContentStatus",
    "OperationalTopic",
    "ContentCopy",
    "MediaAsset",
    "PlatformAdaptation",
    "QAResult",
    "ContentRecord",
    "ContentEngine",
]
