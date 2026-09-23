"""A scheduler-local checkpoint at every provider request, including retries."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_checkpoint: ContextVar[Callable[[], None] | None] = ContextVar(
    "deferred_work_checkpoint", default=None
)

_reporter: ContextVar[Callable[[str], None] | None] = ContextVar(
    "deferred_work_reporter", default=None
)


_lease_tracker: ContextVar[Callable[..., None] | None] = ContextVar(
    "deferred_work_lease_tracker", default=None
)


class SchedulerStopped(BaseException):
    """Leave leased work recoverable without charging a failed job attempt."""


@contextmanager
def provider_gate(
    checkpoint: Callable[[], None],
    reporter: Callable[[str], None],
    lease_tracker: Callable[..., None] | None = None,
) -> Iterator[None]:
    """Install the slot owner's checkpoint only in its execution context."""
    token = _checkpoint.set(checkpoint)
    reporter_token = _reporter.set(reporter)
    lease_token = _lease_tracker.set(lease_tracker)
    try:
        yield
    finally:
        _checkpoint.reset(token)
        _reporter.reset(reporter_token)
        _lease_tracker.reset(lease_token)


def before_provider_call() -> None:
    """Yield deferred work before a request; interactive calls have no gate."""
    checkpoint = _checkpoint.get()
    if checkpoint is not None:
        checkpoint()


def report_leased_job(queue: str, job_id: int) -> None:
    """Publish the exact leased domain job without coupling queues to an owner."""
    reporter = _reporter.get()
    if reporter is not None:
        reporter(f"{queue}:{job_id}")


def track_job_lease(
    queue: str, job_id: int, *, locked_by: str, lease_nonce: str, duration: float
) -> None:
    """Give the scheduler the exact nonce to renew while preempted."""
    tracker = _lease_tracker.get()
    if tracker is not None:
        tracker(
            queue,
            job_id,
            locked_by=locked_by,
            lease_nonce=str(lease_nonce),
            duration=duration,
        )
