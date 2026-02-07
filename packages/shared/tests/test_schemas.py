"""Tests for shared schemas - Stateless Multi-Tenant MVP."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
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


class TestEnums:
    """Tests for enum values."""

    def test_call_goal_values(self):
        """All call goal options are available."""
        assert CallGoal.BOOK_MEETING.value == "book_meeting"
        assert CallGoal.QUALIFY_INTEREST.value == "qualify_interest"
        assert CallGoal.COLLECT_INFO.value == "collect_info"
        assert CallGoal.CLOSE_SALE.value == "close_sale"

    def test_call_status_values(self):
        """All call status options are available."""
        assert CallStatus.PENDING.value == "pending"
        assert CallStatus.IN_PROGRESS.value == "in_progress"
        assert CallStatus.COMPLETED.value == "completed"
        assert CallStatus.FAILED.value == "failed"

    def test_submission_status_values(self):
        """All submission status options are available."""
        assert SubmissionStatus.SUBMITTED.value == "submitted"
        assert SubmissionStatus.VALIDATED.value == "validated"
        assert SubmissionStatus.QUEUED.value == "queued"
        assert SubmissionStatus.IN_PROGRESS.value == "in_progress"
        assert SubmissionStatus.EMAILING.value == "emailing"
        assert SubmissionStatus.COMPLETE.value == "complete"
        assert SubmissionStatus.PARTIAL.value == "partial"
        assert SubmissionStatus.FAILED.value == "failed"
        assert SubmissionStatus.REJECTED.value == "rejected"
        assert SubmissionStatus.THROTTLED.value == "throttled"


class TestLead:
    """Tests for Lead schema."""

    def test_lead_with_phone_only(self):
        """Lead with only required phone field."""
        lead = Lead(phone="+14155551234")
        assert lead.phone == "+14155551234"
        assert lead.name is None
        assert lead.company is None
        assert lead.email is None
        assert lead.title is None

    def test_lead_with_all_fields(self):
        """Lead with all optional fields populated."""
        lead = Lead(
            phone="+14155551234",
            name="John Smith",
            company="Acme Corp",
            email="john@acme.com",
            title="VP of Sales",
        )
        assert lead.phone == "+14155551234"
        assert lead.name == "John Smith"
        assert lead.company == "Acme Corp"
        assert lead.email == "john@acme.com"
        assert lead.title == "VP of Sales"

    def test_lead_missing_phone_raises(self):
        """Lead without phone raises error."""
        with pytest.raises(ValueError):
            Lead(name="John Smith")


class TestCallRequest:
    """Tests for CallRequest (form submission) schema."""

    def test_minimal_call_request(self):
        """CallRequest with only required fields."""
        req = CallRequest(
            owner_email="owner@example.com",
            leads=[Lead(phone="+14155551234")],
            product="Enterprise CRM",
            goal=CallGoal.QUALIFY_INTEREST,
        )
        assert req.owner_email == "owner@example.com"
        assert len(req.leads) == 1
        assert req.leads[0].phone == "+14155551234"
        assert req.phone_count == 1
        assert req.phones == ["+14155551234"]
        assert req.product == "Enterprise CRM"
        assert req.goal == CallGoal.QUALIFY_INTEREST
        assert req.booking_link is None
        assert req.payment_link is None
        assert req.consent is False

    def test_call_request_with_multiple_leads(self):
        """CallRequest with multiple leads (different people)."""
        req = CallRequest(
            owner_email="owner@example.com",
            leads=[
                Lead(phone="+14155551234", name="John Smith", company="Acme Corp"),
                Lead(phone="+14155555678", name="Sarah Lee", company="Beta Inc"),
                Lead(phone="+14155559999", name="Mike Chen"),
            ],
            product="Enterprise CRM",
            goal=CallGoal.QUALIFY_INTEREST,
        )
        assert len(req.leads) == 3
        assert req.phone_count == 3
        assert req.phones == ["+14155551234", "+14155555678", "+14155559999"]
        # Each lead has their own name
        assert req.leads[0].name == "John Smith"
        assert req.leads[1].name == "Sarah Lee"
        assert req.leads[2].name == "Mike Chen"

    def test_call_request_book_meeting(self):
        """CallRequest for book_meeting goal."""
        req = CallRequest(
            owner_email="owner@example.com",
            leads=[Lead(phone="+14155551234", name="John")],
            product="Enterprise CRM",
            goal=CallGoal.BOOK_MEETING,
            booking_link="https://calendly.com/demo",
            consent=True,
        )
        assert req.goal == CallGoal.BOOK_MEETING
        assert req.booking_link == "https://calendly.com/demo"

    def test_call_request_close_sale(self):
        """CallRequest for close_sale goal."""
        req = CallRequest(
            owner_email="owner@example.com",
            leads=[Lead(phone="+14155551234", name="John")],
            product="Enterprise CRM",
            goal=CallGoal.CLOSE_SALE,
            payment_link="https://buy.stripe.com/xxx",
            pricing_summary="$99/month",
            urgency_hook="50% off this week only",
            consent=True,
        )
        assert req.goal == CallGoal.CLOSE_SALE
        assert req.payment_link == "https://buy.stripe.com/xxx"
        assert req.pricing_summary == "$99/month"
        assert req.urgency_hook == "50% off this week only"

    def test_call_request_with_website_and_context(self):
        """CallRequest with website URL and context."""
        req = CallRequest(
            owner_email="owner@example.com",
            leads=[Lead(phone="+14155551234")],
            product="Enterprise CRM",
            website_url="https://mycrm.com",
            context="$99/month, AI-powered analytics, 30-day free trial",
            goal=CallGoal.QUALIFY_INTEREST,
        )
        assert req.website_url == "https://mycrm.com"
        assert "AI-powered analytics" in req.context

    def test_call_request_missing_required_raises(self):
        """Missing required fields raises error."""
        with pytest.raises(ValueError):
            CallRequest(
                owner_email="owner@example.com",
                leads=[Lead(phone="+14155551234")],
            )  # Missing product and goal

    def test_call_request_idempotency_key(self):
        """CallRequest can have an idempotency key."""
        req = CallRequest(
            owner_email="owner@example.com",
            leads=[Lead(phone="+14155551234")],
            product="Enterprise CRM",
            goal=CallGoal.QUALIFY_INTEREST,
            idempotency_key="unique-key-123",
        )
        assert req.idempotency_key == "unique-key-123"

    def test_call_request_leads_have_per_person_data(self):
        """Each lead in a request has independent contact info."""
        req = CallRequest(
            owner_email="owner@example.com",
            leads=[
                Lead(
                    phone="+14155551234",
                    name="Alice",
                    company="TechCorp",
                    email="alice@techcorp.com",
                ),
                Lead(
                    phone="+14155555678",
                    name="Bob",
                    company="StartupXYZ",
                    email="bob@startupxyz.com",
                ),
            ],
            product="Enterprise CRM",
            goal=CallGoal.BOOK_MEETING,
            booking_link="https://calendly.com/demo",
        )
        # Each lead is a separate person with their own data
        assert req.leads[0].name != req.leads[1].name
        assert req.leads[0].company != req.leads[1].company
        assert req.leads[0].email != req.leads[1].email


class TestContextInstance:
    """Tests for ContextInstance schema."""

    def test_context_instance_minimal(self):
        """ContextInstance with required fields only."""
        ctx = ContextInstance(
            owner_email="owner@example.com",
            phone="+14155551234",
            product="Widget Pro",
            goal=CallGoal.QUALIFY_INTEREST,
            agent_instructions="You are a friendly sales assistant.",
            opening_line="Hi! I'm calling about Widget Pro.",
        )
        assert ctx.owner_email == "owner@example.com"
        assert ctx.phone == "+14155551234"
        assert ctx.product == "Widget Pro"
        assert ctx.agent_instructions == "You are a friendly sales assistant."
        assert ctx.opening_line == "Hi! I'm calling about Widget Pro."
        assert ctx.should_email_lead is False

    def test_context_instance_with_lead_details(self):
        """ContextInstance includes per-lead company and title."""
        ctx = ContextInstance(
            owner_email="owner@example.com",
            phone="+14155551234",
            name="John Smith",
            lead_company="Acme Corp",
            lead_title="VP of Sales",
            lead_email_preknown="john@acme.com",
            product="Widget Pro",
            goal=CallGoal.QUALIFY_INTEREST,
            agent_instructions="You are a friendly sales assistant.",
            opening_line="Hi John! I'm calling about Widget Pro.",
        )
        assert ctx.name == "John Smith"
        assert ctx.lead_company == "Acme Corp"
        assert ctx.lead_title == "VP of Sales"
        assert ctx.lead_email_preknown == "john@acme.com"

    def test_context_instance_book_meeting(self):
        """ContextInstance for book_meeting goal."""
        ctx = ContextInstance(
            owner_email="owner@example.com",
            phone="+14155551234",
            product="Enterprise Suite",
            goal=CallGoal.BOOK_MEETING,
            booking_link="https://cal.com/demo",
            agent_instructions="You are a professional sales rep...",
            opening_line="Good afternoon!",
            should_email_lead=True,
            lead_email_template="booking",
        )
        assert ctx.goal == CallGoal.BOOK_MEETING
        assert ctx.booking_link == "https://cal.com/demo"
        assert ctx.should_email_lead is True
        assert ctx.lead_email_template == "booking"

    def test_context_instance_close_sale(self):
        """ContextInstance for close_sale goal."""
        ctx = ContextInstance(
            owner_email="owner@example.com",
            phone="+14155551234",
            product="Premium Plan",
            goal=CallGoal.CLOSE_SALE,
            payment_link="https://buy.stripe.com/xxx",
            pricing_summary="$99/month",
            urgency_hook="Limited time offer",
            agent_instructions="You are an assertive closer...",
            opening_line="Hi, I'm calling about our Premium Plan.",
            objection_handlers={
                "too_expensive": "Let me share how our ROI typically...",
                "need_to_think": "I understand. What specific concerns do you have?",
            },
            should_email_lead=True,
            lead_email_template="payment",
        )
        assert ctx.goal == CallGoal.CLOSE_SALE
        assert ctx.payment_link == "https://buy.stripe.com/xxx"
        assert ctx.pricing_summary == "$99/month"
        assert ctx.urgency_hook == "Limited time offer"
        assert len(ctx.objection_handlers) == 2
        assert ctx.lead_email_template == "payment"

    def test_context_instance_has_uuid(self):
        """ContextInstance has UUID id."""
        ctx = ContextInstance(
            owner_email="owner@example.com",
            phone="+14155551234",
            product="Test",
            goal=CallGoal.QUALIFY_INTEREST,
            agent_instructions="Test",
            opening_line="Hi",
        )
        assert isinstance(ctx.id, UUID)

    def test_context_instance_has_created_at(self):
        """ContextInstance has created_at timestamp."""
        ctx = ContextInstance(
            owner_email="owner@example.com",
            phone="+14155551234",
            product="Test",
            goal=CallGoal.QUALIFY_INTEREST,
            agent_instructions="Test",
            opening_line="Hi",
        )
        assert ctx.created_at is not None
        assert isinstance(ctx.created_at, datetime)


class TestSubmission:
    """Tests for Submission (batch tracking) schema."""

    def test_submission_minimal(self):
        """Submission with required fields."""
        sub = Submission(
            owner_email="owner@example.com",
            leads=[Lead(phone="+14155551234")],
            goal=CallGoal.QUALIFY_INTEREST,
        )
        assert sub.owner_email == "owner@example.com"
        assert len(sub.leads) == 1
        assert sub.leads[0].phone == "+14155551234"
        assert sub.phones == ["+14155551234"]
        assert sub.goal == CallGoal.QUALIFY_INTEREST
        assert sub.status == SubmissionStatus.SUBMITTED
        assert sub.all_calls_done is False
        assert sub.successful_calls == 0

    def test_submission_multiple_leads(self):
        """Submission with multiple leads."""
        sub = Submission(
            owner_email="owner@example.com",
            leads=[
                Lead(phone="+14155551234", name="John"),
                Lead(phone="+14155555678", name="Sarah"),
                Lead(phone="+14155559999", name="Mike"),
            ],
            goal=CallGoal.CLOSE_SALE,
        )
        assert len(sub.leads) == 3
        assert sub.phones == ["+14155551234", "+14155555678", "+14155559999"]
        assert sub.all_calls_done is False

    def test_submission_status_transitions(self):
        """Submission status can be updated."""
        sub = Submission(
            owner_email="owner@example.com",
            leads=[Lead(phone="+14155551234")],
            goal=CallGoal.QUALIFY_INTEREST,
        )
        sub.status = SubmissionStatus.IN_PROGRESS
        assert sub.status == SubmissionStatus.IN_PROGRESS

    def test_submission_all_calls_done(self):
        """all_calls_done is True when results match leads count."""
        sub = Submission(
            owner_email="owner@example.com",
            leads=[Lead(phone="+14155551234")],
            goal=CallGoal.QUALIFY_INTEREST,
        )
        result = CallResult(
            submission_id=sub.id,
            phone="+14155551234",
            goal=CallGoal.QUALIFY_INTEREST,
            outcome="qualified",
        )
        sub.results.append(result)
        assert sub.all_calls_done is True

    def test_submission_successful_calls_count(self):
        """successful_calls counts results without errors."""
        sub = Submission(
            owner_email="owner@example.com",
            leads=[
                Lead(phone="+14155551234", name="John"),
                Lead(phone="+14155555678", name="Sarah"),
            ],
            goal=CallGoal.QUALIFY_INTEREST,
        )
        result1 = CallResult(
            submission_id=sub.id,
            phone="+14155551234",
            goal=CallGoal.QUALIFY_INTEREST,
            outcome="qualified",
        )
        result2 = CallResult(
            submission_id=sub.id,
            phone="+14155555678",
            goal=CallGoal.QUALIFY_INTEREST,
            outcome="error",
            error="No answer",
        )
        sub.results.extend([result1, result2])
        assert sub.successful_calls == 1

    def test_submission_idempotency_key(self):
        """Submission can have an idempotency key."""
        sub = Submission(
            owner_email="owner@example.com",
            leads=[Lead(phone="+14155551234")],
            goal=CallGoal.QUALIFY_INTEREST,
            idempotency_key="unique-submission-123",
        )
        assert sub.idempotency_key == "unique-submission-123"


class TestCallResult:
    """Tests for CallResult schema."""

    def test_call_result_minimal(self):
        """CallResult with required fields."""
        sub_id = uuid4()
        result = CallResult(
            submission_id=sub_id,
            phone="+14155551234",
            goal=CallGoal.QUALIFY_INTEREST,
        )
        assert result.submission_id == sub_id
        assert result.phone == "+14155551234"
        assert result.goal == CallGoal.QUALIFY_INTEREST
        assert result.outcome == "pending"
        assert result.error is None

    def test_call_result_qualified(self):
        """CallResult for qualified lead."""
        result = CallResult(
            submission_id=uuid4(),
            phone="+14155551234",
            goal=CallGoal.QUALIFY_INTEREST,
            outcome="qualified",
            duration_seconds=120,
            collected_data={"budget": "100k", "timeline": "Q1"},
        )
        assert result.outcome == "qualified"
        assert result.duration_seconds == 120
        assert result.collected_data["budget"] == "100k"

    def test_call_result_close_sale_committed(self):
        """CallResult for successful close_sale."""
        result = CallResult(
            submission_id=uuid4(),
            phone="+14155551234",
            goal=CallGoal.CLOSE_SALE,
            outcome="committed",
            lead_email="customer@example.com",
            lead_email_sent=True,
        )
        assert result.outcome == "committed"
        assert result.lead_email == "customer@example.com"
        assert result.lead_email_sent is True

    def test_call_result_close_sale_objection(self):
        """CallResult for close_sale with objection."""
        result = CallResult(
            submission_id=uuid4(),
            phone="+14155551234",
            goal=CallGoal.CLOSE_SALE,
            outcome="objection_price",
            objection_reason="Said it's too expensive compared to competitors",
        )
        assert result.outcome == "objection_price"
        assert result.objection_reason is not None
        assert "expensive" in result.objection_reason

    def test_call_result_no_answer(self):
        """CallResult for no answer."""
        result = CallResult(
            submission_id=uuid4(),
            phone="+14155551234",
            goal=CallGoal.BOOK_MEETING,
            outcome="no_answer",
            duration_seconds=0,
        )
        assert result.outcome == "no_answer"
        assert result.duration_seconds == 0

    def test_call_result_with_transcript(self):
        """CallResult with transcript and recording."""
        result = CallResult(
            submission_id=uuid4(),
            phone="+14155551234",
            goal=CallGoal.COLLECT_INFO,
            outcome="collected",
            transcript="Agent: Hello... Customer: Hi...",
            recording_url="https://livekit.cloud/recordings/abc123",
        )
        assert result.transcript is not None
        assert result.recording_url is not None

    def test_call_result_with_error(self):
        """CallResult with error."""
        result = CallResult(
            submission_id=uuid4(),
            phone="+14155551234",
            goal=CallGoal.QUALIFY_INTEREST,
            outcome="error",
            error="Connection failed",
        )
        assert result.outcome == "error"
        assert result.error == "Connection failed"


class TestCallJob:
    """Tests for CallJob (ephemeral) schema."""

    def test_call_job_minimal(self):
        """CallJob with required fields."""
        ctx_id = uuid4()
        job = CallJob(
            context_id=ctx_id,
            phone="+14155551234",
        )
        assert job.context_id == ctx_id
        assert job.phone == "+14155551234"
        assert job.status == CallStatus.PENDING
        assert job.sms_sent is False
        assert job.error is None

    def test_call_job_has_uuid(self):
        """CallJob has UUID id."""
        job = CallJob(
            context_id=uuid4(),
            phone="+14155551234",
        )
        assert isinstance(job.id, UUID)

    def test_call_job_status_transitions(self):
        """CallJob status can be set to any value."""
        job = CallJob(
            context_id=uuid4(),
            phone="+14155551234",
            status=CallStatus.IN_PROGRESS,
        )
        assert job.status == CallStatus.IN_PROGRESS

    def test_call_job_with_error(self):
        """CallJob can track errors."""
        job = CallJob(
            context_id=uuid4(),
            phone="+14155551234",
            status=CallStatus.FAILED,
            error="Phone number unreachable",
        )
        assert job.status == CallStatus.FAILED
        assert job.error == "Phone number unreachable"


class TestCallJobTTL:
    """Tests for CallJob TTL (Time-To-Live) enforcement."""

    def test_ttl_constant_is_10_minutes(self):
        """TTL constant is 600 seconds (10 minutes)."""
        assert CALL_JOB_TTL_SECONDS == 600

    def test_new_job_not_expired(self):
        """Newly created job is not expired."""
        job = CallJob(
            context_id=uuid4(),
            phone="+14155551234",
        )
        assert job.is_expired() is False

    def test_job_has_expires_at(self):
        """Job has expires_at computed field."""
        job = CallJob(
            context_id=uuid4(),
            phone="+14155551234",
        )
        assert job.expires_at is not None
        assert isinstance(job.expires_at, datetime)

    def test_expires_at_is_created_plus_ttl(self):
        """expires_at is created_at + TTL."""
        job = CallJob(
            context_id=uuid4(),
            phone="+14155551234",
        )
        expected = job.created_at + timedelta(seconds=CALL_JOB_TTL_SECONDS)
        assert job.expires_at == expected

    def test_old_job_is_expired(self):
        """Job created more than TTL seconds ago is expired."""
        old_time = datetime.now(timezone.utc) - timedelta(
            seconds=CALL_JOB_TTL_SECONDS + 1
        )
        job = CallJob(
            context_id=uuid4(),
            phone="+14155551234",
            created_at=old_time,
        )
        assert job.is_expired() is True

    def test_seconds_until_expiry_positive_for_new_job(self):
        """New job has positive seconds until expiry."""
        job = CallJob(
            context_id=uuid4(),
            phone="+14155551234",
        )
        # Should be close to 600 seconds
        assert job.seconds_until_expiry() > 599
        assert job.seconds_until_expiry() <= 600

    def test_seconds_until_expiry_negative_for_expired_job(self):
        """Expired job has negative seconds until expiry."""
        old_time = datetime.now(timezone.utc) - timedelta(
            seconds=CALL_JOB_TTL_SECONDS + 60
        )
        job = CallJob(
            context_id=uuid4(),
            phone="+14155551234",
            created_at=old_time,
        )
        assert job.seconds_until_expiry() < 0


class TestSchemaContract:
    """Contract tests to prevent silent breaking changes."""

    def test_call_goal_values_contract(self):
        """CallGoal enum values are stable."""
        assert {e.value for e in CallGoal} == {
            "book_meeting",
            "qualify_interest",
            "collect_info",
            "close_sale",
        }

    def test_submission_status_values_contract(self):
        """SubmissionStatus enum values are stable."""
        expected = {
            "submitted",
            "validated",
            "queued",
            "in_progress",
            "emailing",
            "complete",
            "partial",
            "failed",
            "rejected",
            "throttled",
        }
        assert {e.value for e in SubmissionStatus} == expected

    def test_call_request_required_fields(self):
        """CallRequest has expected required fields."""
        schema = CallRequest.model_json_schema()
        required = schema.get("required", [])
        assert "owner_email" in required
        assert "leads" in required
        assert "product" in required
        assert "goal" in required

    def test_context_instance_required_fields(self):
        """ContextInstance has expected required fields."""
        schema = ContextInstance.model_json_schema()
        required = schema.get("required", [])
        assert "owner_email" in required
        assert "phone" in required
        assert "product" in required
        assert "goal" in required
        assert "agent_instructions" in required
        assert "opening_line" in required

    def test_submission_required_fields(self):
        """Submission has expected required fields."""
        schema = Submission.model_json_schema()
        required = schema.get("required", [])
        assert "owner_email" in required
        assert "leads" in required
        assert "goal" in required

    def test_call_result_required_fields(self):
        """CallResult has expected required fields."""
        schema = CallResult.model_json_schema()
        required = schema.get("required", [])
        assert "submission_id" in required
        assert "phone" in required
        assert "goal" in required

    def test_call_job_has_ttl_methods(self):
        """CallJob has TTL-related methods and computed field."""
        job = CallJob(
            context_id=uuid4(),
            phone="+14155551234",
        )
        # Verify computed field works
        assert hasattr(job, "expires_at")
        assert job.expires_at is not None

        # Verify methods exist and work
        assert hasattr(job, "is_expired")
        assert hasattr(job, "seconds_until_expiry")
        assert callable(job.is_expired)
        assert callable(job.seconds_until_expiry)

    def test_lead_required_fields(self):
        """Lead has phone as required field."""
        schema = Lead.model_json_schema()
        required = schema.get("required", [])
        assert "phone" in required
