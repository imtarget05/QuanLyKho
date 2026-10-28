"""Session repository - quản lý phiên đăng nhập."""


from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository):
    """Repository cho phiên đăng nhập người dùng."""

    def __init__(self, session: AsyncSession):
        super().__init__(session)
        # In-memory storage để minh họa; trong production nên dùng DB
        self._sessions: dict[str, dict] = {}

    async def create_session(self, user_id: str, token: str) -> dict:
        """Tạo phiên mới."""
        self._sessions[token] = {
            "user_id": user_id,
            "token": token,
            "created_at": "2026-10-27T00:00:00Z",
        }
        return self._sessions[token]

    async def delete_session(self, token: str) -> bool:
        """Xóa phiên."""
        if token in self._sessions:
            del self._sessions[token]
            return True
        return False

    async def get_session(self, token: str) -> dict | None:
        """Lấy thông tin phiên."""
        return self._sessions.get(token)
