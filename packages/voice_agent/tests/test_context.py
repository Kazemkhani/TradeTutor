"""Tests for context injection functionality."""

import json
import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from voice_agent.agent import get_context, load_context, set_context

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestLoadContext:
    """Tests for load_context function."""

    def test_loads_valid_context(self):
        """Test loading a valid ContextInstance JSON."""
        context = load_context(str(FIXTURES_DIR / "context.json"))
        assert context is not None
        assert context["phone"] == "+14155551234"
        assert context["product"] == "Enterprise Widget Suite"

    def test_context_has_all_required_fields(self):
        """Test that loaded context has all expected fields."""
        context = load_context(str(FIXTURES_DIR / "context.json"))
        # Form fields
        assert "owner_email" in context
        assert "phone" in context
        assert "product" in context
        assert "goal" in context
        # Generated fields
        assert "agent_instructions" in context
        assert "opening_line" in context
        assert "qualification_questions" in context

    def test_context_has_phone(self):
        """Test that context has required phone field."""
        context = load_context(str(FIXTURES_DIR / "context.json"))
        assert "phone" in context
        assert context["phone"].startswith("+")

    def test_context_has_agent_instructions(self):
        """Test that context has agent_instructions."""
        context = load_context(str(FIXTURES_DIR / "context.json"))
        assert "agent_instructions" in context
        assert len(context["agent_instructions"]) > 0

    def test_context_has_opening_line(self):
        """Test that context has opening_line."""
        context = load_context(str(FIXTURES_DIR / "context.json"))
        assert "opening_line" in context
        assert len(context["opening_line"]) > 0

    def test_context_email_config(self):
        """Test that context has email configuration for booking goal."""
        context = load_context(str(FIXTURES_DIR / "context.json"))
        assert context["goal"] == "book_meeting"
        assert context["should_email_lead"] is True
        assert context["lead_email_template"] == "booking"
        assert "booking_link" in context

    def test_fails_on_invalid_json(self, tmp_path):
        """Test failure on malformed JSON."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ invalid json }")

        with pytest.raises(ValueError, match="Invalid JSON"):
            load_context(str(bad_file))

    def test_fails_on_missing_file(self):
        """Test failure when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            load_context("/nonexistent/path/context.json")

    def test_returns_none_when_no_context(self):
        """Test that None context path returns None."""
        assert load_context(None) is None

    def test_returns_none_when_empty_string(self):
        """Test that empty string context path returns None."""
        assert load_context("") is None


class TestContextState:
    """Tests for context state management."""

    def test_set_and_get_context(self):
        """Test setting and getting context."""
        test_context = {"test": "data"}
        set_context(test_context)
        assert get_context() == test_context

    def test_clear_context(self):
        """Test clearing context by setting None."""
        set_context({"test": "data"})
        set_context(None)
        assert get_context() is None

    def test_context_persists(self):
        """Test that context persists across calls."""
        context = load_context(str(FIXTURES_DIR / "context.json"))
        set_context(context)

        # Multiple gets should return same context
        assert get_context() is context
        assert get_context() is context


class TestContextValidation:
    """Tests for context validation with shared schemas."""

    def test_fixture_validates_against_schema(self):
        """Test that fixture validates against ContextInstance schema."""
        try:
            from shared.schemas import ContextInstance

            with open(FIXTURES_DIR / "context.json") as f:
                data = json.load(f)

            # This should not raise
            context = ContextInstance.model_validate(data)
            assert context.phone == "+14155551234"
            assert context.product == "Enterprise Widget Suite"
            assert context.owner_email == "owner@acme.com"
            assert context.should_email_lead is True
            assert context.lead_email_template == "booking"
        except ImportError:
            pytest.skip("shared package not installed")
