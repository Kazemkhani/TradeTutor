"""Tests for context builder - Stateless Multi-Tenant MVP."""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from context_builder.builder import (
    ContextBuilder,
    build_context,
    build_contexts_for_submission,
)
from shared.schemas import (
    CallGoal,
    CallRequest,
    ContextInstance,
    Lead,
)


def make_lead(**kwargs) -> Lead:
    """Helper to create a Lead with defaults."""
    defaults = {
        "phone": "+14155551234",
    }
    defaults.update(kwargs)
    return Lead(**defaults)


def make_request(**kwargs) -> CallRequest:
    """Helper to create a CallRequest with defaults."""
    defaults = {
        "owner_email": "owner@example.com",
        "leads": [make_lead()],
        "product": "Test Product",
        "goal": CallGoal.QUALIFY_INTEREST,
    }
    defaults.update(kwargs)
    return CallRequest(**defaults)


def make_close_sale_request(**kwargs) -> CallRequest:
    """Helper to create a close_sale CallRequest."""
    defaults = {
        "owner_email": "owner@example.com",
        "leads": [make_lead()],
        "product": "Premium CRM",
        "goal": CallGoal.CLOSE_SALE,
        "payment_link": "https://buy.stripe.com/test",
        "pricing_summary": "$99/month",
        "urgency_hook": "50% off this week only",
    }
    defaults.update(kwargs)
    return CallRequest(**defaults)


def make_book_meeting_request(**kwargs) -> CallRequest:
    """Helper to create a book_meeting CallRequest."""
    defaults = {
        "owner_email": "owner@example.com",
        "leads": [make_lead()],
        "product": "Test Product",
        "goal": CallGoal.BOOK_MEETING,
        "booking_link": "https://calendly.com/test/30min",
    }
    defaults.update(kwargs)
    return CallRequest(**defaults)


class TestContextBuilder:
    """Tests for ContextBuilder class."""

    def test_builds_context_instance(self):
        """Test that builder creates a valid ContextInstance."""
        lead = make_lead(name="John Doe")
        request = make_request(leads=[lead])

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert isinstance(context, ContextInstance)
        assert context.phone == "+14155551234"
        assert context.name == "John Doe"
        assert context.product == "Test Product"
        assert context.owner_email == "owner@example.com"

    def test_generates_agent_instructions(self):
        """Test that builder generates agent instructions."""
        lead = make_lead()
        request = make_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert context.agent_instructions is not None
        assert len(context.agent_instructions) > 0
        assert "professional" in context.agent_instructions.lower()

    def test_generates_opening_line_with_name(self):
        """Test that builder generates personalized opening line."""
        lead = make_lead(name="Jane Smith")
        request = make_request(leads=[lead])

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert context.opening_line is not None
        assert "Jane Smith" in context.opening_line
        assert request.product in context.opening_line

    def test_generates_opening_line_without_name(self):
        """Test opening line when no name provided."""
        lead = make_lead()  # No name
        request = make_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert context.opening_line is not None
        assert request.product in context.opening_line

    def test_generates_opening_line_with_company(self):
        """Test opening line includes lead's company when provided."""
        lead = make_lead(name="John", company="Acme Corp")
        request = make_request(leads=[lead])

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert "Acme Corp" in context.opening_line

    def test_generates_qualification_questions(self):
        """Test that builder generates qualification questions."""
        lead = make_lead()
        request = make_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert isinstance(context.qualification_questions, list)
        assert len(context.qualification_questions) > 0

    def test_generates_objection_handlers(self):
        """Test that builder generates objection handlers."""
        lead = make_lead()
        request = make_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert isinstance(context.objection_handlers, dict)
        assert len(context.objection_handlers) > 0
        assert "too_expensive" in context.objection_handlers

    def test_generates_closing_script(self):
        """Test that builder generates closing script."""
        lead = make_lead()
        request = make_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert context.closing_script is not None
        assert len(context.closing_script) > 0

    def test_product_context_included(self):
        """Test that product context is included in agent instructions."""
        lead = make_lead()
        request = make_request(context="Special feature: AI-powered analytics")

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert "AI-powered analytics" in context.agent_instructions

    def test_per_lead_data_in_context(self):
        """Test that per-lead company and title are included in context."""
        lead = make_lead(
            name="Alice",
            company="TechCorp",
            title="VP of Sales",
            email="alice@techcorp.com",
        )
        request = make_request(leads=[lead])

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert context.name == "Alice"
        assert context.lead_company == "TechCorp"
        assert context.lead_title == "VP of Sales"
        assert context.lead_email_preknown == "alice@techcorp.com"


class TestCloseSaleGoal:
    """Tests for close_sale goal behavior."""

    def test_close_sale_generates_assertive_instructions(self):
        """Test that close_sale generates assertive agent instructions."""
        lead = make_lead()
        request = make_close_sale_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert "confident" in context.agent_instructions.lower()
        assert "value" in context.agent_instructions.lower()
        assert (
            "sales" in context.agent_instructions.lower()
            or "close" in context.agent_instructions.lower()
        )

    def test_close_sale_includes_pricing(self):
        """Test that close_sale includes pricing in instructions."""
        lead = make_lead()
        request = make_close_sale_request(pricing_summary="$149/month")

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert "$149/month" in context.agent_instructions

    def test_close_sale_includes_urgency(self):
        """Test that close_sale includes urgency hook in instructions."""
        lead = make_lead()
        request = make_close_sale_request(urgency_hook="Limited time offer")

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert "Limited time offer" in context.agent_instructions

    def test_close_sale_has_assertive_objection_handlers(self):
        """Test that close_sale has more assertive objection handlers."""
        lead = make_lead()
        request = make_close_sale_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        # Close sale should have assertive handlers
        assert "too_expensive" in context.objection_handlers
        assert (
            "ROI" in context.objection_handlers["too_expensive"]
            or "pays for itself" in context.objection_handlers["too_expensive"]
        )

    def test_close_sale_has_need_approval_handler(self):
        """Test that close_sale has handler for 'need to check with someone'."""
        lead = make_lead()
        request = make_close_sale_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert "need_approval" in context.objection_handlers

    def test_close_sale_opening_is_direct(self):
        """Test that close_sale opening is more direct."""
        lead = make_lead()
        request = make_close_sale_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert "2 minutes" in context.opening_line or "achieve" in context.opening_line

    def test_close_sale_has_payment_closing(self):
        """Test that close_sale closing mentions payment link."""
        lead = make_lead()
        request = make_close_sale_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert "payment" in context.closing_script.lower()


class TestEmailConfiguration:
    """Tests for email configuration based on goal."""

    def test_book_meeting_enables_lead_email(self):
        """Test that book_meeting enables lead email with booking template."""
        lead = make_lead()
        request = make_book_meeting_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert context.should_email_lead is True
        assert context.lead_email_template == "booking"

    def test_close_sale_enables_lead_email(self):
        """Test that close_sale enables lead email with payment template."""
        lead = make_lead()
        request = make_close_sale_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert context.should_email_lead is True
        assert context.lead_email_template == "payment"

    def test_qualify_interest_no_lead_email(self):
        """Test that qualify_interest does not enable lead email."""
        lead = make_lead()
        request = make_request(goal=CallGoal.QUALIFY_INTEREST)

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert context.should_email_lead is False
        assert context.lead_email_template == ""

    def test_collect_info_no_lead_email(self):
        """Test that collect_info does not enable lead email."""
        lead = make_lead()
        request = make_request(goal=CallGoal.COLLECT_INFO)

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert context.should_email_lead is False
        assert context.lead_email_template == ""


class TestBookMeetingGoal:
    """Tests for book_meeting goal behavior."""

    def test_book_meeting_generates_consultative_instructions(self):
        """Test that book_meeting generates consultative agent instructions."""
        lead = make_lead()
        request = make_book_meeting_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert (
            "demo" in context.agent_instructions.lower()
            or "meeting" in context.agent_instructions.lower()
        )
        assert (
            "consultative" in context.agent_instructions.lower()
            or "helpful" in context.agent_instructions.lower()
        )

    def test_book_meeting_mentions_email_booking_link(self):
        """Test that book_meeting mentions emailing booking link."""
        lead = make_lead()
        request = make_book_meeting_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert "email" in context.agent_instructions.lower()
        assert "booking" in context.agent_instructions.lower()

    def test_book_meeting_closing_mentions_email(self):
        """Test that book_meeting closing mentions email."""
        lead = make_lead()
        request = make_book_meeting_request()

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert "email" in context.closing_script.lower()


class TestCollectInfoGoal:
    """Tests for collect_info goal behavior."""

    def test_collect_info_uses_goal_criteria(self):
        """Test that collect_info uses goal_criteria for questions."""
        lead = make_lead()
        request = make_request(
            goal=CallGoal.COLLECT_INFO,
            goal_criteria="email, company size, current solution",
        )

        builder = ContextBuilder()
        context = builder.build(request, lead)

        assert "email, company size, current solution" in context.agent_instructions


class TestBuildContextFunction:
    """Tests for build_context convenience function."""

    def test_builds_context(self):
        """Test convenience function builds context."""
        lead = make_lead()
        request = make_request()

        context = build_context(request, lead)

        assert isinstance(context, ContextInstance)
        assert context.phone == "+14155551234"

    def test_accepts_llm_model(self):
        """Test convenience function accepts llm_model param."""
        lead = make_lead()
        request = make_request()

        # Should not raise
        context = build_context(request, lead, llm_model="test/model")

        assert isinstance(context, ContextInstance)


class TestBuildContextsForSubmission:
    """Tests for build_contexts_for_submission function."""

    def test_builds_contexts_for_all_leads(self):
        """Test that function builds contexts for all leads."""
        leads = [
            Lead(phone="+14155551234", name="John"),
            Lead(phone="+14155551235", name="Sarah"),
            Lead(phone="+14155551236", name="Mike"),
        ]
        request = make_request(leads=leads)

        contexts = build_contexts_for_submission(request)

        assert len(contexts) == 3
        assert contexts[0].phone == "+14155551234"
        assert contexts[0].name == "John"
        assert contexts[1].phone == "+14155551235"
        assert contexts[1].name == "Sarah"
        assert contexts[2].phone == "+14155551236"
        assert contexts[2].name == "Mike"

    def test_all_contexts_share_same_owner(self):
        """Test that all contexts share the same owner email."""
        leads = [
            Lead(phone="+14155551234"),
            Lead(phone="+14155551235"),
        ]
        request = make_request(
            leads=leads,
            owner_email="shared@example.com",
        )

        contexts = build_contexts_for_submission(request)

        assert all(c.owner_email == "shared@example.com" for c in contexts)

    def test_each_context_has_unique_id(self):
        """Test that each context has a unique ID."""
        leads = [
            Lead(phone="+14155551234"),
            Lead(phone="+14155551235"),
            Lead(phone="+14155551236"),
        ]
        request = make_request(leads=leads)

        contexts = build_contexts_for_submission(request)

        ids = [c.id for c in contexts]
        assert len(ids) == len(set(ids))  # All unique

    def test_different_leads_get_different_opening_lines(self):
        """Test that different leads produce different personalized openings."""
        leads = [
            Lead(phone="+14155551234", name="Alice", company="TechCorp"),
            Lead(phone="+14155551235", name="Bob", company="StartupXYZ"),
        ]
        request = make_request(leads=leads)

        contexts = build_contexts_for_submission(request)

        assert "Alice" in contexts[0].opening_line
        assert "TechCorp" in contexts[0].opening_line
        assert "Bob" in contexts[1].opening_line
        assert "StartupXYZ" in contexts[1].opening_line


class TestContextInstanceSerialization:
    """Tests for ContextInstance JSON serialization."""

    def test_context_serializes_to_json(self):
        """Test that context can be serialized to JSON."""
        lead = make_lead()
        request = make_request()

        context = build_context(request, lead)
        json_str = context.model_dump_json()

        assert isinstance(json_str, str)
        assert "+14155551234" in json_str
        assert "Test Product" in json_str

    def test_context_deserializes_from_json(self):
        """Test that context can be deserialized from JSON."""
        lead = make_lead(name="Test User")
        request = make_request(leads=[lead])

        context = build_context(request, lead)
        json_str = context.model_dump_json()

        # Deserialize
        restored = ContextInstance.model_validate_json(json_str)

        assert restored.phone == "+14155551234"
        assert restored.name == "Test User"
        assert restored.product == "Test Product"

    def test_close_sale_context_serializes(self):
        """Test that close_sale context serializes all fields."""
        lead = make_lead()
        request = make_close_sale_request()

        context = build_context(request, lead)
        json_str = context.model_dump_json()

        # Deserialize
        restored = ContextInstance.model_validate_json(json_str)

        assert restored.goal == CallGoal.CLOSE_SALE
        assert restored.payment_link == "https://buy.stripe.com/test"
        assert restored.pricing_summary == "$99/month"
        assert restored.urgency_hook == "50% off this week only"
        assert restored.should_email_lead is True
        assert restored.lead_email_template == "payment"

    def test_context_with_lead_details_serializes(self):
        """Test that context with per-lead details serializes correctly."""
        lead = make_lead(
            name="Alice",
            company="TechCorp",
            title="CTO",
            email="alice@techcorp.com",
        )
        request = make_request(leads=[lead])

        context = build_context(request, lead)
        json_str = context.model_dump_json()

        restored = ContextInstance.model_validate_json(json_str)
        assert restored.name == "Alice"
        assert restored.lead_company == "TechCorp"
        assert restored.lead_title == "CTO"
        assert restored.lead_email_preknown == "alice@techcorp.com"
