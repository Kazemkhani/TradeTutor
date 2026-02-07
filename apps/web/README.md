# Web Form - Lead Submission

Minimal web form for submitting leads to the AI Lead Qualification System.

## Overview

This is a simple, static HTML form that:
1. Collects lead information (phone, name, company, email, notes)
2. Submits to the API (`POST /leads`)
3. Triggers a qualification call (`POST /calls/trigger`)

No build step required - just static HTML, CSS, and JavaScript.

## Running Locally

```bash
# From the apps/web directory
python -m http.server 3000

# Or using task
task web:dev
```

Then open http://localhost:3000 in your browser.

## Prerequisites

The API must be running at http://localhost:8000 for the form to work.

```bash
# Start the API first
task api:dev

# Then start the web form
task web:dev
```

## Form Fields

| Field | Required | Description |
|-------|----------|-------------|
| Phone | Yes | Lead's phone number (E.164 format preferred) |
| Name | No | Lead's full name |
| Company | No | Company name |
| Email | No | Email address |
| Notes | No | Additional context about the lead |

## API Integration

The form makes two API calls:

1. `POST /leads` - Creates the lead record
2. `POST /calls/trigger` - Triggers the qualification call

Both calls expect the API to be running at `http://localhost:8000`.

## Customization

To change the API endpoint, modify the `API_BASE` constant in `index.html`:

```javascript
const API_BASE = 'http://localhost:8000';
```

## Production Deployment

For production, you can:
1. Serve these static files from any CDN or static hosting
2. Update the `API_BASE` to point to your production API
3. Configure CORS appropriately on the API side
