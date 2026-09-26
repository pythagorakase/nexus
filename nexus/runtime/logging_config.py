"""One logging configuration for supervised services (issue #842).

The supervisor is the single file and rotation owner: it captures each
service's stdout+stderr in ``<state_dir>/<service>.log`` and rotates that file
at spawn. Services therefore log to stdout only — no FileHandler anywhere in a
service process — through one formatter shared by the application loggers
(root) and uvicorn's ``uvicorn``, ``uvicorn.error`` and ``uvicorn.access``
loggers.

``build_logging_config`` turns ``[runtime.logs]`` into a
``logging.config.dictConfig`` mapping. The supervisor writes it as JSON and
hands the path to uvicorn through the ``{log_config}`` argv placeholder
(``--log-config``), so uvicorn applies it before importing the app and its
own default config never replaces it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable

from nexus.config.settings_models import RuntimeLogsSettings

ACCESS_LOGGER = "uvicorn.access"
CONSOLE_HANDLER = "console"
STANDARD_FORMATTER = "standard"
SUCCESSFUL_ACCESS_FILTER = "successful_access"

# uvicorn's h11 and httptools protocols log each response on uvicorn.access as
# '%s - "%s %s HTTP/%s" %d' with args
# (client_addr, method, path_with_query_string, http_version, status_code).
_ACCESS_ARG_COUNT = 5
_ACCESS_PATH_INDEX = 2
_ACCESS_STATUS_INDEX = 4


class SuccessfulAccessFilter(logging.Filter):
    """Drop successful uvicorn access records for configured noisy paths.

    A record is dropped only when its request path (query string ignored) is
    in the exclusion set AND its status is below 400, so every 4xx and 5xx —
    including failures of an excluded health path — stays in the log.
    """

    def __init__(self, exclude_paths: Iterable[str]) -> None:
        """Store the exact request paths whose successes are suppressed."""
        super().__init__()
        self.exclude_paths = frozenset(exclude_paths)

    def filter(self, record: logging.LogRecord) -> bool:
        """Return False only for a successful access record on an excluded path."""
        args = record.args
        if not isinstance(args, tuple) or len(args) != _ACCESS_ARG_COUNT:
            raise TypeError(
                f"{ACCESS_LOGGER} record from {record.name!r} does not carry "
                "uvicorn's (client_addr, method, path, http_version, status) "
                f"args: {args!r}. The access-log shape changed; update "
                "SuccessfulAccessFilter."
            )
        path = args[_ACCESS_PATH_INDEX]
        status = args[_ACCESS_STATUS_INDEX]
        if not isinstance(path, str) or not isinstance(status, int):
            raise TypeError(
                f"{ACCESS_LOGGER} record args have unexpected types: path "
                f"{type(path).__name__}, status {type(status).__name__}"
            )
        if status >= 400:
            return True
        return path.split("?", 1)[0] not in self.exclude_paths


def build_logging_config(settings: RuntimeLogsSettings) -> Dict[str, Any]:
    """Build the ``dictConfig`` mapping for a supervised service.

    One stdout ``StreamHandler`` with one formatter serves root, ``uvicorn``,
    ``uvicorn.error`` (propagating to ``uvicorn``) and ``uvicorn.access``
    (with the successful-access filter). The mapping is JSON-serializable so
    the supervisor can write it for ``uvicorn --log-config``.
    """
    filter_factory = (
        f"{SuccessfulAccessFilter.__module__}.{SuccessfulAccessFilter.__qualname__}"
    )
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {STANDARD_FORMATTER: {"format": settings.format}},
        "filters": {
            SUCCESSFUL_ACCESS_FILTER: {
                "()": filter_factory,
                "exclude_paths": list(settings.access_success_exclude_paths),
            }
        },
        "handlers": {
            CONSOLE_HANDLER: {
                "class": "logging.StreamHandler",
                "formatter": STANDARD_FORMATTER,
                "stream": "ext://sys.stdout",
            }
        },
        "loggers": {
            "uvicorn": {
                "handlers": [CONSOLE_HANDLER],
                "level": settings.level,
                "propagate": False,
            },
            "uvicorn.error": {"level": settings.level, "propagate": True},
            ACCESS_LOGGER: {
                "handlers": [CONSOLE_HANDLER],
                "level": settings.level,
                "propagate": False,
                "filters": [SUCCESSFUL_ACCESS_FILTER],
            },
        },
        "root": {"handlers": [CONSOLE_HANDLER], "level": settings.level},
    }
