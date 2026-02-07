"""Shared schemas for the Stateless Multi-Tenant Voice Agent MVP."""

from shared.email import (
    EmailConfig,
    EmailSender,
    send_post_call_emails,
)
from shared.schemas import (
    CALL_JOB_TTL_SECONDS,
    CallGoal,
    CallJob,
    CallRequest,
    CallResult,
    CallStatus,
    ContextInstance,
    Lead,
    Submission,
    SubmissionStatus,
)
from shared.scraper import (
    ScrapedContent,
    WebsiteScraper,
    scrape_website,
    summarize_website_content,
)

__all__ = [
    "CALL_JOB_TTL_SECONDS",
    "CallGoal",
    "CallJob",
    "CallRequest",
    "CallResult",
    "CallStatus",
    "ContextInstance",
    "EmailConfig",
    "EmailSender",
    "Lead",
    "ScrapedContent",
    "Submission",
    "SubmissionStatus",
    "WebsiteScraper",
    "scrape_website",
    "send_post_call_emails",
    "summarize_website_content",
]
