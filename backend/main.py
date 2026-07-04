import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from backend.routers import frequency, search, compare

app = FastAPI(
    title="HSK Vocabulary Frequency API",
    description="Analyze word frequency across HSK exam papers",
    version="0.1.0",
)

# Rate limiting deters casual bulk-scraping. It's in-memory (per serverless
# instance) rather than backed by Redis/etc, so a cold start resets the
# counters — good enough against sustained request bursts within one warm
# instance, not a hard guarantee across every invocation on Vercel.
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Blocks requests with no User-Agent or with the default UA of common
# scraping libraries. Trivially spoofed by anyone motivated, but it's a free
# filter that stops the large share of naive/default-config scrapers.
BLOCKED_UA_SUBSTRINGS = (
    "python-requests",
    "scrapy",
    "curl/",
    "wget/",
    "go-http-client",
    "libwww-perl",
    "httpclient",
)


@app.middleware("http")
async def block_known_scrapers(request: Request, call_next):
    ua = request.headers.get("user-agent", "").lower()
    if not ua or any(sub in ua for sub in BLOCKED_UA_SUBSTRINGS):
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)


allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(frequency.router, prefix="/api/frequency", tags=["frequency"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(compare.router, prefix="/api/compare", tags=["compare"])


@app.get("/health")
def health():
    return {"status": "ok"}
