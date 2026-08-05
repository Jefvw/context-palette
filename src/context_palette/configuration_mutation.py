from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import threading
from collections.abc import Callable, Iterator
from typing import ParamSpec, TypeVar


_CONFIGURATION_MUTATION_LOCK = threading.RLock()
_P = ParamSpec("_P")
_R = TypeVar("_R")


@contextmanager
def configuration_mutation_gate() -> Iterator[None]:
    """Serialize application-owned configuration reads and mutations.

    The gate is reentrant so a logical multi-file operation can hold it while
    its individual persistence calls acquire it automatically.
    """

    with _CONFIGURATION_MUTATION_LOCK:
        yield


def gated_configuration_mutation(
    function: Callable[_P, _R],
) -> Callable[_P, _R]:
    """Hold the shared gate across one logical multi-file mutation."""

    @wraps(function)
    def gated(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        with configuration_mutation_gate():
            return function(*args, **kwargs)

    return gated
