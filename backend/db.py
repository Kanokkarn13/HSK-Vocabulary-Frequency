import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import NullPool

DATABASE_URL = (
    f"postgresql://{os.getenv('DB_USER', 'hsk_user')}:"
    f"{os.getenv('DB_PASSWORD', 'changeme')}@"
    f"{os.getenv('DB_HOST', 'localhost')}:"
    f"{os.getenv('DB_PORT', '5432')}/"
    f"{os.getenv('DB_NAME', 'hsk_frequency')}"
)
if os.getenv("DB_SSLMODE"):
    DATABASE_URL += f"?sslmode={os.getenv('DB_SSLMODE')}"

# On Vercel (VERCEL=1 is set automatically in the function runtime), each
# invocation may run in a fresh, short-lived container, so a normal
# QueuePool sitting in front of Neon's pooler can accumulate stale
# connections instead of helping. NullPool opens/closes per request instead,
# which is what Neon's pooled endpoint (pgbouncer) expects. Locally/Docker
# (long-running process), the default QueuePool is still correct.
poolclass = NullPool if os.getenv("VERCEL") else None

engine = create_engine(DATABASE_URL, pool_pre_ping=True, poolclass=poolclass)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
