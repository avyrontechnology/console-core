"""Async execution helpers for Celery workers.

Celery's default ``prefork`` pool runs tasks inside forked, single-threaded
worker processes (``ForkPoolWorker-N``). Mixing that with async SQLAlchemy +
asyncpg has two sharp edges:

1. ``asyncio.run(coro)`` creates a BRAND-NEW event loop on every call and
   closes it afterwards. asyncpg connections are bound to the loop they were
   created on, but SQLAlchemy's connection pool (a process-wide singleton)
   caches them across tasks. The next task opens a new loop and gets handed a
   connection bound to the now-closed loop, raising::

       asyncpg ... cannot perform operation: another operation is in progress

2. If the engine/pool is created in the parent process before ``fork()``, every
   child inherits the same TCP sockets and corrupts each other's traffic.

This module fixes both by giving each worker process a single, long-lived event
loop (so pooled connections stay bound to one stable loop) and by resetting the
DB engine right after fork (so each child builds its own pool).
"""

import asyncio
import inspect
from typing import Coroutine

from celery.signals import worker_process_init, worker_process_shutdown

from src.core.container import Container
from src.loggers.console_celery_logger import CeleryLogger

celery_logger = CeleryLogger.get_logger()

# One persistent event loop per worker (child) process.
_loop: asyncio.AbstractEventLoop | None = None


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """Return this worker process's persistent event loop, creating it if needed."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def _warm_async_resources(loop: asyncio.AbstractEventLoop) -> None:
    """Initialize the async ``providers.Resource`` graph (the redis pool) on
    this worker's loop, so a later synchronous ``@inject`` can resolve a
    redis-backed provider from cache instead of trying to lazily initialize
    the resource itself.

    Why this is needed: ``redis_pool`` is an async ``providers.Resource``.
    dependency-injector resolves an ``@inject``'d provider synchronously at task
    CALL time (before the task body). If the resource isn't initialized yet, it
    is initialized via ``asyncio.ensure_future()``, which calls
    ``asyncio.get_event_loop()``. Several tasks run their coroutine with
    ``asyncio.run(...)``, which resets the thread's current loop to ``None`` on
    completion, so the next such injection raised:

        RuntimeError: There is no current event loop in thread 'MainThread'.

    Warming (and caching) the resource here removes that lazy-init path
    entirely — the injection returns the already-initialized resource with no
    ``ensure_future`` / ``get_event_loop`` call. Both the declarative container
    and the wired instance are warmed so whichever provider ``@inject`` binds to
    is covered. Any failure falls back to a warning (the resource still
    lazily initializes on first real use)."""
    containers = [Container]
    try:
        # Lazy import to avoid a circular import (celery_app imports this module).
        from src.console_celery.celery_app import celery

        instance = getattr(celery, "container", None)
        if instance is not None:
            containers.append(instance)
    except Exception as exc:  # pragma: no cover - defensive
        celery_logger.warning(f"Could not access wired container to warm resources: {exc}")

    warmed_provider_ids: set[int] = set()
    for container in containers:
        provider = getattr(container, "redis_pool", None)
        if provider is None or id(provider) in warmed_provider_ids:
            continue
        warmed_provider_ids.add(id(provider))
        try:
            result = provider()
            if inspect.isawaitable(result):
                loop.run_until_complete(result)
            celery_logger.info("Warmed redis_pool resource for worker")
        except Exception as exc:
            celery_logger.warning(f"Could not warm redis_pool on worker init: {exc}")


@worker_process_init.connect
def init_worker_process(**_kwargs) -> None:
    """Run inside each forked worker AFTER fork.

    Resets the DB engine singleton so the child does not share asyncpg
    connections/sockets inherited from the parent, then creates this process's
    dedicated event loop.
    """
    try:
        # Workers must not reuse pooled connections (see db.USE_NULL_POOL). Flip
        # the flag BEFORE resetting so the engine is rebuilt with NullPool.
        import src.core.db as db_module

        db_module.USE_NULL_POOL = True
        # Drop any engine/pool that may have been built in the parent process.
        Container.db.reset()
    except Exception as exc:
        celery_logger.warning(f"Could not reset DB provider on worker init: {exc}")

    loop = _ensure_loop()
    _warm_async_resources(loop)
    celery_logger.info("Celery worker process initialized with dedicated event loop")


@worker_process_shutdown.connect
def shutdown_worker_process(**_kwargs) -> None:
    """Dispose the engine and close the loop cleanly when a worker process exits."""
    global _loop
    if _loop is None or _loop.is_closed():
        return
    try:
        db = Container.db()
        _loop.run_until_complete(db.close())
    except Exception as exc:
        celery_logger.warning(f"Error disposing DB engine on worker shutdown: {exc}")
    finally:
        _loop.close()
        _loop = None


def run_async(coro: Coroutine):
    """Run a coroutine on this worker's persistent event loop.

    Drop-in replacement for ``asyncio.run`` inside Celery tasks. Unlike
    ``asyncio.run`` it reuses one loop for the lifetime of the worker process,
    so pooled asyncpg connections stay valid across tasks.
    """
    return _ensure_loop().run_until_complete(coro)
