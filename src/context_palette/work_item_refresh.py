from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
import time
from typing import Callable

from .work_items import (
    DiscoveredWorkItem,
    WorkItemDiscoveryError,
    WorkItemSource,
    discover_work_items,
)


@dataclass(frozen=True, slots=True)
class SourceRefreshResult:
    source: WorkItemSource
    items: tuple[DiscoveredWorkItem, ...]
    error: str | None = None
    using_last_known_good: bool = False


@dataclass(frozen=True, slots=True)
class WorkItemIndex:
    sources: tuple[SourceRefreshResult, ...] = ()
    elapsed_seconds: float = 0.0

    @property
    def items(self) -> tuple[DiscoveredWorkItem, ...]:
        return tuple(item for source in self.sources for item in source.items)


def refresh_work_item_index(
    sources: tuple[WorkItemSource, ...],
    previous: WorkItemIndex | None = None,
    *,
    discoverer: Callable[[WorkItemSource], tuple[DiscoveredWorkItem, ...]] = discover_work_items,
) -> WorkItemIndex:
    started = time.perf_counter()
    previous_by_id = {
        result.source.id.casefold(): result for result in (previous.sources if previous else ())
    }
    results: list[SourceRefreshResult] = []
    for source in sources:
        try:
            items = discoverer(source)
        except WorkItemDiscoveryError as exc:
            last_good = previous_by_id.get(source.id.casefold())
            results.append(
                SourceRefreshResult(
                    source,
                    last_good.items if last_good is not None else (),
                    str(exc),
                    last_good is not None,
                )
            )
        else:
            results.append(SourceRefreshResult(source, items))
    return WorkItemIndex(tuple(results), time.perf_counter() - started)


class WorkItemRefreshCoordinator:
    """Run discovery off-thread and expose completion only through main-thread drain."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._completed: queue.SimpleQueue[
            tuple[WorkItemIndex, Callable[[WorkItemIndex], None]]
        ] = queue.SimpleQueue()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def completion_pending(self) -> bool:
        return not self._completed.empty()

    def start(
        self,
        sources: tuple[WorkItemSource, ...],
        previous: WorkItemIndex | None,
        on_complete: Callable[[WorkItemIndex], None],
    ) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True

        def work() -> None:
            result = refresh_work_item_index(sources, previous)
            self._completed.put((result, on_complete))

        threading.Thread(target=work, daemon=True, name="work-item-refresh").start()
        return True

    def drain(self) -> bool:
        """Deliver one completed refresh; callers must invoke this on the UI thread."""
        try:
            result, on_complete = self._completed.get_nowait()
        except queue.Empty:
            return False
        try:
            on_complete(result)
        finally:
            with self._lock:
                self._running = False
        return True
