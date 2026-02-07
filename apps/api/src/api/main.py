"""FastAPI application for Voice Agent SaaS.

Provides:
- Lead qualification calls with usage-based billing
- JWT authentication
- Subscription management via Stripe
- Referral program with commission tracking
- Anti-fraud protection

Flow:
1. POST /auth/signup - Create account (with trial)
2. POST /auth/login - Get JWT token
3. POST /calls - Submit form, build context, dispatch calls (usage-metered)
4. GET /calls/{id} - Check call status
5. GET /billing/usage - Check usage and limits
"""

import asyncio
import contextlib
import logging

# Load environment variables from project root
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

# Import context builder
from context_builder.builder import build_contexts_for_submission
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import from shared schemas (single source of truth)
from shared.schemas import (
    CALL_JOB_TTL_SECONDS,
    CallGoal,
    CallJob,
    CallRequest,
    CallStatus,
    ContextInstance,
)

# Import routers for monetization features
from api.auth.routes import router as auth_router
from api.billing.routes import router as billing_router

# Import LiveKit dispatch
from api.dispatch import dispatch_voice_call
from api.referrals.routes import router as referrals_router

_project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
)
load_dotenv(os.path.join(_project_root, ".env.local"))
load_dotenv()  # Also try default .env

# Get Firecrawl API key for website scraping
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

logger = logging.getLogger("voice-agent-api")


# =============================================================================
# Concurrency-Safe In-Memory Store
# =============================================================================


class EphemeralStore:
    """Thread-safe ephemeral storage with TTL cleanup.

    All operations are protected by asyncio.Lock to prevent race conditions.
    """

    def __init__(self):
        self._call_jobs: dict[UUID, CallJob] = {}
        self._contexts: dict[UUID, ContextInstance] = {}
        self._ip_requests: dict[str, list[datetime]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_count: int = 0  # Track total cleanups for testing

    async def add_job(self, job: CallJob, context: ContextInstance) -> None:
        """Add a job and its context atomically."""
        async with self._lock:
            self._call_jobs[job.id] = job
            self._contexts[context.id] = context

    async def get_job(self, job_id: UUID) -> CallJob | None:
        """Get a job by ID, or None if not found/expired."""
        async with self._lock:
            return self._call_jobs.get(job_id)

    async def get_context(self, context_id: UUID) -> ContextInstance | None:
        """Get a context by ID, or None if not found."""
        async with self._lock:
            return self._contexts.get(context_id)

    async def count_jobs(self) -> int:
        """Count active jobs."""
        async with self._lock:
            return len(self._call_jobs)

    async def cleanup_expired(self) -> int:
        """Remove expired CallJob records. Returns count of removed records."""
        async with self._lock:
            expired_ids = [
                job_id for job_id, job in self._call_jobs.items() if job.is_expired()
            ]
            for job_id in expired_ids:
                job = self._call_jobs.pop(job_id, None)
                if job:
                    self._contexts.pop(job.context_id, None)
            self._cleanup_count += len(expired_ids)
            return len(expired_ids)

    async def check_rate_limit(
        self, ip: str, window_seconds: int, max_requests: int
    ) -> bool:
        """Check if IP is rate limited. Returns True if allowed, False if blocked."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            cutoff = now.timestamp() - window_seconds

            requests = self._ip_requests.get(ip, [])
            requests = [r for r in requests if r.timestamp() > cutoff]

            if len(requests) >= max_requests:
                return False

            requests.append(now)
            self._ip_requests[ip] = requests
            return True

    async def start_cleanup_task(self, interval_seconds: int = 60) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(
                self._periodic_cleanup(interval_seconds)
            )

    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            self._cleanup_task = None

    async def _periodic_cleanup(self, interval_seconds: int) -> None:
        """Periodically cleanup expired records."""
        while True:
            await asyncio.sleep(interval_seconds)
            removed = await self.cleanup_expired()
            if removed > 0:
                print(f"[cleanup] Removed {removed} expired call job(s)")

    @property
    def total_cleanups(self) -> int:
        """Total number of records cleaned up (for testing)."""
        return self._cleanup_count


# Global store instance
store = EphemeralStore()

# Rate limiting config
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 5

# E.164 phone number regex (basic validation)
E164_REGEX = re.compile(r"^\+[1-9]\d{6,14}$")


def validate_phone_e164(phone: str) -> bool:
    """Validate phone number is in E.164 format."""
    return bool(E164_REGEX.match(phone))


# =============================================================================
# App Lifecycle
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle - start/stop cleanup task."""
    # Startup: start background cleanup
    await store.start_cleanup_task(interval_seconds=60)
    yield
    # Shutdown: stop cleanup task
    await store.stop_cleanup_task()


app = FastAPI(
    title="Voice Agent MVP API",
    description="Stateless multi-tenant voice agent - no accounts, no persistence",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include monetization routers
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(referrals_router)


# =============================================================================
# Request/Response Models
# =============================================================================


class LeadCallResult(BaseModel):
    """Result of dispatching a single lead's call."""

    call_id: UUID
    context_id: UUID
    phone: str
    lead_name: str | None = None
    status: CallStatus
    expires_in_seconds: float
    message: str


class BatchCallResponse(BaseModel):
    """Response after dispatching calls for all leads."""

    calls: list[LeadCallResult]
    total: int
    dispatched: int
    failed: int


class CallStatusResponse(BaseModel):
    """Response for call status check."""

    call_id: UUID
    status: CallStatus
    phone: str
    sms_sent: bool
    error: str | None
    expires_in_seconds: float


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    active_calls: int
    ttl_seconds: int


# =============================================================================
# Endpoints
# =============================================================================


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    # Cleanup on health check too
    await store.cleanup_expired()

    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        active_calls=await store.count_jobs(),
        ttl_seconds=CALL_JOB_TTL_SECONDS,
    )


@app.post("/calls", response_model=BatchCallResponse)
async def create_call(request: CallRequest, http_request: Request):
    """Submit form and dispatch outbound calls for ALL leads.

    Validates:
    - Required consent checkbox
    - Phone numbers are E.164 format, no duplicates
    - Goal-specific required fields
    - IP rate limiting

    Returns:
    - Per-lead call results with call_id, status, TTL
    - Summary counts (total, dispatched, failed)
    """
    # Cleanup expired jobs first
    await store.cleanup_expired()

    # Validate consent (REQUIRED)
    if not request.consent:
        raise HTTPException(
            status_code=400,
            detail="Consent checkbox must be checked to proceed",
        )

    # Validate leads list
    if not request.leads:
        raise HTTPException(
            status_code=400,
            detail="At least one lead is required",
        )

    if len(request.leads) > 5:
        raise HTTPException(
            status_code=400,
            detail="Maximum 5 leads allowed per submission",
        )

    # Validate all phone formats (E.164) and check for duplicates
    seen_phones = set()
    for i, lead in enumerate(request.leads):
        if not validate_phone_e164(lead.phone):
            raise HTTPException(
                status_code=400,
                detail=f"Lead {i + 1}: Phone must be in E.164 format (e.g., +14155551234). Invalid: {lead.phone}",
            )
        if lead.phone in seen_phones:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate phone number: {lead.phone}",
            )
        seen_phones.add(lead.phone)

    # Validate goal-specific required fields
    if request.goal == CallGoal.BOOK_MEETING and not request.booking_link:
        raise HTTPException(
            status_code=400,
            detail="booking_link is required when goal is book_meeting",
        )

    if request.goal == CallGoal.CLOSE_SALE and not request.payment_link:
        raise HTTPException(
            status_code=400,
            detail="payment_link is required when goal is close_sale",
        )

    # Check rate limit
    client_ip = http_request.client.host if http_request.client else "unknown"
    allowed = await store.check_rate_limit(
        client_ip, RATE_LIMIT_WINDOW_SECONDS, RATE_LIMIT_MAX_REQUESTS
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS} seconds.",
        )

    # TODO: Validate Cloudflare Turnstile token
    # if request.turnstile_token:
    #     valid = await verify_turnstile(request.turnstile_token, client_ip)
    #     if not valid:
    #         raise HTTPException(status_code=400, detail="Invalid captcha token")

    # Build context for ALL leads (scrapes website once, builds per-lead context)
    contexts = build_contexts_for_submission(
        request, firecrawl_api_key=FIRECRAWL_API_KEY
    )

    # Dispatch a call for each lead
    call_results: list[LeadCallResult] = []
    dispatched_count = 0
    failed_count = 0

    for lead, context in zip(request.leads, contexts, strict=True):
        # Create ephemeral call job
        call_job = CallJob(
            context_id=context.id,
            phone=lead.phone,
            status=CallStatus.PENDING,
        )

        # Store atomically
        await store.add_job(call_job, context)

        # Dispatch the call via LiveKit SIP
        dispatch_result = await dispatch_voice_call(context)

        if dispatch_result.success:
            call_job.status = CallStatus.IN_PROGRESS
            call_job.started_at = datetime.now(timezone.utc)
            logger.info(
                f"Call dispatched for {lead.phone}: room={dispatch_result.room_name}"
            )
            message = "Call dispatched successfully"
            dispatched_count += 1
        else:
            call_job.status = CallStatus.FAILED
            call_job.error = dispatch_result.error
            logger.error(
                f"Call dispatch failed for {lead.phone}: {dispatch_result.error}"
            )
            message = f"Call dispatch failed: {dispatch_result.error}"
            failed_count += 1

        call_results.append(
            LeadCallResult(
                call_id=call_job.id,
                context_id=context.id,
                phone=lead.phone,
                lead_name=lead.name,
                status=call_job.status,
                expires_in_seconds=call_job.seconds_until_expiry(),
                message=message,
            )
        )

    return BatchCallResponse(
        calls=call_results,
        total=len(request.leads),
        dispatched=dispatched_count,
        failed=failed_count,
    )


@app.get("/calls/{call_id}", response_model=CallStatusResponse)
async def get_call_status(call_id: UUID):
    """Get call status by ID.

    Returns 404 if:
    - Call ID not found
    - Call has expired (past TTL)
    """
    # Cleanup expired jobs first
    await store.cleanup_expired()

    job = await store.get_job(call_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Call not found or expired",
        )

    return CallStatusResponse(
        call_id=job.id,
        status=job.status,
        phone=job.phone,
        sms_sent=job.sms_sent,
        error=job.error,
        expires_in_seconds=job.seconds_until_expiry(),
    )


@app.get("/contexts/{context_id}")
async def get_context(context_id: UUID):
    """Get context instance by ID (for debugging).

    Returns the full context that was/will be passed to the agent.
    """
    # Cleanup first
    await store.cleanup_expired()

    context = await store.get_context(context_id)
    if context is None:
        raise HTTPException(
            status_code=404,
            detail="Context not found or expired",
        )

    return context.model_dump(mode="json")


# =============================================================================
# Browser Participant Token Endpoint
# =============================================================================


class TokenRequest(BaseModel):
    """Request for a browser participant token."""

    room_name: str
    participant_name: str = "Test Caller"


class TokenResponse(BaseModel):
    """Response with LiveKit connection credentials."""

    server_url: str
    participant_token: str
    room_name: str


@app.post("/token", response_model=TokenResponse)
async def get_participant_token(request: TokenRequest):
    """Generate a LiveKit participant token for browser-based testing.

    This allows users to join the voice agent room from their browser
    to test the full conversation flow without needing SIP/phone calls.

    The token grants:
    - Room join permission
    - Audio publish permission (microphone)
    - Audio subscribe permission (hear the agent)
    """
    from datetime import timedelta

    from livekit import api as lk_api

    livekit_url = os.getenv("LIVEKIT_URL", "")
    api_key = os.getenv("LIVEKIT_API_KEY", "")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "")

    if not all([livekit_url, api_key, api_secret]):
        raise HTTPException(
            status_code=500,
            detail="LiveKit not configured. Check LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET",
        )

    # Create access token for browser participant
    token = lk_api.AccessToken(api_key, api_secret)
    token = token.with_identity(f"browser-{request.participant_name}")
    token = token.with_name(request.participant_name)
    token = token.with_grants(
        lk_api.VideoGrants(
            room_join=True,
            room=request.room_name,
            can_publish=True,
            can_subscribe=True,
        )
    )
    # Token expires in 10 minutes
    token = token.with_ttl(timedelta(minutes=10))

    jwt_token = token.to_jwt()

    logger.info(
        f"Generated browser token for {request.participant_name} in room {request.room_name}"
    )

    return TokenResponse(
        server_url=livekit_url,
        participant_token=jwt_token,
        room_name=request.room_name,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
