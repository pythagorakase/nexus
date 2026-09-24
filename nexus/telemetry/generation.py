"""Task-local generation phase reporting, independent of provider transport."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_reporter: ContextVar[Callable[[str], None] | None] = ContextVar(
    "generation_phase_reporter", default=None
)


@contextmanager
def generation_progress(reporter: Callable[[str], None]) -> Iterator[None]:
    """Install the durable owner for this attempt and its child tasks."""
    token = _reporter.set(reporter)
    try:
        yield
    finally:
        _reporter.reset(token)


def report_generation_phase(phase: str) -> None:
    """Report an actual phase boundary when a durable owner is present."""
    reporter = _reporter.get()
    if reporter is not None:
        reporter(phase)
