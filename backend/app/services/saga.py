"""Saga Orchestrator + bù trừ (interview-prep 02/05 §4, §5.2).

Orchestrator tập trung lưu trạng thái saga trong DB. Mỗi bước có action_fn và
compensate_fn. Khi bước k thất bại, orchestrator chạy bù trừ cho các bước
k-1 .. 1 theo thứ tự ngược lại (compensating transaction).

saga_id đóng vai trò idempotency key: chạy lại saga_id đã hoàn thành không
xử lý lại.

Mẫu TCC (Try–Confirm–Cancel):
  - Try:    phong tỏa số dư (reserve_balance).
  - Confirm: trừ nguồn + cộng đích + giải tỏa (commit_reservation).
  - Cancel: hủy phong tỏa (release_reservation).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.saga import CompensatingLog, SagaInstance, SagaStep
from app.services.saga_orchestrator import (
    SagaContext,
    SagaResult,
)
from app.services.saga_orchestrator import (
    SagaOrchestrator as ModernSagaOrchestrator,
)


class SagaError(Exception):
    """Lỗi trong khi thực thi Saga (kèm thông tin bước thất bại)."""

    def __init__(self, message: str, step_name: str | None = None):
        super().__init__(message)
        self.step_name = step_name


class SagaOrchestrator:
    """Điều phối chuỗi bước saga với bù trừ khi thất bại."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def execute_saga(
        self,
        saga_name: str,
        steps: list[Any],
        context: SagaContext | None = None,
        saga_id: str | None = None,
    ) -> SagaResult:
        """Executes saga using the ModernSagaOrchestrator engine."""
        modern = ModernSagaOrchestrator(self.session)
        return await modern.execute_saga(
            saga_name=saga_name,
            steps=steps,
            context=context,
            saga_id=saga_id,
        )

    async def execute(
        self,
        *,
        saga_id: str,
        saga_type: str,
        steps: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Thực thi saga.

        `steps`: danh sách {"name", "action", "compensate"} theo thứ tự thực thi.
        `action` / `compensate`: callable async (session, context) -> Any.
        Trả về dict {"saga_id", "saga_type", "status", "current_step", "context"}.
        """
        saga = await self._get_or_create_saga(saga_id, saga_type, context or {})

        # Idempotent: saga đã kết thúc không xử lý lại.
        if saga.status in {"completed", "failed"}:
            return self._serialize(saga)

        saga.status = "running"
        await self.session.flush()

        context = dict(saga.context_json or {})
        executed: list[tuple[SagaStep, Callable | None]] = []
        try:
            for step_def in steps:
                step_name = step_def["name"]
                action_fn = step_def["action"]
                compensate_fn = step_def.get("compensate")

                step = SagaStep(
                    saga_id=saga.id,
                    step_name=step_name,
                    status="pending",
                    action_json={},
                    compensate_json={},
                )
                self.session.add(step)
                await self.session.flush()

                saga.current_step = step_name
                await self.session.flush()

                try:
                    result = await action_fn(self.session, context)
                    step.action_json = (
                        result if isinstance(result, dict) else {"result": result}
                    )
                    step.status = "done"
                    step.completed_at = datetime.now(UTC)
                except Exception as exc:  # noqa: BLE001
                    step.status = "failed"
                    step.action_json = {"error": str(exc)}
                    await self.session.flush()
                    raise SagaError(str(exc), step_name=step_name) from exc

                if compensate_fn is not None:
                    try:
                        comp_result = await compensate_fn(self.session, context)
                        step.compensate_json = (
                            comp_result
                            if isinstance(comp_result, dict)
                            else {"result": comp_result}
                        )
                    except Exception as exc:  # noqa: BLE001
                        step.compensate_json = {"error": str(exc)}
                await self.session.flush()
                executed.append((step, compensate_fn))

            saga.status = "completed"
            await self.session.flush()
            return self._serialize(saga, context)

        except SagaError as exc:
            await self._compensate(saga, executed, exc.step_name, context)
            saga.status = "failed"
            await self.session.flush()
            raise exc
        except Exception as exc:  # noqa: BLE001
            await self._compensate(saga, executed, None, context)
            saga.status = "failed"
            await self.session.flush()
            raise SagaError(f"Saga {saga_id} thất bại: {exc}") from exc

    async def _get_or_create_saga(
        self, saga_id: str, saga_type: str, context: dict[str, Any]
    ) -> SagaInstance:
        result = await self.session.execute(
            select(SagaInstance).where(SagaInstance.id == UUID(saga_id))
        )
        saga = result.scalars().first()
        if saga is None:
            saga = SagaInstance(
                id=UUID(saga_id),
                saga_type=saga_type,
                status="pending",
                current_step=None,
                context_json=context,
            )
            self.session.add(saga)
            await self.session.flush()
        elif saga.status == "pending" and context:
            saga.context_json = {**saga.context_json, **context}
            await self.session.flush()
        return saga

    async def _compensate(
        self,
        saga: SagaInstance,
        executed: list[tuple[SagaStep, Callable | None]],
        failed_step: str | None,
        context: dict[str, Any],
    ) -> None:
        """Chạy bù trừ cho các bước đã done theo thứ tự ngược lại."""
        context = dict(context)
        context["failed_step"] = failed_step

        for step, compensate_fn in reversed(executed):
            if step.status != "done":
                continue
            detail: dict[str, Any] = {
                "step": step.step_name,
                "failed_step": failed_step,
            }
            if compensate_fn is None:
                detail["compensate_available"] = False
            log = CompensatingLog(
                saga_id=saga.id,
                step_name=step.step_name,
                action="compensate",
                status="pending",
                detail_json=detail,
            )
            self.session.add(log)
            await self.session.flush()

            compensated = False
            if compensate_fn is not None:
                try:
                    comp_result = await compensate_fn(self.session, context)
                    compensated = True
                    detail["compensate_available"] = True
                    detail["result"] = (
                        comp_result if isinstance(comp_result, dict) else {"result": comp_result}
                    )
                    log.status = "done"
                except Exception as exc:  # noqa: BLE001
                    detail["error"] = str(exc)
                    log.status = "failed"
            else:
                log.status = "done"  # không có hàm bù trừ -> coi như bỏ qua
                compensated = True

            step.status = "compensated" if compensated else "failed"
            log.detail_json = detail
            await self.session.flush()

    @staticmethod
    def _serialize(saga: SagaInstance, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "saga_id": str(saga.id),
            "saga_type": saga.saga_type,
            "status": saga.status,
            "current_step": saga.current_step,
            "context": saga.context_json or context or {},
        }
