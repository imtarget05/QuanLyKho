"""Retention for durable RetailOps checkpoints.

The PostgreSQL saver owns deletion across checkpoints, blobs and writes. We
select only thread IDs whose newest checkpoint is older than the cutoff.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import psycopg

logger = logging.getLogger(__name__)


async def prune_expired_threads(checkpointer, dsn: str, retention_days: int = 30) -> int:
    if retention_days < 1:
        raise ValueError("retention_days must be positive")
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        rows = await conn.execute(
            """SELECT thread_id FROM checkpoints
               GROUP BY thread_id
               HAVING max((checkpoint->>'ts')::timestamptz) < %s
               LIMIT 500""",
            (cutoff,),
        )
        thread_ids = [row[0] for row in await rows.fetchall()]
    for thread_id in thread_ids:
        await checkpointer.adelete_thread(thread_id)
    return len(thread_ids)


async def retention_loop(checkpointer, dsn: str, retention_days: int = 30) -> None:
    while True:
        try:
            total_deleted = 0
            while True:
                deleted = await prune_expired_threads(checkpointer, dsn, retention_days)
                total_deleted += deleted
                if deleted < 500:
                    break
            if total_deleted:
                logger.info("retail_agent_checkpoints_pruned count=%s", total_deleted)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("retail_agent_checkpoint_prune_failed")
        await asyncio.sleep(24 * 60 * 60)
