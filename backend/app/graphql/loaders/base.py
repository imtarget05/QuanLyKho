"""DataLoader tối giản (không thêm dependency) cho A6.

Semantics giống `aiodataloader`: mọi `load()` được gọi trong cùng một lượt của
event loop (trước khi loop trả quyền) sẽ được gom vào **một** `batch_load_fn`.
Cache sống theo instance; vì mỗi request tạo instance mới nên không rò dữ liệu
giữa các request.
"""

from __future__ import annotations

import asyncio
from typing import Any, Generic, TypeVar

Key = TypeVar("Key")
Value = TypeVar("Value")


class BatchLoader(Generic[Key, Value]):
    """Batched, per-request cache loader."""

    def __init__(self) -> None:
        self._cache: dict[Key, Value] = {}
        self._futures: dict[Key, asyncio.Future[Value]] = {}
        self._queue: list[Key] = []
        self._dispatch_handle: asyncio.Handle | None = None

    # -- API ---------------------------------------------------------------
    def prime(self, key: Key, value: Value) -> None:
        """Nạp sẵn giá trị đã biết để tránh round-trip."""
        self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()

    def load(self, key: Key) -> asyncio.Future[Value]:
        """Trả Future cho `key`; các key cùng lượt sẽ được batch lại."""
        loop = asyncio.get_running_loop()
        if key in self._cache:
            future: asyncio.Future[Value] = loop.create_future()
            future.set_result(self._cache[key])
            return future
        if key in self._futures:
            return self._futures[key]

        future = loop.create_future()
        self._futures[key] = future
        self._queue.append(key)
        if self._dispatch_handle is None:
            self._dispatch_handle = loop.call_soon(self._dispatch)
        return future

    async def load_many(self, keys: list[Key]) -> list[Value]:
        return list(await asyncio.gather(*(self.load(key) for key in keys)))

    # -- internals ---------------------------------------------------------
    def _dispatch(self) -> None:
        self._dispatch_handle = None
        if not self._queue:
            return
        keys = list(self._queue)
        self._queue.clear()
        futures = {key: self._futures.pop(key) for key in keys}
        asyncio.get_running_loop().create_task(self._run_batch(keys, futures))

    async def _run_batch(
        self, keys: list[Key], futures: dict[Key, asyncio.Future[Value]]
    ) -> None:
        try:
            values = await self.batch_load_fn(keys)
            if len(values) != len(keys):
                raise ValueError(
                    f"batch_load_fn trả {len(values)} giá trị cho {len(keys)} khoá"
                )
        except BaseException as exc:  # noqa: BLE001 - forward mọi lỗi cho mọi future
            for future in futures.values():
                if not future.done():
                    future.set_exception(exc)
            return
        for key, value in zip(keys, values, strict=True):
            self._cache[key] = value
            future = futures.get(key)
            if future is not None and not future.done():
                future.set_result(value)

    async def batch_load_fn(self, keys: list[Key]) -> list[Any]:
        raise NotImplementedError
