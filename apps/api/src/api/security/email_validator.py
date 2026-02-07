"""Email domain validation for anti-fraud.

Detects disposable email domains and categorizes email types.
"""

# Common disposable email domains (top 100+)
# In production, use a maintained list or API like hunter.io
DISPOSABLE_DOMAINS = frozenset(
    [
        # Popular disposable email services
        "10minutemail.com",
        "guerrillamail.com",
        "guerrillamail.org",
        "guerrillamailblock.com",
        "mailinator.com",
        "mailinator2.com",
        "maildrop.cc",
        "tempmail.com",
        "temp-mail.org",
        "throwaway.email",
        "throwawaymail.com",
        "getnada.com",
        "getairmail.com",
        "fakeinbox.com",
        "dispostable.com",
        "mailnesia.com",
        "mintemail.com",
        "mohmal.com",
        "tempinbox.com",
        "yopmail.com",
        "yopmail.fr",
        "spamgourmet.com",
        "trashmail.com",
        "trashmail.net",
        "sharklasers.com",
        "guerrillamail.net",
        "grr.la",
        "spam4.me",
        "byom.de",
        "trbvm.com",
        "mailforspam.com",
        "emailondeck.com",
        "fakemail.fr",
        "jetable.org",
        "nada.email",
        "tempail.com",
        "tempr.email",
        "discard.email",
        "discardmail.com",
        "mailcatch.com",
        "mailscrap.com",
        "mailsac.com",
        "mt2014.com",
        "mt2015.com",
        "mytrashmail.com",
        "throwam.com",
        "wegwerfmail.de",
        "wegwerfmail.net",
        "wegwerfmail.org",
        "zep-hyr.com",
        "crazymailing.com",
        "emkei.cz",
        "fakemailgenerator.com",
        "gmailnator.com",
        "inboxbear.com",
        "mailpoof.com",
        "10minutemail.net",
        "10minutemail.org",
        "33mail.com",
        "anonymbox.com",
        "antispam.de",
        "binkmail.com",
        "bobmail.info",
        "bofthew.com",
        "bugmenot.com",
        "bumpymail.com",
        "casualdx.com",
        "chogmail.com",
        "cool.fr.nf",
        "correo.blogos.net",
        "cosmorph.com",
        "courrieltemporaire.com",
        "curryworld.de",
        "dayrep.com",
        "devnullmail.com",
        "dfgh.net",
        "digitalsanctuary.com",
        "e4ward.com",
        "emailias.com",
        "emailisvalid.com",
        "emailsensei.com",
        "emailtemporanea.com",
        "emailtemporanea.net",
        "emailtemporario.com.br",
        "emailthe.net",
        "emailtmp.com",
        "emailwarden.com",
        "ephemail.net",
        "etranquil.com",
        "etranquil.net",
        "etranquil.org",
        "evopo.com",
        "explodemail.com",
        "fastacura.com",
        "fastchevy.com",
        "fastchrysler.com",
        "fastkawasaki.com",
        "fastmazda.com",
        "fastmitsubishi.com",
        "fastnissan.com",
        "fastsubaru.com",
        "fastsuzuki.com",
        "fasttoyota.com",
        "fastyamaha.com",
    ]
)

# Common free email providers (not disposable, but higher risk for B2B)
FREE_EMAIL_DOMAINS = frozenset(
    [
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "yahoo.fr",
        "yahoo.de",
        "yahoo.es",
        "yahoo.it",
        "hotmail.com",
        "hotmail.co.uk",
        "hotmail.fr",
        "hotmail.de",
        "hotmail.es",
        "hotmail.it",
        "outlook.com",
        "outlook.co.uk",
        "outlook.fr",
        "outlook.de",
        "live.com",
        "live.co.uk",
        "live.fr",
        "msn.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "protonmail.com",
        "proton.me",
        "mail.com",
        "zoho.com",
        "yandex.com",
        "yandex.ru",
        "gmx.com",
        "gmx.de",
        "gmx.net",
        "web.de",
        "t-online.de",
    ]
)


def get_domain(email: str) -> str:
    """Extract domain from email address."""
    return email.lower().split("@")[-1]


def is_disposable_email(email: str) -> bool:
    """Check if email uses a disposable domain.

    Args:
        email: Email address to check.

    Returns:
        True if the domain is known to be disposable.
    """
    domain = get_domain(email)
    return domain in DISPOSABLE_DOMAINS


def is_free_email(email: str) -> bool:
    """Check if email uses a free email provider.

    Args:
        email: Email address to check.

    Returns:
        True if the domain is a common free email provider.
    """
    domain = get_domain(email)
    return domain in FREE_EMAIL_DOMAINS


def validate_email_domain(email: str) -> tuple[bool, str | None]:
    """Validate email domain for signup.

    Args:
        email: Email address to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    # Block disposable emails
    if is_disposable_email(email):
        return (
            False,
            "Disposable email addresses are not allowed. Please use a permanent email.",
        )

    # Check for obviously fake patterns
    suspicious_patterns = [
        "test@",
        "fake@",
        "spam@",
        "noreply@",
        "nobody@",
        "example@",
        "asdf@",
        "qwerty@",
    ]
    email_lower = email.lower()
    for pattern in suspicious_patterns:
        if email_lower.startswith(pattern):
            return False, "This email address appears to be invalid."

    return True, None
