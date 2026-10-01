"""
Data models for the Sanocea Content Engine.
Defines canonical schemas for pillars, topics, copy, media assets, QA gates, approvals, and platform adaptations.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ContentPillar(str, Enum):
    INVENTORY_VELOCITY = "inventory_velocity"
    MARKETPLACE_OPS = "marketplace_ops"
    ORDER_SLA = "order_sla"
    FULFILLMENT_SYNC = "fulfillment_sync"
    FINANCIAL_RECONCILIATION = "financial_reconciliation"
    HUMAN_IN_THE_LOOP_AI = "human_in_the_loop_ai"
    DYNAMIC_PRICING = "dynamic_pricing"
    OMNICHANNEL_EXCEPTIONS = "omnichannel_exceptions"


class ContentFormat(str, Enum):
    CAROUSEL = "carousel"
    STATIC = "static"
    REEL = "reel"


class Platform(str, Enum):
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    LINKEDIN = "linkedin"


class ContentStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"


class OperationalTopic(BaseModel):
    id: str
    pillar: ContentPillar
    title: str
    summary: str
    operational_problem: str
    root_cause: str
    corrective_action: str
    keywords: List[str] = Field(default_factory=list)
    suggested_formats: List[ContentFormat] = Field(default_factory=list)
    visual_archetype: Optional[str] = None
    operational_data: Optional[Dict[str, Any]] = None


class ContentCopy(BaseModel):
    headline_hook: str
    problem_narrative: str
    mechanism_explanation: str
    solution_narrative: str
    call_to_action: str
    alt_text: str
    first_comment: Optional[str] = None


class MediaAsset(BaseModel):
    sequence: int = 1
    filename: str
    local_path: str
    mime_type: str = "image/png"
    width: int = 1080
    height: int = 1350
    alt_text: str = ""
    postiz_media_id: Optional[str] = None
    postiz_remote_url: Optional[str] = None


class PlatformAdaptation(BaseModel):
    platform: Platform
    integration_id: str
    post_type: str = "post"
    caption: str
    hashtags: List[str] = Field(default_factory=list)
    first_comment: Optional[str] = None
    link_url: Optional[str] = None
    media_ids: List[str] = Field(default_factory=list)


class QACheckItem(BaseModel):
    check_name: str
    passed: bool
    details: str


class QAResult(BaseModel):
    passed: bool
    checks: List[QACheckItem] = Field(default_factory=list)
    failure_reasons: List[str] = Field(default_factory=list)
    wordmark_verified: bool = False
    dimensions_verified: bool = False
    no_fabricated_stats: bool = True
    no_unsupported_claims: bool = True


class ApprovalRecord(BaseModel):
    approved: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    notes: Optional[str] = None


class SchedulingRecord(BaseModel):
    target_utc: str
    target_local: str
    postiz_post_ids: List[str] = Field(default_factory=list)
    status: ContentStatus = ContentStatus.DRAFT


class ContentRecord(BaseModel):
    content_id: str
    tenant_id: str = "sanocea"
    pillar: ContentPillar
    topic: OperationalTopic
    format: ContentFormat
    status: ContentStatus = ContentStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.utcnow)
    content_copy: ContentCopy = Field(..., alias="copy")
    media: List[MediaAsset] = Field(default_factory=list)
    platform_adaptations: Dict[str, PlatformAdaptation] = Field(default_factory=dict)
    qa_results: Optional[QAResult] = None
    approval: ApprovalRecord = Field(default_factory=ApprovalRecord)
    scheduling: Optional[SchedulingRecord] = None
    publication_ids: Dict[str, str] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @property
    def copy(self) -> ContentCopy:
        return self.content_copy

    @copy.setter
    def copy(self, val: ContentCopy):
        self.content_copy = val

    def is_publishable(self) -> bool:
        """Determines if the record is approved, passed QA, and ready for Postiz dispatch."""
        if not self.approval.approved:
            return False
        if not self.qa_results or not self.qa_results.passed:
            return False
        if not self.media:
            return False
        if not self.platform_adaptations:
            return False
        return True
