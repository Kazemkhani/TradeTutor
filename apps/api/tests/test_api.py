"""API integration tests for Stateless Multi-Tenant Voice Agent MVP."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from api.main import EphemeralStore, app, store, validate_phone_e164


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
async def reset_store():
    """Reset the store before each test."""
    # Clear all data
    async with store._lock:
        store._call_jobs.clear()
        store._contexts.clear()
        store._ip_requests.clear()
        store._cleanup_count = 0
    yield


def make_valid_request():
    """Create a valid CallRequest payload with leads."""
    return {
        "owner_email": "owner@example.com",
        "leads": [{"phone": "+14155551234"}],
        "product": "Test Product",
        "goal": "qualify_interest",
        "consent": True,
    }


def make_book_meeting_request():
    """Create a valid book_meeting request."""
    return {
        "owner_email": "owner@example.com",
        "leads": [{"phone": "+14155551234"}],
        "product": "Test Product",
        "goal": "book_meeting",
        "booking_link": "https://calendly.com/test/30min",
        "consent": True,
    }


def make_close_sale_request():
    """Create a valid close_sale request."""
    return {
        "owner_email": "owner@example.com",
        "leads": [{"phone": "+14155551234"}],
        "product": "Premium CRM",
        "goal": "close_sale",
        "payment_link": "https://buy.stripe.com/test",
        "pricing_summary": "$99/month",
        "urgency_hook": "50% off this week only",
        "consent": True,
    }


# =============================================================================
# Phone Validation Tests (G)
# =============================================================================


class TestPhoneValidation:
    """Tests for E.164 phone number validation."""

    def test_valid_e164_us(self):
        """Valid US phone number."""
        assert validate_phone_e164("+14155551234") is True

    def test_valid_e164_uk(self):
        """Valid UK phone number."""
        assert validate_phone_e164("+442071234567") is True

    def test_valid_e164_short(self):
        """Valid short international number."""
        assert validate_phone_e164("+1234567") is True

    def test_invalid_no_plus(self):
        """Invalid - missing plus sign."""
        assert validate_phone_e164("14155551234") is False

    def test_invalid_too_short(self):
        """Invalid - too short."""
        assert validate_phone_e164("+12345") is False

    def test_invalid_letters(self):
        """Invalid - contains letters."""
        assert validate_phone_e164("+1415555ABCD") is False

    def test_invalid_spaces(self):
        """Invalid - contains spaces."""
        assert validate_phone_e164("+1 415 555 1234") is False

    def test_invalid_zero_start(self):
        """Invalid - starts with zero after plus."""
        assert validate_phone_e164("+0123456789") is False


class TestAPIPhoneValidation:
    """Tests for phone validation in API endpoint."""

    def test_create_call_rejects_invalid_phone(self, client):
        """API rejects invalid phone format."""
        payload = make_valid_request()
        payload["leads"] = [{"phone": "14155551234"}]  # Missing +

        response = client.post("/calls", json=payload)

        assert response.status_code == 400
        assert "E.164" in response.json()["detail"]

    def test_create_call_accepts_valid_phone(self, client):
        """API accepts valid E.164 phone."""
        payload = make_valid_request()

        response = client.post("/calls", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "calls" in data
        assert len(data["calls"]) == 1

    def test_create_call_rejects_empty_leads_list(self, client):
        """API rejects empty leads list."""
        payload = make_valid_request()
        payload["leads"] = []

        response = client.post("/calls", json=payload)

        assert response.status_code == 400
        assert "At least one lead" in response.json()["detail"]

    def test_create_call_rejects_too_many_leads(self, client):
        """API rejects more than 5 leads."""
        payload = make_valid_request()
        payload["leads"] = [
            {"phone": "+14155551234"},
            {"phone": "+14155551235"},
            {"phone": "+14155551236"},
            {"phone": "+14155551237"},
            {"phone": "+14155551238"},
            {"phone": "+14155551239"},  # 6th lead
        ]

        response = client.post("/calls", json=payload)

        assert response.status_code == 400
        assert "Maximum 5" in response.json()["detail"]

    def test_create_call_accepts_multiple_valid_leads(self, client):
        """API accepts up to 5 valid leads."""
        payload = make_valid_request()
        payload["leads"] = [
            {"phone": "+14155551234", "name": "Alice"},
            {"phone": "+14155551235", "name": "Bob"},
            {"phone": "+14155551236", "name": "Charlie"},
        ]

        response = client.post("/calls", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["calls"]) == 3

    def test_create_call_rejects_duplicate_phones(self, client):
        """API rejects duplicate phone numbers."""
        payload = make_valid_request()
        payload["leads"] = [
            {"phone": "+14155551234", "name": "Alice"},
            {"phone": "+14155551234", "name": "Bob"},  # Same phone
        ]

        response = client.post("/calls", json=payload)

        assert response.status_code == 400
        assert "Duplicate phone" in response.json()["detail"]


# =============================================================================
# Goal-Specific Validation Tests
# =============================================================================


class TestGoalValidation:
    """Tests for goal-specific field validation."""

    def test_book_meeting_requires_booking_link(self, client):
        """book_meeting goal requires booking_link."""
        payload = make_valid_request()
        payload["goal"] = "book_meeting"
        # No booking_link provided

        response = client.post("/calls", json=payload)

        assert response.status_code == 400
        assert "booking_link is required" in response.json()["detail"]

    def test_book_meeting_accepts_with_booking_link(self, client):
        """book_meeting goal accepts request with booking_link."""
        payload = make_book_meeting_request()

        response = client.post("/calls", json=payload)

        assert response.status_code == 200

    def test_close_sale_requires_payment_link(self, client):
        """close_sale goal requires payment_link."""
        payload = make_valid_request()
        payload["goal"] = "close_sale"
        # No payment_link provided

        response = client.post("/calls", json=payload)

        assert response.status_code == 400
        assert "payment_link is required" in response.json()["detail"]

    def test_close_sale_accepts_with_payment_link(self, client):
        """close_sale goal accepts request with payment_link."""
        payload = make_close_sale_request()

        response = client.post("/calls", json=payload)

        assert response.status_code == 200

    def test_qualify_interest_no_extra_fields_required(self, client):
        """qualify_interest goal doesn't require extra fields."""
        payload = make_valid_request()
        payload["goal"] = "qualify_interest"

        response = client.post("/calls", json=payload)

        assert response.status_code == 200

    def test_collect_info_no_extra_fields_required(self, client):
        """collect_info goal doesn't require extra fields."""
        payload = make_valid_request()
        payload["goal"] = "collect_info"

        response = client.post("/calls", json=payload)

        assert response.status_code == 200


# =============================================================================
# Consent Validation Tests (G)
# =============================================================================


class TestConsentValidation:
    """Tests for consent checkbox requirement."""

    def test_create_call_rejects_without_consent(self, client):
        """API rejects request without consent."""
        payload = make_valid_request()
        payload["consent"] = False

        response = client.post("/calls", json=payload)

        assert response.status_code == 400
        assert "Consent" in response.json()["detail"]

    def test_create_call_rejects_missing_consent(self, client):
        """API rejects request with missing consent (defaults to False)."""
        payload = make_valid_request()
        del payload["consent"]

        response = client.post("/calls", json=payload)

        assert response.status_code == 400
        assert "Consent" in response.json()["detail"]

    def test_create_call_accepts_with_consent(self, client):
        """API accepts request with consent=True."""
        payload = make_valid_request()
        payload["consent"] = True

        response = client.post("/calls", json=payload)

        assert response.status_code == 200


# =============================================================================
# Batch Response Tests
# =============================================================================


class TestBatchResponse:
    """Tests for batch call response format."""

    def test_single_lead_returns_batch_response(self, client):
        """Single lead still returns batch response format."""
        payload = make_valid_request()

        response = client.post("/calls", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "calls" in data
        assert "total" in data
        assert "dispatched" in data
        assert "failed" in data
        assert data["total"] == 1
        assert len(data["calls"]) == 1

    def test_single_lead_call_result_shape(self, client):
        """Each call result has the expected fields."""
        payload = make_valid_request()

        response = client.post("/calls", json=payload)

        data = response.json()
        call = data["calls"][0]
        assert "call_id" in call
        assert "context_id" in call
        assert "phone" in call
        assert "status" in call
        assert "expires_in_seconds" in call
        assert "message" in call
        assert call["phone"] == "+14155551234"

    def test_multiple_leads_all_dispatched(self, client):
        """Multiple leads each get their own call dispatch."""
        payload = make_valid_request()
        payload["leads"] = [
            {"phone": "+14155551234", "name": "Alice"},
            {"phone": "+14155551235", "name": "Bob"},
            {"phone": "+14155551236", "name": "Charlie"},
        ]

        response = client.post("/calls", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["calls"]) == 3

        # Each call has the correct phone
        phones = [c["phone"] for c in data["calls"]]
        assert "+14155551234" in phones
        assert "+14155551235" in phones
        assert "+14155551236" in phones

        # Each call has a unique call_id and context_id
        call_ids = [c["call_id"] for c in data["calls"]]
        assert len(set(call_ids)) == 3
        context_ids = [c["context_id"] for c in data["calls"]]
        assert len(set(context_ids)) == 3

    def test_lead_names_in_response(self, client):
        """Lead names are included in call results."""
        payload = make_valid_request()
        payload["leads"] = [
            {"phone": "+14155551234", "name": "Alice"},
            {"phone": "+14155551235"},  # No name
        ]

        response = client.post("/calls", json=payload)

        data = response.json()
        assert data["calls"][0]["lead_name"] == "Alice"
        assert data["calls"][1]["lead_name"] is None


# =============================================================================
# API Contract Smoke Tests (F)
# =============================================================================


class TestAPIContract:
    """API contract smoke tests."""

    def test_create_call_returns_batch(self, client):
        """POST /calls returns batch response with calls array."""
        payload = make_valid_request()

        response = client.post("/calls", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "calls" in data
        assert data["total"] == 1
        call = data["calls"][0]
        assert "call_id" in call
        assert "context_id" in call
        assert call["expires_in_seconds"] > 0

    def test_get_context_returns_valid_shape(self, client):
        """GET /contexts/{id} returns valid ContextInstance shape."""
        # Create a call first
        payload = make_valid_request()
        create_response = client.post("/calls", json=payload)
        context_id = create_response.json()["calls"][0]["context_id"]

        # Get context
        response = client.get(f"/contexts/{context_id}")

        assert response.status_code == 200
        data = response.json()

        # Verify ContextInstance shape
        assert "phone" in data
        assert "product" in data
        assert "goal" in data
        assert "owner_email" in data
        assert "agent_instructions" in data
        assert "opening_line" in data
        assert data["phone"] == "+14155551234"
        assert data["owner_email"] == "owner@example.com"

    def test_get_context_for_close_sale(self, client):
        """GET /contexts/{id} returns close_sale-specific fields."""
        payload = make_close_sale_request()
        create_response = client.post("/calls", json=payload)
        context_id = create_response.json()["calls"][0]["context_id"]

        response = client.get(f"/contexts/{context_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["goal"] == "close_sale"
        assert data["payment_link"] == "https://buy.stripe.com/test"
        assert data["pricing_summary"] == "$99/month"
        assert data["urgency_hook"] == "50% off this week only"
        assert data["should_email_lead"] is True
        assert data["lead_email_template"] == "payment"

    def test_get_context_for_book_meeting(self, client):
        """GET /contexts/{id} returns book_meeting-specific fields."""
        payload = make_book_meeting_request()
        create_response = client.post("/calls", json=payload)
        context_id = create_response.json()["calls"][0]["context_id"]

        response = client.get(f"/contexts/{context_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["goal"] == "book_meeting"
        assert data["booking_link"] == "https://calendly.com/test/30min"
        assert data["should_email_lead"] is True
        assert data["lead_email_template"] == "booking"

    def test_get_call_status_after_create(self, client):
        """GET /calls/{id} returns valid status after create."""
        payload = make_valid_request()
        create_response = client.post("/calls", json=payload)
        call_id = create_response.json()["calls"][0]["call_id"]

        response = client.get(f"/calls/{call_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["phone"] == "+14155551234"
        assert data["sms_sent"] is False

    def test_get_context_for_each_lead(self, client):
        """Each lead gets a unique context with personalized data."""
        payload = make_valid_request()
        payload["leads"] = [
            {"phone": "+14155551234", "name": "Alice", "company": "TechCorp"},
            {"phone": "+14155551235", "name": "Bob", "company": "StartupXYZ"},
        ]

        create_response = client.post("/calls", json=payload)
        calls = create_response.json()["calls"]

        # Get context for first lead
        ctx1 = client.get(f"/contexts/{calls[0]['context_id']}").json()
        assert ctx1["name"] == "Alice"
        assert ctx1["lead_company"] == "TechCorp"
        assert "Alice" in ctx1["opening_line"]

        # Get context for second lead
        ctx2 = client.get(f"/contexts/{calls[1]['context_id']}").json()
        assert ctx2["name"] == "Bob"
        assert ctx2["lead_company"] == "StartupXYZ"
        assert "Bob" in ctx2["opening_line"]

    def test_health_check(self, client):
        """GET /health returns valid response."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["ttl_seconds"] == 600


# =============================================================================
# TTL Cleanup Tests (B)
# =============================================================================


class TestTTLCleanup:
    """Tests for TTL-based cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired_jobs(self):
        """Cleanup removes expired jobs."""
        test_store = EphemeralStore()

        from shared.schemas import CallGoal, CallJob, ContextInstance

        old_time = datetime.now(timezone.utc) - timedelta(minutes=11)
        context = ContextInstance(
            owner_email="test@example.com",
            phone="+14155551234",
            product="Test",
            goal=CallGoal.QUALIFY_INTEREST,
            agent_instructions="Test",
            opening_line="Hi",
        )
        job = CallJob(
            context_id=context.id,
            phone="+14155551234",
            created_at=old_time,
        )

        await test_store.add_job(job, context)
        assert await test_store.count_jobs() == 1

        removed = await test_store.cleanup_expired()

        assert removed == 1
        assert await test_store.count_jobs() == 0
        assert test_store.total_cleanups == 1

    @pytest.mark.asyncio
    async def test_cleanup_keeps_valid_jobs(self):
        """Cleanup keeps non-expired jobs."""
        test_store = EphemeralStore()

        from shared.schemas import CallGoal, CallJob, ContextInstance

        context = ContextInstance(
            owner_email="test@example.com",
            phone="+14155551234",
            product="Test",
            goal=CallGoal.QUALIFY_INTEREST,
            agent_instructions="Test",
            opening_line="Hi",
        )
        job = CallJob(
            context_id=context.id,
            phone="+14155551234",
        )

        await test_store.add_job(job, context)

        removed = await test_store.cleanup_expired()

        assert removed == 0
        assert await test_store.count_jobs() == 1

    def test_expired_call_returns_404(self, client):
        """GET returns 404 for expired call after cleanup."""
        from uuid import UUID

        payload = make_valid_request()
        create_response = client.post("/calls", json=payload)
        call_id_str = create_response.json()["calls"][0]["call_id"]
        call_id = UUID(call_id_str)

        # Manually expire the job by patching created_at
        import asyncio

        async def expire_job():
            async with store._lock:
                job = store._call_jobs.get(call_id)
                if job:
                    from shared.schemas import CallJob

                    expired_job = CallJob(
                        id=job.id,
                        context_id=job.context_id,
                        phone=job.phone,
                        created_at=datetime.now(timezone.utc) - timedelta(minutes=11),
                    )
                    store._call_jobs[call_id] = expired_job

        asyncio.get_event_loop().run_until_complete(expire_job())

        response = client.get(f"/calls/{call_id_str}")
        assert response.status_code == 404


# =============================================================================
# Concurrency Safety Tests (C)
# =============================================================================


class TestConcurrencySafety:
    """Tests for concurrency safety with asyncio locks."""

    @pytest.mark.asyncio
    async def test_concurrent_add_and_cleanup(self):
        """Concurrent add and cleanup don't cause race conditions."""
        test_store = EphemeralStore()

        from shared.schemas import CallGoal, CallJob, ContextInstance

        async def add_job(i: int):
            context = ContextInstance(
                owner_email=f"test{i}@example.com",
                phone=f"+1415555{i:04d}",
                product=f"Product {i}",
                goal=CallGoal.QUALIFY_INTEREST,
                agent_instructions="Test",
                opening_line="Hi",
            )
            job = CallJob(
                context_id=context.id,
                phone=f"+1415555{i:04d}",
            )
            await test_store.add_job(job, context)
            return job.id

        async def cleanup_loop():
            for _ in range(10):
                await test_store.cleanup_expired()
                await asyncio.sleep(0.001)

        # Run adds and cleanups concurrently
        add_tasks = [add_job(i) for i in range(20)]
        cleanup_task = asyncio.create_task(cleanup_loop())

        job_ids = await asyncio.gather(*add_tasks)
        await cleanup_task

        # All jobs should still exist (none expired)
        count = await test_store.count_jobs()
        assert count == 20

        # Verify we can get all jobs
        for job_id in job_ids:
            job = await test_store.get_job(job_id)
            assert job is not None

    @pytest.mark.asyncio
    async def test_concurrent_reads_and_writes(self):
        """Concurrent reads and writes are safe."""
        test_store = EphemeralStore()

        from shared.schemas import CallGoal, CallJob, ContextInstance

        # First add a job
        context = ContextInstance(
            owner_email="test@example.com",
            phone="+14155551234",
            product="Test",
            goal=CallGoal.QUALIFY_INTEREST,
            agent_instructions="Test",
            opening_line="Hi",
        )
        job = CallJob(
            context_id=context.id,
            phone="+14155551234",
        )
        await test_store.add_job(job, context)

        errors = []

        async def read_job():
            try:
                for _ in range(50):
                    result = await test_store.get_job(job.id)
                    if result is None:
                        errors.append("Job unexpectedly None during read")
                    await asyncio.sleep(0.001)
            except Exception as e:
                errors.append(str(e))

        async def add_more_jobs():
            try:
                for i in range(10):
                    ctx = ContextInstance(
                        owner_email=f"test{i}@example.com",
                        phone=f"+1415555{i:04d}",
                        product=f"Product {i}",
                        goal=CallGoal.QUALIFY_INTEREST,
                        agent_instructions="Test",
                        opening_line="Hi",
                    )
                    j = CallJob(context_id=ctx.id, phone=f"+1415555{i:04d}")
                    await test_store.add_job(j, ctx)
                    await asyncio.sleep(0.001)
            except Exception as e:
                errors.append(str(e))

        # Run concurrently
        await asyncio.gather(
            read_job(),
            add_more_jobs(),
            test_store.cleanup_expired(),
        )

        assert len(errors) == 0, f"Errors during concurrent access: {errors}"
