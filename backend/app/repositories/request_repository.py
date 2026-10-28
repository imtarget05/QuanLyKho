"""Request (invoice) repository - truy cập dữ liệu phiếu nhập - xuất."""

from uuid import UUID

from sqlalchemy import select

from app.models.inventory import InventoryRequest, InventoryRequestLine
from app.repositories.base import BaseRepository


class InventoryRequestRepository(BaseRepository[InventoryRequest]):
    """Repository cho phiếu nhập - xuất kho."""

    async def add(self, entity: InventoryRequest) -> InventoryRequest:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id: str | UUID) -> InventoryRequest | None:
        result = await self.session.execute(
            select(InventoryRequest).where(InventoryRequest.id == id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 50,
        status: str | None = None,
        kind: str | None = None,
        location_id: str | None = None,
        user_id: str | None = None,
    ) -> list[InventoryRequest]:
        query = select(InventoryRequest)
        if status:
            query = query.where(InventoryRequest.status == status)
        if kind:
            query = query.where(InventoryRequest.kind == kind)
        if location_id:
            query = query.where(InventoryRequest.location_id == location_id)
        if user_id:
            query = query.where(InventoryRequest.user_id == user_id)
        query = query.order_by(InventoryRequest.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_number(self, number: str) -> InventoryRequest | None:
        """Lấy phiếu theo số (tendocument)."""
        result = await self.session.execute(
            select(InventoryRequest).where(InventoryRequest.number == number)
        )
        return result.scalar_one_or_none()


class InventoryRequestLineRepository(BaseRepository[InventoryRequestLine]):
    """Repository cho dòng phiếu nhập - xuất."""

    async def add(self, entity: InventoryRequestLine) -> InventoryRequestLine:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id: str | UUID) -> InventoryRequestLine | None:
        result = await self.session.execute(
            select(InventoryRequestLine).where(InventoryRequestLine.id == id)
        )
        return result.scalar_one_or_none()

    async def list_by_request(
        self,
        request_id: str,
    ) -> list[InventoryRequestLine]:
        result = await self.session.execute(
            select(InventoryRequestLine).where(InventoryRequestLine.request_id == request_id)
        )
        return list(result.scalars().all())

    async def list_by_lines(
        self,
        request_ids: list[str],
    ) -> list[InventoryRequestLine]:
        result = await self.session.execute(
            select(InventoryRequestLine).where(InventoryRequestLine.request_id.in_(request_ids))
        )
        return list(result.scalars().all())