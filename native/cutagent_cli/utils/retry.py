"""Retry decorator for flaky DaVinci Resolve API calls."""

from __future__ import annotations

import functools
import logging
import time
from typing import Callable, TypeVar

T = TypeVar("T")
logger = logging.getLogger("cutagent-cli")


def retry(
    max_attempts: int = 3,
    delay: float = 0.2,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Callable | None = None,
):
    """
    Retry decorator with exponential backoff.
    
    Also retries when the function returns None (common DaVinci Resolve API behavior).
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            current_delay = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    if result is not None:
                        return result
                    if attempt < max_attempts:
                        logger.debug(
                            "%s returned None (attempt %d/%d), retrying in %.1fs",
                            func.__name__, attempt, max_attempts, current_delay,
                        )
                        if on_retry:
                            on_retry()
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        return result
                except exceptions as exc:
                    if attempt < max_attempts:
                        logger.debug(
                            "%s raised %s (attempt %d/%d), retrying in %.1fs",
                            func.__name__, exc, attempt, max_attempts, current_delay,
                        )
                        if on_retry:
                            on_retry()
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        raise
            return None  # type: ignore

        return wrapper

    return decorator
