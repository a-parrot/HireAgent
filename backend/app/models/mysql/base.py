from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared base for business models; migrations are managed by Alembic."""
