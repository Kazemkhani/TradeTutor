"""Email sending module using Resend.

Handles all email sending for the Stateless Multi-Tenant Voice Agent MVP:
- Owner summary emails (all goals)
- Booking link emails to leads (book_meeting)
- Payment link emails to leads (close_sale)

Uses Resend API for reliable email delivery.
"""

import logging
import os
from dataclasses import dataclass

import resend

from shared.schemas import CallGoal, CallResult, ContextInstance

logger = logging.getLogger("voice-agent-email")


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class EmailConfig:
    """Email service configuration."""

    api_key: str
    from_email: str
    from_name: str = "Voice Agent"

    @classmethod
    def from_env(cls) -> "EmailConfig":
        """Load email config from environment variables."""
        api_key = os.getenv("RESEND_API_KEY", "")
        from_email = os.getenv("RESEND_FROM_EMAIL", "noreply@example.com")
        from_name = os.getenv("RESEND_FROM_NAME", "Voice Agent")

        if not api_key:
            logger.warning("RESEND_API_KEY not set - emails will fail")

        return cls(api_key=api_key, from_email=from_email, from_name=from_name)


# =============================================================================
# Email Templates
# =============================================================================


def _format_outcome(outcome: str, goal: CallGoal) -> str:
    """Format outcome string for display."""
    outcome_labels = {
        # Book meeting outcomes
        "booked": "Meeting Booked",
        "declined": "Declined",
        # Qualify interest outcomes
        "qualified": "Lead Qualified",
        "not_qualified": "Not Qualified",
        # Collect info outcomes
        "collected": "Information Collected",
        "partial": "Partial Information",
        # Close sale outcomes
        "committed": "Sale Committed",
        "soft_commitment": "Soft Commitment (Follow-up Needed)",
        "objection_price": "Objection: Price",
        "objection_timing": "Objection: Timing",
        "objection_trust": "Objection: Trust",
        "no_interest": "Not Interested",
        # Common outcomes
        "no_answer": "No Answer",
        "disconnected": "Call Disconnected",
        "error": "Error",
        "pending": "Pending",
    }
    return outcome_labels.get(outcome, outcome.replace("_", " ").title())


def _build_owner_summary_html(
    context: ContextInstance,
    result: CallResult,
) -> str:
    """Build HTML content for owner summary email."""
    outcome_display = _format_outcome(result.outcome, result.goal)
    goal_display = result.goal.value.replace("_", " ").title()

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Call Summary - {context.product}</h2>

        <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #666;">Call Details</h3>
            <p><strong>Phone:</strong> {result.phone}</p>
            <p><strong>Goal:</strong> {goal_display}</p>
            <p><strong>Outcome:</strong> <span style="color: {"#28a745" if result.outcome in ("booked", "qualified", "collected", "committed") else "#dc3545"};">{outcome_display}</span></p>
            <p><strong>Duration:</strong> {result.duration_seconds} seconds</p>
    """

    if result.objection_reason:
        html += f"""
            <p><strong>Objection Reason:</strong> {result.objection_reason}</p>
        """

    if result.lead_email:
        html += f"""
            <p><strong>Lead Email Collected:</strong> {result.lead_email}</p>
        """

    html += """
        </div>
    """

    # Collected data section
    if result.collected_data:
        html += """
        <div style="background: #e8f4fd; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #0066cc;">Collected Information</h3>
            <ul style="margin: 0; padding-left: 20px;">
        """
        for key, value in result.collected_data.items():
            html += f"""
                <li><strong>{key.replace("_", " ").title()}:</strong> {value}</li>
            """
        html += """
            </ul>
        </div>
        """

    # Transcript section
    if result.transcript:
        html += f"""
        <div style="background: #fff; border: 1px solid #ddd; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #666;">Call Transcript</h3>
            <pre style="white-space: pre-wrap; font-family: monospace; font-size: 12px; background: #f9f9f9; padding: 10px; border-radius: 4px; overflow-x: auto;">{result.transcript}</pre>
        </div>
        """

    # Recording URL
    if result.recording_url:
        html += f"""
        <div style="margin: 20px 0;">
            <a href="{result.recording_url}" style="display: inline-block; background: #0066cc; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Listen to Recording</a>
        </div>
        """

    html += """
        <p style="color: #999; font-size: 12px; margin-top: 30px;">
            This email was automatically generated by Voice Agent.
        </p>
    </div>
    """

    return html


def _build_booking_link_html(
    context: ContextInstance,
    lead_email: str,
) -> str:
    """Build HTML content for booking link email to lead."""
    lead_name = context.name or "there"

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Schedule Your Demo - {context.product}</h2>

        <p>Hi {lead_name},</p>

        <p>Thank you for your interest in {context.product}! As promised during our call, here's the link to schedule your demo at a time that works best for you:</p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{context.booking_link}" style="display: inline-block; background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-size: 18px;">Book Your Demo</a>
        </div>

        <p>If you have any questions before our meeting, feel free to reply to this email.</p>

        <p>Looking forward to speaking with you!</p>

        <p style="color: #999; font-size: 12px; margin-top: 30px;">
            If the button doesn't work, copy and paste this link: {context.booking_link}
        </p>
    </div>
    """

    return html


def _build_payment_link_html(
    context: ContextInstance,
    lead_email: str,
) -> str:
    """Build HTML content for payment link email to lead."""
    lead_name = context.name or "there"

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Complete Your Purchase - {context.product}</h2>

        <p>Hi {lead_name},</p>

        <p>Thank you for choosing {context.product}! As discussed, here's your secure payment link:</p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{context.payment_link}" style="display: inline-block; background: #0066cc; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-size: 18px;">Complete Purchase</a>
        </div>
    """

    if context.pricing_summary:
        html += f"""
        <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #666;">Pricing Details</h3>
            <p>{context.pricing_summary}</p>
        </div>
        """

    if context.urgency_hook:
        html += f"""
        <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107;">
            <p style="margin: 0;"><strong>Limited Time:</strong> {context.urgency_hook}</p>
        </div>
        """

    html += f"""
        <p>If you have any questions, feel free to reply to this email.</p>

        <p>Thank you for your business!</p>

        <p style="color: #999; font-size: 12px; margin-top: 30px;">
            If the button doesn't work, copy and paste this link: {context.payment_link}
        </p>
    </div>
    """

    return html


# =============================================================================
# Email Sender
# =============================================================================


class EmailSender:
    """Sends emails via Resend API."""

    def __init__(self, config: EmailConfig | None = None):
        """Initialize the email sender.

        Args:
            config: Email configuration. If not provided, loads from environment.
        """
        self.config = config or EmailConfig.from_env()
        resend.api_key = self.config.api_key

    async def send_owner_summary(
        self,
        context: ContextInstance,
        result: CallResult,
    ) -> bool:
        """Send summary email to the business owner.

        Args:
            context: The context instance with owner_email
            result: The call result with outcome and transcript

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.config.api_key:
            logger.error("Cannot send email: RESEND_API_KEY not configured")
            return False

        try:
            outcome_display = _format_outcome(result.outcome, result.goal)
            subject = f"Call Complete: {context.product} - {outcome_display}"

            html_content = _build_owner_summary_html(context, result)

            params: resend.Emails.SendParams = {
                "from": f"{self.config.from_name} <{self.config.from_email}>",
                "to": [context.owner_email],
                "subject": subject,
                "html": html_content,
            }

            email_response = resend.Emails.send(params)
            logger.info(
                f"Owner summary email sent to {context.owner_email}: {email_response.get('id')}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to send owner summary email: {e}")
            return False

    async def send_booking_link(
        self,
        context: ContextInstance,
        lead_email: str,
    ) -> bool:
        """Send booking link email to the lead.

        Args:
            context: The context instance with booking_link
            lead_email: The lead's email address

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.config.api_key:
            logger.error("Cannot send email: RESEND_API_KEY not configured")
            return False

        if not context.booking_link:
            logger.error("Cannot send booking link: no booking_link in context")
            return False

        try:
            subject = f"Book Your Demo - {context.product}"
            html_content = _build_booking_link_html(context, lead_email)

            params: resend.Emails.SendParams = {
                "from": f"{self.config.from_name} <{self.config.from_email}>",
                "to": [lead_email],
                "subject": subject,
                "html": html_content,
            }

            email_response = resend.Emails.send(params)
            logger.info(
                f"Booking link email sent to {lead_email}: {email_response.get('id')}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to send booking link email: {e}")
            return False

    async def send_payment_link(
        self,
        context: ContextInstance,
        lead_email: str,
    ) -> bool:
        """Send payment link email to the lead.

        Args:
            context: The context instance with payment_link
            lead_email: The lead's email address

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.config.api_key:
            logger.error("Cannot send email: RESEND_API_KEY not configured")
            return False

        if not context.payment_link:
            logger.error("Cannot send payment link: no payment_link in context")
            return False

        try:
            subject = f"Complete Your Purchase - {context.product}"
            html_content = _build_payment_link_html(context, lead_email)

            params: resend.Emails.SendParams = {
                "from": f"{self.config.from_name} <{self.config.from_email}>",
                "to": [lead_email],
                "subject": subject,
                "html": html_content,
            }

            email_response = resend.Emails.send(params)
            logger.info(
                f"Payment link email sent to {lead_email}: {email_response.get('id')}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to send payment link email: {e}")
            return False


# =============================================================================
# Convenience Functions
# =============================================================================


async def send_post_call_emails(
    context: ContextInstance,
    result: CallResult,
) -> dict[str, bool]:
    """Send all appropriate emails after a call completes.

    Determines which emails to send based on goal and outcome,
    then sends them.

    Args:
        context: The context instance
        result: The call result

    Returns:
        Dict with keys 'owner_email_sent' and 'lead_email_sent'
    """
    sender = EmailSender()
    results = {
        "owner_email_sent": False,
        "lead_email_sent": False,
    }

    # Always send owner summary
    results["owner_email_sent"] = await sender.send_owner_summary(context, result)

    # Send lead email based on goal and outcome
    if result.lead_email:
        if context.goal == CallGoal.BOOK_MEETING and result.outcome == "booked":
            results["lead_email_sent"] = await sender.send_booking_link(
                context, result.lead_email
            )
        elif context.goal == CallGoal.CLOSE_SALE and result.outcome in (
            "committed",
            "soft_commitment",
        ):
            results["lead_email_sent"] = await sender.send_payment_link(
                context, result.lead_email
            )

    return results
