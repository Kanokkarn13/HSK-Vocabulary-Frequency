"""Vercel serverless entrypoint. Exposes the FastAPI ASGI app directly —
Vercel's Python runtime detects the `app` variable and serves it natively,
no adapter (e.g. Mangum, which targets AWS Lambda's event format) needed."""
from backend.main import app
