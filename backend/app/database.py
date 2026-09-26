from __future__ import annotations

from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import ensure_data_directories, settings

ensure_data_directories()

DATABASE_URL = URL.create("sqlite", database=str(settings.database_path)).render_as_string(hide_password=False)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
