"""SQLAlchemy async database setup and base model."""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    # Always off, regardless of environment: SQLAlchemy's echo dumps full query
    # parameters — including patient statements — to stdout. Clinical content must
    # never land in ordinary application logs (spec §31).
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables on startup and seed initial staff users if database is empty."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await seed_initial_staff()


async def seed_initial_staff():
    """Automatically seed default staff credentials if no staff exists (enables repo markers to log in immediately)."""
    from sqlalchemy import select
    from app.models.models import User, UserRole
    from app.core.security import hash_password

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.role.in_([UserRole.ADMIN, UserRole.NURSE]))
        )
        if not result.scalars().first():
            admin_user = User(
                username="admin",
                hashed_password=hash_password("Admin123!"),
                role=UserRole.ADMIN,
                full_name="System Administrator",
            )
            nurse_user = User(
                username="nurse",
                hashed_password=hash_password("Nurse123!"),
                role=UserRole.NURSE,
                full_name="Triage Nurse",
            )
            session.add(admin_user)
            session.add(nurse_user)
            await session.commit()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
