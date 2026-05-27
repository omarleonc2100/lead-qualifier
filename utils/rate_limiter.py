"""
Rate limiter distribuido.
Controla el flujo de requests a APIs externas.
"""

from typing import Dict
from datetime import datetime, timedelta, timezone
from utils.logger import get_logger
import asyncio

logger = get_logger(__name__)


class RateLimiter:
    """
    Rate limiter para controlar llamadas a APIs externas.

    ESTRATEGIA:
    - Por usuario: máximo N requests por minuto
    - Global: máximo M requests por segundo a APIs
    """

    def __init__(
        self,
        per_user_limit: int = 10,  # 10 por minuto
        global_limit: int = 5,     # 5 por segundo
    ):
        """
        Inicializa el rate limiter.

        Args:
            per_user_limit: Máximo de requests por usuario por minuto
            global_limit: Máximo de requests globales por segundo
        """
        self.per_user_limit = per_user_limit
        self.global_limit = global_limit

        # Timestamps de requests por usuario
        self._user_requests: Dict[int, list] = {}

        # Timestamps de requests globales
        self._global_requests: list = []

        # Lock para thread-safety
        self._lock = asyncio.Lock()

        logger.info(
            "rate_limiter_initialized",
            per_user_limit=per_user_limit,
            global_limit=global_limit
        )

    async def check_user_limit(self, user_id: int) -> bool:
        """
        Verifica si el usuario puede hacer otro request.

        Args:
            user_id: ID del usuario

        Returns:
            True si puede proceder, False si excedió límite
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            one_minute_ago = now - timedelta(minutes=1)

            # Limpiar requests viejos
            if user_id in self._user_requests:
                self._user_requests[user_id] = [
                    ts for ts in self._user_requests[user_id]
                    if ts > one_minute_ago
                ]
            else:
                self._user_requests[user_id] = []

            # Verificar límite
            if len(self._user_requests[user_id]) >= self.per_user_limit:
                logger.warning(
                    "rate_limit_user_exceeded",
                    user_id=user_id,
                    limit=self.per_user_limit
                )
                return False

            # Registrar request
            self._user_requests[user_id].append(now)
            return True

    async def check_global_limit(self) -> bool:
        """
        Verifica límite global de requests.

        Returns:
            True si puede proceder
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            one_second_ago = now - timedelta(seconds=1)

            # Limpiar requests viejos
            self._global_requests = [
                ts for ts in self._global_requests
                if ts > one_second_ago
            ]

            # Verificar límite
            if len(self._global_requests) >= self.global_limit:
                logger.warning(
                    "rate_limit_global_exceeded",
                    limit=self.global_limit
                )
                return False

            # Registrar request
            self._global_requests.append(now)
            return True

    async def wait_if_needed(self, user_id: int) -> None:
        """
        Espera si es necesario para respetar rate limits.

        Args:
            user_id: ID del usuario
        """
        max_retries = 5
        retry_count = 0

        while retry_count < max_retries:
            user_ok = await self.check_user_limit(user_id)
            global_ok = await self.check_global_limit()

            if user_ok and global_ok:
                return

            # Esperar antes de reintentar
            wait_time = 0.1 * (2 ** retry_count)  # Backoff exponencial
            logger.debug(
                "rate_limiter_waiting",
                user_id=user_id,
                wait_seconds=wait_time
            )

            await asyncio.sleep(wait_time)
            retry_count += 1

        logger.error(
            "rate_limiter_timeout",
            user_id=user_id,
            max_retries=max_retries
        )
