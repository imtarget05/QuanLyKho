"""Location repository - truy cập dữ liệu kho/địa điểm."""


from sqlalchemy import select

from app.models.inventory import Location
from app.repositories.base import BaseRepository


class LocationRepository(BaseRepository[Location]):
    """Repository cho địa điểm (kho)."""

    async def add(self, entity: Location) -> Location:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id: str) -> Location | None:
        result = await self.session.execute(
            select(Location).where(Location.id == id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Location]:
        result = await self.session.execute(
            select(Location).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_code(self, code: str) -> Location | None:
        """Lấy location theo mã."""
        result = await self.session.execute(
            select(Location).where(Location.code == code)
        )
        return result.scalar_one_or_none()

    async def delete(self, id: str) -> bool:
        entity = await self.get(id)
        if entity:
            await self.session.delete(entity)
            await self.session.flush()
            return True
        return False
