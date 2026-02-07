"""Tests for the email module."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from shared.email import (
    EmailConfig,
    EmailSender,
    _build_booking_link_html,
    _build_owner_summary_html,
    _build_payment_link_html,
    _format_outcome,
    send_post_call_emails,
)
from shared.schemas import CallGoal, CallResult, ContextInstance

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_context() -> ContextInstance:
    """Create a sample context instance for testing."""
    return ContextInstance(
        owner_email="owner@example.com",
        phone="+14155551234",
        name="John Doe",
        product="Test Product",
        goal=CallGoal.CLOSE_SALE,
        booking_link="https://calendly.com/test/30min",
        payment_link="https://buy.stripe.com/test",
        pricing_summary="$99/month, 30-day free trial",
        urgency_hook="50% off this week only",
        agent_instructions="Test instructions",
        opening_line="Hello!",
        qualification_questions=["Question 1"],
        objection_handlers={"price": "Value response"},
        closing_script="Thank you!",
        should_email_lead=True,
        lead_email_template="payment",
    )


@pytest.fixture
def sample_call_result(sample_context: ContextInstance) -> CallResult:
    """Create a sample call result for testing."""
    return CallResult(
        call_id=uuid4(),
        submission_id=sample_context.id,
        phone=sample_context.phone,
        duration_seconds=120,
        goal=CallGoal.CLOSE_SALE,
        outcome="committed",
        objection_reason=None,
        collected_data={"company_size": "10-50 employees"},
        lead_email="lead@example.com",
        transcript="Agent: Hello!\nLead: Hi there!",
        recording_url="https://livekit.io/recording/test",
        lead_email_sent=False,
        error=None,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )


# =============================================================================
# Test EmailConfig
# =============================================================================


class TestEmailConfig:
    """Tests for EmailConfig."""

    def test_from_env_with_values(self, monkeypatch):
        """Test loading config from environment variables."""
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
        monkeypatch.setenv("RESEND_FROM_EMAIL", "noreply@test.com")
        monkeypatch.setenv("RESEND_FROM_NAME", "Test Agent")

        config = EmailConfig.from_env()

        assert config.api_key == "re_test_key"
        assert config.from_email == "noreply@test.com"
        assert config.from_name == "Test Agent"

    def test_from_env_with_defaults(self, monkeypatch):
        """Test loading config with default values."""
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        monkeypatch.delenv("RESEND_FROM_EMAIL", raising=False)
        monkeypatch.delenv("RESEND_FROM_NAME", raising=False)

        config = EmailConfig.from_env()

        assert config.api_key == ""
        assert config.from_email == "noreply@example.com"
        assert config.from_name == "Voice Agent"


# =============================================================================
# Test Outcome Formatting
# =============================================================================


class TestFormatOutcome:
    """Tests for outcome formatting."""

    @pytest.mark.parametrize(
        "outcome,expected",
        [
            ("booked", "Meeting Booked"),
            ("committed", "Sale Committed"),
            ("soft_commitment", "Soft Commitment (Follow-up Needed)"),
            ("objection_price", "Objection: Price"),
            ("no_answer", "No Answer"),
            ("qualified", "Lead Qualified"),
            ("collected", "Information Collected"),
            ("unknown_outcome", "Unknown Outcome"),  # Fallback
        ],
    )
    def test_format_outcome(self, outcome, expected):
        """Test outcome formatting for various values."""
        result = _format_outcome(outcome, CallGoal.CLOSE_SALE)
        assert result == expected


# =============================================================================
# Test HTML Template Builders
# =============================================================================


class TestOwnerSummaryHtml:
    """Tests for owner summary HTML builder."""

    def test_includes_call_details(self, sample_context, sample_call_result):
        """Test that owner summary includes basic call details."""
        html = _build_owner_summary_html(sample_context, sample_call_result)

        assert sample_context.product in html
        assert sample_call_result.phone in html
        assert "Close Sale" in html  # Goal display
        assert "Sale Committed" in html  # Outcome
        assert "120 seconds" in html  # Duration

    def test_includes_collected_data(self, sample_context, sample_call_result):
        """Test that collected data is shown."""
        html = _build_owner_summary_html(sample_context, sample_call_result)

        assert "Collected Information" in html
        assert "10-50 employees" in html

    def test_includes_lead_email(self, sample_context, sample_call_result):
        """Test that lead email is shown when collected."""
        html = _build_owner_summary_html(sample_context, sample_call_result)

        assert "lead@example.com" in html

    def test_includes_transcript(self, sample_context, sample_call_result):
        """Test that transcript is included."""
        html = _build_owner_summary_html(sample_context, sample_call_result)

        assert "Call Transcript" in html
        assert "Hello!" in html
        assert "Hi there!" in html

    def test_includes_recording_url(self, sample_context, sample_call_result):
        """Test that recording URL is included."""
        html = _build_owner_summary_html(sample_context, sample_call_result)

        assert "Listen to Recording" in html
        assert sample_call_result.recording_url in html

    def test_shows_objection_reason(self, sample_context, sample_call_result):
        """Test that objection reason is shown when present."""
        sample_call_result.outcome = "objection_price"
        sample_call_result.objection_reason = "Too expensive for their budget"

        html = _build_owner_summary_html(sample_context, sample_call_result)

        assert "Objection Reason" in html
        assert "Too expensive for their budget" in html


class TestBookingLinkHtml:
    """Tests for booking link HTML builder."""

    def test_includes_booking_link(self, sample_context):
        """Test that booking link is included."""
        sample_context.goal = CallGoal.BOOK_MEETING
        html = _build_booking_link_html(sample_context, "lead@example.com")

        assert sample_context.booking_link in html
        assert "Book Your Demo" in html

    def test_includes_lead_name(self, sample_context):
        """Test that lead name is personalized."""
        html = _build_booking_link_html(sample_context, "lead@example.com")

        assert "John Doe" in html  # name from context

    def test_fallback_greeting_without_name(self, sample_context):
        """Test fallback greeting when no name provided."""
        sample_context.name = None
        html = _build_booking_link_html(sample_context, "lead@example.com")

        assert "Hi there" in html


class TestPaymentLinkHtml:
    """Tests for payment link HTML builder."""

    def test_includes_payment_link(self, sample_context):
        """Test that payment link is included."""
        html = _build_payment_link_html(sample_context, "lead@example.com")

        assert sample_context.payment_link in html
        assert "Complete Purchase" in html

    def test_includes_pricing_summary(self, sample_context):
        """Test that pricing summary is shown when provided."""
        html = _build_payment_link_html(sample_context, "lead@example.com")

        assert "Pricing Details" in html
        assert sample_context.pricing_summary in html

    def test_includes_urgency_hook(self, sample_context):
        """Test that urgency hook is shown when provided."""
        html = _build_payment_link_html(sample_context, "lead@example.com")

        assert "Limited Time" in html
        assert sample_context.urgency_hook in html

    def test_no_pricing_section_without_summary(self, sample_context):
        """Test that pricing section is omitted without pricing_summary."""
        sample_context.pricing_summary = None
        html = _build_payment_link_html(sample_context, "lead@example.com")

        assert "Pricing Details" not in html


# =============================================================================
# Test EmailSender
# =============================================================================


class TestEmailSender:
    """Tests for EmailSender."""

    @pytest.mark.asyncio
    async def test_send_owner_summary_without_api_key(
        self, sample_context, sample_call_result
    ):
        """Test that sending fails gracefully without API key."""
        config = EmailConfig(api_key="", from_email="test@test.com")
        sender = EmailSender(config)

        result = await sender.send_owner_summary(sample_context, sample_call_result)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_booking_link_without_booking_link(self, sample_context):
        """Test that sending fails when booking_link is missing."""
        sample_context.booking_link = None
        config = EmailConfig(api_key="re_test", from_email="test@test.com")
        sender = EmailSender(config)

        result = await sender.send_booking_link(sample_context, "lead@example.com")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_payment_link_without_payment_link(self, sample_context):
        """Test that sending fails when payment_link is missing."""
        sample_context.payment_link = None
        config = EmailConfig(api_key="re_test", from_email="test@test.com")
        sender = EmailSender(config)

        result = await sender.send_payment_link(sample_context, "lead@example.com")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_owner_summary_success(
        self, sample_context, sample_call_result, monkeypatch
    ):
        """Test successful email sending."""
        mock_send = MagicMock(return_value={"id": "email_123"})
        monkeypatch.setattr("resend.Emails.send", mock_send)

        config = EmailConfig(api_key="re_test_key", from_email="test@test.com")
        sender = EmailSender(config)

        result = await sender.send_owner_summary(sample_context, sample_call_result)

        assert result is True
        mock_send.assert_called_once()

        # Verify email params
        call_args = mock_send.call_args[0][0]
        assert sample_context.owner_email in call_args["to"]
        assert "Sale Committed" in call_args["subject"]

    @pytest.mark.asyncio
    async def test_send_booking_link_success(self, sample_context, monkeypatch):
        """Test successful booking link email."""
        mock_send = MagicMock(return_value={"id": "email_456"})
        monkeypatch.setattr("resend.Emails.send", mock_send)

        sample_context.goal = CallGoal.BOOK_MEETING
        config = EmailConfig(api_key="re_test_key", from_email="test@test.com")
        sender = EmailSender(config)

        result = await sender.send_booking_link(sample_context, "lead@example.com")

        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_payment_link_success(self, sample_context, monkeypatch):
        """Test successful payment link email."""
        mock_send = MagicMock(return_value={"id": "email_789"})
        monkeypatch.setattr("resend.Emails.send", mock_send)

        config = EmailConfig(api_key="re_test_key", from_email="test@test.com")
        sender = EmailSender(config)

        result = await sender.send_payment_link(sample_context, "lead@example.com")

        assert result is True
        mock_send.assert_called_once()


# =============================================================================
# Test send_post_call_emails
# =============================================================================


class TestSendPostCallEmails:
    """Tests for the convenience function send_post_call_emails."""

    @pytest.mark.asyncio
    async def test_sends_owner_email_for_all_goals(
        self, sample_context, sample_call_result, monkeypatch
    ):
        """Test that owner summary is always sent."""
        mock_send = MagicMock(return_value={"id": "email_123"})
        monkeypatch.setattr("resend.Emails.send", mock_send)
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")

        # Reset goal to something that doesn't send lead email
        sample_context.goal = CallGoal.QUALIFY_INTEREST
        sample_call_result.goal = CallGoal.QUALIFY_INTEREST
        sample_call_result.outcome = "qualified"
        sample_call_result.lead_email = None

        results = await send_post_call_emails(sample_context, sample_call_result)

        assert results["owner_email_sent"] is True
        assert results["lead_email_sent"] is False
        assert mock_send.call_count == 1

    @pytest.mark.asyncio
    async def test_sends_payment_link_on_committed(
        self, sample_context, sample_call_result, monkeypatch
    ):
        """Test that payment link is sent when close_sale commits."""
        mock_send = MagicMock(return_value={"id": "email_123"})
        monkeypatch.setattr("resend.Emails.send", mock_send)
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")

        sample_context.goal = CallGoal.CLOSE_SALE
        sample_call_result.goal = CallGoal.CLOSE_SALE
        sample_call_result.outcome = "committed"
        sample_call_result.lead_email = "lead@example.com"

        results = await send_post_call_emails(sample_context, sample_call_result)

        assert results["owner_email_sent"] is True
        assert results["lead_email_sent"] is True
        assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_sends_booking_link_on_booked(
        self, sample_context, sample_call_result, monkeypatch
    ):
        """Test that booking link is sent when book_meeting books."""
        mock_send = MagicMock(return_value={"id": "email_123"})
        monkeypatch.setattr("resend.Emails.send", mock_send)
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")

        sample_context.goal = CallGoal.BOOK_MEETING
        sample_call_result.goal = CallGoal.BOOK_MEETING
        sample_call_result.outcome = "booked"
        sample_call_result.lead_email = "lead@example.com"

        results = await send_post_call_emails(sample_context, sample_call_result)

        assert results["owner_email_sent"] is True
        assert results["lead_email_sent"] is True
        assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_no_lead_email_without_collected_email(
        self, sample_context, sample_call_result, monkeypatch
    ):
        """Test that lead email is not sent if no email was collected."""
        mock_send = MagicMock(return_value={"id": "email_123"})
        monkeypatch.setattr("resend.Emails.send", mock_send)
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")

        sample_context.goal = CallGoal.CLOSE_SALE
        sample_call_result.goal = CallGoal.CLOSE_SALE
        sample_call_result.outcome = "committed"
        sample_call_result.lead_email = None  # No email collected

        results = await send_post_call_emails(sample_context, sample_call_result)

        assert results["owner_email_sent"] is True
        assert results["lead_email_sent"] is False
        assert mock_send.call_count == 1  # Only owner email

    @pytest.mark.asyncio
    async def test_no_lead_email_on_declined(
        self, sample_context, sample_call_result, monkeypatch
    ):
        """Test that lead email is not sent if outcome is declined."""
        mock_send = MagicMock(return_value={"id": "email_123"})
        monkeypatch.setattr("resend.Emails.send", mock_send)
        monkeypatch.setenv("RESEND_API_KEY", "re_test_key")

        sample_context.goal = CallGoal.CLOSE_SALE
        sample_call_result.goal = CallGoal.CLOSE_SALE
        sample_call_result.outcome = "objection_price"  # Declined due to price
        sample_call_result.lead_email = "lead@example.com"

        results = await send_post_call_emails(sample_context, sample_call_result)

        assert results["owner_email_sent"] is True
        assert results["lead_email_sent"] is False  # Don't spam declined leads
