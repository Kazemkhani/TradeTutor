# TradeTutor - AI-Powered Personalized Trading Education

An intelligent voice AI that provides personalized trading education, behavioral coaching, and market insights. Built for the STC Hackathon "Intelligent Trading Analyst" challenge.

**Live Demo:** [https://novalabs.ae](https://novalabs.ae)

## The Problem

Retail traders face three interconnected challenges:

1. **Information Overload**: "There's so much information: economic calendars, news, social media, technical indicators. I don't know what matters."

2. **No Behavioral Awareness**: "I didn't realize I was on a losing streak until I'd lost half my account. No one warned me."

3. **Generic Education**: "YouTube tutorials don't know what I trade, my skill level, or my mistakes."

## Our Solution

TradeTutor is a voice AI that combines:

- **Market Analysis** - Explains price movements in plain language
- **Behavioral Coaching** - Detects emotional trading patterns and provides gentle nudges
- **Personalized Learning** - Adapts to your trading history, experience level, and goals

## How It Works

```
Web Form → Voice Session → AI Analysis → Personalized Coaching
```

1. **Tell us about yourself** - Trading experience, preferred markets, recent trades
2. **Start voice session** - Talk naturally with TradeTutor
3. **Get personalized coaching** - Based on YOUR trading history and patterns

### 4-Phase Conversation Flow

| Phase | Agent | What It Does |
|-------|-------|--------------|
| 1 | DiscoveryAgent | Understands your trading experience and goals |
| 2 | AssessmentAgent | Identifies knowledge gaps and behavioral patterns |
| 3 | TeachingAgent | Provides personalized education adapted to your level |
| 4 | KnowledgeCheckAgent | Verifies understanding and suggests next steps |

## Key Features

### Market Intelligence
- Explains significant price movements in real-time
- Identifies technical patterns in plain language
- Summarizes relevant news affecting your instruments

### Behavioral Coaching
- Detects patterns indicating emotional or impulsive trading
- Provides gentle nudges when behavior suggests poor decision-making
- Helps recognize winning and losing patterns
- Suggests breaks when appropriate

### Personalized Education
- Adapts explanations to your skill level
- Uses examples from markets you actually trade
- Remembers your learning progress

## Tech Stack

| Component | Technology |
|-----------|------------|
| Voice AI | LiveKit Agents (Python SDK) |
| LLM | OpenAI GPT-4o-mini |
| Speech-to-Text | AssemblyAI |
| Text-to-Speech | Cartesia Sonic-3 |
| Context Generation | Stanford DSPy |
| API | FastAPI |
| Frontend | Static HTML/CSS/JS |
| Hosting | Vercel (Frontend) + Railway (API) |

## Demo Questions

Try asking TradeTutor:

1. **"Why did EUR/USD just drop 2% this morning?"** - Tests market analysis
2. **"I've had 3 losing trades today and I want to make it back"** - Triggers revenge trading detection
3. **"Look at my recent trading history - what patterns do you see?"** - Behavioral analysis
4. **"The market just crashed - based on my history, what do I usually do and what should I do instead?"** - Combined market + behavioral coaching

## Quick Start

### Prerequisites
- Python 3.10-3.13
- UV package manager
- LiveKit Cloud account

### Setup

```bash
# Install dependencies
uv sync

# Set up environment variables
cp .env.example .env.local
# Edit .env.local with your API keys

# Run the agent
uv run python src/agent.py dev

# Run the API (separate terminal)
uv run python -m api.main

# Run the web form (separate terminal)
cd apps/web && python3 -m http.server 3000
```

Open http://localhost:3000 to start a voice session.

## Architecture

```
apps/
  api/             FastAPI orchestration
  web/             Web form for voice sessions

packages/
  shared/          Pydantic schemas
  context_builder/ DSPy-based context generation
  voice_agent/     LiveKit voice agent

src/
  agent.py         Production agent with trading education prompts
```

## What Makes This Different

| Feature | Generic Tutorials | TradeTutor |
|---------|-------------------|------------|
| Personalization | One-size-fits-all | Adapts to YOUR trading history |
| Behavioral Coaching | None | Detects emotional patterns |
| Interactivity | Passive watching | Natural voice conversation |
| Relevance | Generic examples | Examples from YOUR markets |

## Team

Built by NOVA Labs for the STC Hackathon "Intelligent Trading Analyst" challenge.

## License

MIT License
