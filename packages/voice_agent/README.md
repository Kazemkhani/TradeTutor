# Voice Agent

LiveKit-based voice agent for the AI Lead Qualification Voice Agent System.

This package handles real-time voice conversations. It receives pre-built context via the `--context` CLI flag and contains no DSPy dependencies for optimal latency.

## Usage

```bash
# Download required models (VAD, turn detector)
python src/agent.py download-files

# Console mode (talk to agent in terminal)
python src/agent.py console

# Development mode
python src/agent.py dev

# With context injection
python src/agent.py dev --context ./context.json
```

## Configuration

All provider configuration is loaded from environment variables (see `.env.local`):

- `VOICE_AGENT_LLM_MODEL` - LLM model identifier
- `VOICE_AGENT_STT_MODEL` - STT model identifier
- `VOICE_AGENT_TTS_MODEL` - TTS model identifier
- `VOICE_AGENT_VOICE_ID` - Voice ID for TTS
- `VOICE_AGENT_LANGUAGE` - Language code (default: en)
