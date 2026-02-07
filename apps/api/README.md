# API

FastAPI orchestration layer for the AI Lead Qualification Voice Agent System.

Connects the web form to the context builder and voice agent.

## Endpoints

- `POST /leads` - Create a new lead
- `GET /leads/{lead_id}` - Get lead details
- `POST /calls/trigger` - Trigger a qualification call
- `GET /calls/{call_id}` - Get call status
- `GET /health` - Health check

## Usage

```bash
# Development mode
uvicorn api.main:app --reload --port 8000
```
