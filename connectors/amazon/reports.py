from __future__ import annotations

from dataclasses import dataclass

from .mappings import ASYNC_JOB_STATUS_MAP

"""Step 9Q.3 Part D - Amazon's Feeds and Reports APIs are genuinely asynchronous (confirmed directly
from the primary feeds_2021-06-30.json / reports_2021-06-30.json models this step: createFeed/
createReport return immediately with an id; the actual outcome is learned later via a SEPARATE
getFeed/getReport status poll). A submitted feed/report is NOT an applied mutation - this module makes
that distinction explicit rather than hiding it behind a synchronous-looking fake success, and reuses
Step 9's CONFIRMED_SUCCEEDED / CONFIRMED_NOT_APPLIED / STILL_UNKNOWN vocabulary
(packages/post_order/operations.py) for the verdict, since the shape of the problem is identical:
UNKNOWN RESULT != FAILED RESULT.

Polling ownership: nothing in this module or connectors/amazon/connector.py loops/waits for a job to
finish. `get_feed_status`/`get_report_status` (connector.py) each make exactly ONE status check and
return the current state - a caller (a bounded harness, or a future scheduled worker) decides when and
how many times to call again. This matches the session-wide "bounded harness owns repetition" rule.
"""


@dataclass
class AsyncJobResult:
    external_job_id: str
    amazon_status: str
    connector_command_status: str  # one of ConnectorCommand.status's Literal values
    verdict: str  # "STILL_UNKNOWN" | "CONFIRMED_SUCCEEDED" | "CONFIRMED_NOT_APPLIED"
    document_id: str | None = None


def interpret_async_status(external_job_id: str, amazon_status: str, document_id: str | None = None) -> AsyncJobResult:
    connector_command_status = ASYNC_JOB_STATUS_MAP.get(amazon_status, "executing")
    if amazon_status == "DONE":
        verdict = "CONFIRMED_SUCCEEDED"
    elif amazon_status in {"CANCELLED", "FATAL"}:
        verdict = "CONFIRMED_NOT_APPLIED"
    else:
        # IN_QUEUE, IN_PROGRESS, or any future/unrecognized value - genuinely still unresolved. An
        # unrecognized value is deliberately treated as unknown, never guessed toward success or failure.
        verdict = "STILL_UNKNOWN"
    return AsyncJobResult(
        external_job_id=external_job_id, amazon_status=amazon_status,
        connector_command_status=connector_command_status, verdict=verdict, document_id=document_id,
    )
