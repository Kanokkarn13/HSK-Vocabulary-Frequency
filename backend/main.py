import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import frequency, search, compare

app = FastAPI(
    title="HSK Vocabulary Frequency API",
    description="Analyze word frequency across HSK exam papers",
    version="0.1.0",
)

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
