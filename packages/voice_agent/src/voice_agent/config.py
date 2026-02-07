"""Voice Agent configuration.

Provider configuration is loaded from environment variables.
No hardcoded defaults - all values must be explicitly set in .env.local.
This ensures no vendor coupling in the codebase.
"""

import os


class ConfigurationError(Exception):
    """Raised when required configuration is missing."""

    pass


def _require_env(key: str, description: str) -> str:
    """Get required env var or raise clear error."""
    value = os.getenv(key)
    if not value:
        raise ConfigurationError(
            f"Missing required environment variable: {key}\n"
            f"Description: {description}\n"
            f"Please set this in your .env.local file.\n"
            f'Example: {key}="your-value-here"'
        )
    return value


class VoiceAgentConfig:
    """Provider configuration loaded from environment.

    No defaults - all values must be explicitly set in .env.local.
    This keeps the codebase provider-agnostic.

    Required environment variables:
    - VOICE_AGENT_LLM_MODEL: LLM model identifier
    - VOICE_AGENT_STT_MODEL: STT model identifier
    - VOICE_AGENT_TTS_MODEL: TTS model identifier
    - VOICE_AGENT_VOICE_ID: Voice ID for TTS
    """

    def __init__(self):
        self.llm_model = _require_env(
            "VOICE_AGENT_LLM_MODEL",
            "LLM model identifier (e.g., anthropic/claude-sonnet-4.5-20250929)",
        )
        self.stt_model = _require_env(
            "VOICE_AGENT_STT_MODEL",
            "STT model identifier (e.g., assemblyai/universal-streaming)",
        )
        self.tts_model = _require_env(
            "VOICE_AGENT_TTS_MODEL",
            "TTS model identifier (e.g., cartesia/sonic-3)",
        )
        self.voice_id = _require_env(
            "VOICE_AGENT_VOICE_ID",
            "Voice ID for TTS (provider-specific)",
        )
        # Language has a sensible default
        self.language = os.getenv("VOICE_AGENT_LANGUAGE", "en")


def load_config() -> VoiceAgentConfig:
    """Load and validate configuration. Fails fast with clear errors."""
    return VoiceAgentConfig()
