"""Inventory repository - truy cập dữ liệu kho."""

from uuid import UUID

from sqlalchemy import select

from app.models.inventory import (
    Balance,
    Item,
    Location,
    Movement,
    Stocktake,
    StocktakeLine,
)
from app.repositories.base import BaseRepository


class ItemRepository(BaseRepository[Item]):
    """Repository cho mặt hàng."""

    async def add(self, entity: Item) -> Item:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id: str | UUID) -> Item | None:
        result = await self.session.execute(
            select(Item).where(Item.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_sku(self, sku: str) -> Item | None:
        result = await self.session.execute(
            select(Item).where(Item.sku == sku)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 50,
        active_only: bool = True,
    ) -> list[Item]:
        query = select(Item)
        if active_only:
            query = query.where(Item.active.is_(True))
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class LocationRepository(BaseRepository[Location]):
    """Repository cho kho/địa điểm."""

    async def add(self, entity: Location) -> Location:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id: str | UUID) -> Location | None:
        result = await self.session.execute(
            select(Location).where(Location.id == id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 50,
        active_only: bool = True,
    ) -> list[Location]:
        query = select(Location)
        if active_only:
            query = query.where(Location.active.is_(True))
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
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


class BalanceRepository(BaseRepository[Balance]):
    """Repository cho số dồn tồn kho."""

    async def add(self, entity: Balance) -> Balance:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id: str | UUID) -> Balance | None:
        return None  # Balance không có id đơn lẻ, dùng composite key

    async def list(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Balance]:
        result = await self.session.execute(
            select(Balance).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_location_item(
        self,
        location_id: str,
        item_id: str,
    ) -> Balance | None:
        """Lấy số dồn theo (location, item)."""
        result = await self.session.execute(
            select(Balance).where(
                Balance.location_id == location_id,
                Balance.item_id == item_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        location_id: str,
        item_id: str,
        quantity: float,
    ) -> Balance:
        """Upsert số lượng tồn - tạo mới hoặc cập nhật."""
        from app.domain.inventory import Quantity

        existing = await self.get_by_location_item(location_id, item_id)
        if existing:
            existing.quantity = Quantity(existing.quantity.value + Quantity(quantity).value)
            existing.version += 1
            await self.session.flush()
            return existing
        else:
            new_balance = Balance(
                location_id=location_id,
                item_id=item_id,
                quantity=Quantity(quantity),
                version=1,
            )
            self.session.add(new_balance)
            await self.session.flush()
            return new_balance


class MovementRepository(BaseRepository[Movement]):
    """Repository cho sổ biến động kho."""

    async def add(self, entity: Movement) -> Movement:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id: str | UUID) -> Movement | None:
        result = await self.session.execute(
            select(Movement).where(Movement.id == id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 50,
        item_id: str | None = None,
        location_id: str | None = None,
    ) -> list[Movement]:
        query = select(Movement)
        if item_id:
            query = query.where(Movement.item_id == item_id)
        if location_id:
            query = query.where(Movement.location_id == location_id)
        query = query.order_by(Movement.posted_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class StocktakeRepository(BaseRepository[Stocktake]):
    """Repository cho phiên kiểm kê."""

    async def add(self, entity: Stocktake) -> Stocktake:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id: str | UUID) -> Stocktake | None:
        result = await self.session.execute(
            select(Stocktake).where(Stocktake.id == id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 50,
        location_id: str | None = None,
        status: str | None = None,
    ) -> list[Stocktake]:
        query = select(Stocktake)
        if location_id:
            query = query.where(Stocktake.location_id == location_id)
        if status:
            query = query.where(Stocktake.status == status)
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_open_by_location_shift(
        self,
        location_id: str,
        business_date,
        shift_code: str,
    ) -> Stocktake | None:
        """Lấy ca kiểm kê đang mở theo (kho, ngày, ca)."""
        result = await self.session.execute(
            select(Stocktake).where(
                Stocktake.location_id == location_id,
                Stocktake.business_date == business_date,
                Stocktake.shift_code == shift_code,
                Stocktake.status == "open",
            )
        )
        return result.scalar_one_or_none()


class StocktakeLineRepository(BaseRepository[StocktakeLine]):
    """Repository cho dòng kiểm kê."""

    async def add(self, entity: StocktakeLine) -> StocktakeLine:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, id: str | UUID) -> StocktakeLine | None:
        result = await self.session.execute(
            select(StocktakeLine).where(StocktakeLine.id == id)
        )
        return result.scalar_one_or_none()

    async def list_by_stocktake(
        self,
        stocktake_id: str,
    ) -> list[StocktakeLine]:
        result = await self.session.execute(
            select(StocktakeLine).where(StocktakeLine.stocktake_id == stocktake_id)
        )
        return list(result.scalars().all())
