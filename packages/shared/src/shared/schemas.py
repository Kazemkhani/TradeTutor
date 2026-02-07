"""Pydantic schemas for the Stateless Multi-Tenant Voice Agent MVP.

No accounts, no dashboards, no persistent storage.
Any visitor can submit the form and trigger an outbound call immediately.

These schemas are provider-agnostic. Provider-specific configuration
is handled in voice_agent/config.py via environment variables.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field

# =============================================================================
# Constants
# =============================================================================

# Maximum time to keep ephemeral CallJob records in memory
CALL_JOB_TTL_SECONDS: int = 600  # 10 minutes


# =============================================================================
# Form Field Enums
# =============================================================================


class TargetAudience(str, Enum):
    """Who the product/service is targeted at."""

    CONSUMER = "consumer"
    SME = "sme"
    ENTERPRISE = "enterprise"
    OTHER = "other"


class CallGoal(str, Enum):
    """What the call should accomplish."""

    BOOK_MEETING = "book_meeting"
    QUALIFY_INTEREST = "qualify_interest"
    COLLECT_INFO = "collect_info"
    CLOSE_SALE = "close_sale"


class AgentStyle(str, Enum):
    """Communication style for the agent."""

    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    ASSERTIVE = "assertive"
    LUXURY = "luxury"
    CONCISE = "concise"


class CallStatus(str, Enum):
    """Ephemeral call status (in-memory only)."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# Lead (Individual Person to Call)
# =============================================================================


class Lead(BaseModel):
    """A single lead/prospect to be called.

    Each lead is a distinct person with their own phone number
    and optional contact details. This ensures 1:1 mapping between
    phone numbers and the people being called.
    """

    phone: str  # Required, E.164 format (e.g., "+14155551234")
    name: str | None = None  # Lead's name (for personalization)
    company: str | None = None  # Lead's company
    email: str | None = None  # Lead's email (pre-known, not collected on call)
    title: str | None = None  # Lead's job title


# =============================================================================
# Form Submission (Input from Web)
# =============================================================================


class CallRequest(BaseModel):
    """Form submission from web visitor.

    This is the raw input - no processing yet.
    Validated at API boundary before building context.
    """

    # Business owner info
    owner_email: str  # Required - for receiving call results

    # Who to call (1-5 leads, each with their own phone + contact info)
    leads: list[Lead]  # Required, each lead has phone in E.164 format

    # Business info (what to pitch)
    product: str  # Required - what are you selling?
    website_url: str | None = None  # Optional - for context scraping
    context: str = ""  # Free-text product info

    # Call configuration
    goal: CallGoal  # Required - what should the call accomplish?

    # Goal-specific fields
    booking_link: str | None = None  # Required if goal=book_meeting
    payment_link: str | None = None  # Required if goal=close_sale
    pricing_summary: str | None = None  # For close_sale: exact pricing
    urgency_hook: str | None = None  # For close_sale: limited offer
    goal_criteria: str | None = None  # Qualification criteria or info to collect

    # Anti-abuse (validated at API layer)
    turnstile_token: str | None = None  # Cloudflare Turnstile token
    consent: bool = False  # Must be True to proceed
    idempotency_key: str | None = None  # For duplicate request prevention

    @property
    def phone_count(self) -> int:
        """Number of leads to call."""
        return len(self.leads)

    @property
    def phones(self) -> list[str]:
        """Extract phone numbers from leads (backward compatibility)."""
        return [lead.phone for lead in self.leads]


# =============================================================================
# Context Instance (Built by DSPy, Passed to Agent)
# =============================================================================


class ContextInstance(BaseModel):
    """Pre-built context passed to voice agent at call start.

    Built in-memory by context_builder (DSPy allowed here).
    Passed to agent via --context JSON file.
    No DSPy runs during the actual call.
    """

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # From form submission
    owner_email: str  # For sending results
    phone: str  # Individual phone for this call
    name: str | None = None  # Lead's name
    lead_company: str | None = None  # Lead's company
    lead_title: str | None = None  # Lead's job title
    lead_email_preknown: str | None = None  # Lead's email (known before call)
    product: str
    goal: CallGoal

    # Goal-specific fields
    booking_link: str | None = None  # For book_meeting
    payment_link: str | None = None  # For close_sale
    pricing_summary: str | None = None  # For close_sale
    urgency_hook: str | None = None  # For close_sale
    goal_criteria: str | None = None

    # Generated by DSPy context_builder
    agent_instructions: str  # Full system prompt for the agent (varies by goal)
    opening_line: str  # What the agent says first
    qualification_questions: list[str] = Field(default_factory=list)
    objection_handlers: dict[str, str] = Field(
        default_factory=dict
    )  # More assertive for close_sale
    closing_script: str = ""  # How to end the call

    # Email config (for lead)
    should_email_lead: bool = False  # True if book_meeting or close_sale
    lead_email_template: str = ""  # "booking" or "payment"


# =============================================================================
# Ephemeral Call Job (In-Memory Only)
# =============================================================================


class CallJob(BaseModel):
    """Ephemeral call record - kept in-memory for max 10 minutes.

    No persistent storage. For debugging only.
    Use is_expired() to check if record should be cleaned up.
    """

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Reference to context (passed inline, not stored)
    context_id: UUID
    phone: str

    # Status tracking
    status: CallStatus = CallStatus.PENDING
    started_at: datetime | None = None
    ended_at: datetime | None = None

    # Optional outcome (if we want to log it before expiry)
    sms_sent: bool = False
    error: str | None = None

    @computed_field
    @property
    def expires_at(self) -> datetime:
        """When this record should be cleaned up."""
        return self.created_at + timedelta(seconds=CALL_JOB_TTL_SECONDS)

    def is_expired(self) -> bool:
        """Check if this record has exceeded its TTL and should be removed."""
        return datetime.now(timezone.utc) > self.expires_at

    def seconds_until_expiry(self) -> float:
        """Seconds remaining until this record expires. Negative if already expired."""
        delta = self.expires_at - datetime.now(timezone.utc)
        return delta.total_seconds()


# =============================================================================
# Submission (Batch of Calls)
# =============================================================================


class SubmissionStatus(str, Enum):
    """Status of a batch submission."""

    SUBMITTED = "submitted"
    VALIDATED = "validated"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    EMAILING = "emailing"
    COMPLETE = "complete"
    PARTIAL = "partial"  # Some calls failed
    FAILED = "failed"
    REJECTED = "rejected"  # Validation failed
    THROTTLED = "throttled"  # Rate limited


class Submission(BaseModel):
    """Batch submission tracking - links multiple calls together.

    Created when a form is submitted with 1-5 phone numbers.
    Tracks overall progress and aggregates results.
    """

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # From form
    owner_email: str
    leads: list[Lead]  # 1-5 leads to call
    goal: CallGoal

    # Status tracking
    status: SubmissionStatus = SubmissionStatus.SUBMITTED
    call_ids: list[UUID] = Field(default_factory=list)  # Individual call tracking

    # Results (populated after completion)
    results: list["CallResult"] = Field(default_factory=list)
    owner_email_sent: bool = False
    owner_email_sent_at: datetime | None = None

    # Idempotency
    idempotency_key: str | None = None

    # Timestamps
    completed_at: datetime | None = None

    @property
    def phones(self) -> list[str]:
        """Extract phone numbers from leads (backward compatibility)."""
        return [lead.phone for lead in self.leads]

    @property
    def all_calls_done(self) -> bool:
        """Check if all calls have completed."""
        return len(self.results) == len(self.leads)

    @property
    def successful_calls(self) -> int:
        """Count of calls that completed without error."""
        return sum(1 for r in self.results if r.error is None)


# =============================================================================
# Call Result (After Each Call)
# =============================================================================


class CallResult(BaseModel):
    """Result of a single call within a submission.

    Created after each call completes (success or failure).
    Linked back to parent submission.
    """

    call_id: UUID = Field(default_factory=uuid4)
    submission_id: UUID  # Links to parent submission
    phone: str
    duration_seconds: int = 0
    goal: CallGoal

    # Outcome tracking
    # Values by goal:
    # - book_meeting: booked / declined / no_answer / disconnected / error
    # - qualify_interest: qualified / not_qualified / no_answer / disconnected / error
    # - collect_info: collected / partial / declined / no_answer / disconnected / error
    # - close_sale: committed / soft_commitment / objection_price / objection_timing /
    #               objection_trust / no_interest / no_answer / disconnected / error
    outcome: str = "pending"
    objection_reason: str | None = None  # For close_sale: why they said no

    # Collected data
    collected_data: dict = Field(default_factory=dict)
    lead_email: str | None = None  # Email captured from lead (if any)

    # Transcript and recording
    transcript: str | None = None  # Full conversation (None if failed)
    recording_url: str | None = None  # LiveKit recording URL

    # Email tracking
    lead_email_sent: bool = False  # For book_meeting/close_sale: sent link to lead

    # Error tracking
    error: str | None = None  # Error message if call failed

    # Timestamps
    started_at: datetime | None = None
    ended_at: datetime | None = None
