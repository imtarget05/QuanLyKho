"""Role repository - truy cập dữ liệu vai trò (IAM)."""


from sqlalchemy import select

from app.models.iam import Role
from app.repositories.base import BaseRepository


class RoleRepository(BaseRepository[Role]):
    """Repository cho vai trò."""

    async def add(self, entity: Role) -> Role:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id: str) -> Role | None:
        result = await self.session.execute(
            select(Role).where(Role.code == id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Role]:
        result = await self.session.execute(
            select(Role).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_code(self, code: str) -> Role | None:
        """Lấy role theo mã."""
        result = await self.session.execute(
            select(Role).where(Role.code == code)
        )
        return result.scalar_one_or_none()

    async def delete(self, id: str) -> bool:
        entity = await self.get(id)
        if entity:
            await self.session.delete(entity)
            await self.session.flush()
            return True
        return False
