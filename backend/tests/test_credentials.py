import pytest
from sqlalchemy import select
from app.models.database import AsyncSessionLocal, init_db
from app.models.models import User
from app.core.security import verify_password

@pytest.mark.asyncio
async def test_staff_credentials_seeded():
    await init_db()
    async with AsyncSessionLocal() as session:
        res_admin = await session.execute(select(User).where(User.username == "admin"))
        admin = res_admin.scalar_one_or_none()
        assert admin is not None
        assert verify_password("Admin123!", admin.hashed_password) is True

        res_nurse = await session.execute(select(User).where(User.username == "nurse"))
        nurse = res_nurse.scalar_one_or_none()
        assert nurse is not None
        assert verify_password("Nurse123!", nurse.hashed_password) is True
