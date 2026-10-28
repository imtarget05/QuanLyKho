"""Base repository - CRUD operations cơ bản."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """Base repository với các phương thức CRUD cơ bản."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @abstractmethod
    async def add(self, entity: T) -> T:
        ...

    @abstractmethod
    async def get(self, id: str | UUID) -> T | None:
        ...

    @abstractmethod
    async def list(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[T]:
        ...

    @abstractmethod
    async def delete(self, id: str | UUID) -> bool:
        ...