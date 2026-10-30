from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

_database_url = settings.database_url
_is_sqlite = _database_url.startswith("sqlite")

# SQLite needs check_same_thread=False for multi-threaded access (FastAPI).
# PostgreSQL / Neon uses connection pooling with pre_ping so idle serverless
# connections terminated by Neon are recycled automatically instead of erroring.
# Neon SSL (sslmode=require) is passed through the DATABASE_URL itself, which
# psycopg2/SQLAlchemy handle natively — no connect_args change is required.
if _is_sqlite:
    connect_args = {"check_same_thread": False}
    engine_kwargs = {}
else:
    connect_args = {}
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 300,
    }

engine = create_engine(
    _database_url,
    connect_args=connect_args,
    **engine_kwargs,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
