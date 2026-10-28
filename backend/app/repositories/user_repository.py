"""User repository - truy cập dữ liệu người dùng (IAM)."""

from uuid import UUID

from sqlalchemy import select

from app.models.iam import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository cho người dùng."""

    async def add(self, entity: User) -> User:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id: str | UUID) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[User]:
        result = await self.session.execute(
            select(User).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_username(self, username: str) -> User | None:
        """Lấy user theo username."""
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def delete(self, id: str | UUID) -> bool:
        entity = await self.get(id)
        if entity:
            await self.session.delete(entity)
            await self.session.flush()
            return True
        return False
