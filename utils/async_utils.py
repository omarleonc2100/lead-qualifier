"""
Utilidades para operaciones asincrónicas.
Incluye retry logic con backoff exponencial.
"""

import asyncio
import functools
from typing import TypeVar, Callable, Any, Optional
from utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


def async_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
):
    """
    Decorador para reintentar funciones asincrónicas con backoff exponencial.

    Args:
        max_attempts: Número máximo de intentos
        initial_delay: Delay inicial en segundos
        backoff_factor: Factor multiplicativo del delay
        max_delay: Delay máximo en segundos

    Example:
        @async_retry(max_attempts=3, initial_delay=1.0)
        async def my_api_call():
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = initial_delay
            last_exception: Optional[Exception] = None

            for attempt in range(1, max_attempts + 1):
                try:
                    logger.debug(
                        "async_retry_attempt",
                        func_name=func.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts
                    )
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if attempt < max_attempts:
                        actual_delay = min(delay, max_delay)
                        logger.warning(
                            "async_retry_failed",
                            func_name=func.__name__,
                            attempt=attempt,
                            error=str(e),
                            next_retry_in=actual_delay
                        )
                        await asyncio.sleep(actual_delay)
                        delay *= backoff_factor
                    else:
                        logger.error(
                            "async_retry_exhausted",
                            func_name=func.__name__,
                            max_attempts=max_attempts,
                            error=str(e)
                        )

            raise last_exception or Exception(f"Failed to execute {func.__name__}")

        return wrapper

    return decorator
