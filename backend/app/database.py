import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

DB_PATH = os.path.join(os.path.dirname(__file__), "mlforge.db")
DATABASE_URL = os.environ.get("MLFORGE_DATABASE_URL", f"sqlite:///{DB_PATH}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_light_migrations():
    """Adds columns introduced after the DB already existed (team auth
    fields). There's no Alembic in this project, so this is a deliberately
    tiny stand-in: each ALTER TABLE is wrapped so it's a silent no-op once
    the column exists. Safe to call on every startup."""
    statements = [
        "ALTER TABLE teams ADD COLUMN password_hash TEXT",
        "ALTER TABLE teams ADD COLUMN password_salt TEXT",
        "ALTER TABLE teams ADD COLUMN team_code TEXT",
        "ALTER TABLE teams ADD COLUMN token TEXT",
    ]
    with engine.connect() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                conn.rollback()  # column already exists — expected after the first run
