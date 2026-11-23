import os
from dotenv import load_dotenv
from app.paths import BASE_DIR
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'library.db').as_posix()}")
# Neon/Render memberi "postgresql://..."; SQLAlchemy butuh driver psycopg (v3) secara eksplisit.
if DATABASE_URL.startswith(("postgres://", "postgresql://")):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.split("://", 1)[1]

# check_same_thread hanya dikenal SQLite, jadi jangan dikirim ke PostgreSQL
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine_kwargs = {"pool_pre_ping": True}
if os.getenv("VERCEL") and DATABASE_URL.startswith("postgresql"):
    # Serverless + pooler Neon (pgbouncer mode transaksi): pool kecil, tanpa prepared statement.
    connect_args = {"prepare_threshold": None}
    engine_kwargs.update(pool_size=1, max_overflow=2, pool_recycle=300)

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()