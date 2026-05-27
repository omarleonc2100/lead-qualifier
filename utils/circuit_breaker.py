"""
Implementación de Circuit Breaker para APIs externas.
Evita cascadas de fallos y permite recuperación gradual.

PATRÓN:
- CLOSED: Funcionando normal
- OPEN: Demasiados fallos, bloquear requests
- HALF_OPEN: Probando si el servicio se recuperó
"""

from typing import Callable, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum
from utils.logger import get_logger
import asyncio

logger = get_logger(__name__)


class CircuitState(Enum):
    """Estados posibles del circuit breaker."""
    CLOSED = "closed"      # Funcionando normal
    OPEN = "open"          # Bloqueado por muchos fallos
    HALF_OPEN = "half_open"  # Probando recuperación


class CircuitBreaker:
    """
    Circuit Breaker para proteger llamadas a APIs externas.
    
    ESTRATEGIA:
    1. Contar fallos consecutivos
    2. Si se llega al threshold, pasar a OPEN
    3. En OPEN, rechazar todas las requests sin llamar API
    4. Después de timeout, pasar a HALF_OPEN
    5. En HALF_OPEN, permitir un request de prueba
    6. Si funciona, volver a CLOSED
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,  # segundos
        expected_exception: type = Exception,
    ):
        """
        Inicializa el circuit breaker.
        
        Args:
            name: Nombre del circuito (para logging)
            failure_threshold: Fallos consecutivos antes de abrir
            recovery_timeout: Segundos antes de intentar recuperación
            expected_exception: Tipo de excepción a contar
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._state = CircuitState.CLOSED
        
        logger.info(
            "circuit_breaker_initialized",
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout
        )
    
    @property
    def state(self) -> CircuitState:
        """Retorna el estado actual del circuito."""
        return self._state
    
    async def call(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Ejecuta una función a través del circuit breaker.
        
        Args:
            func: Función a ejecutar
            *args: Argumentos posicionales
            **kwargs: Argumentos nombrados
        
        Returns:
            Resultado de la función
        
        Raises:
            Exception: Si el circuito está OPEN
        """
        # Verificar si es tiempo de intentar recuperación
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
                logger.info(
                    "circuit_breaker_half_open",
                    name=self.name,
                    failure_count=self._failure_count
                )
            else:
                logger.warning(
                    "circuit_breaker_open_rejecting",
                    name=self.name
                )
                raise RuntimeError(
                    f"Circuit breaker '{self.name}' está OPEN. "
                    f"El servicio no está disponible."
                )
        
        try:
            # Ejecutar función
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            # Si funcionó, resetear el estado
            if self._state == CircuitState.HALF_OPEN:
                self._reset()
                logger.info("circuit_breaker_closed", name=self.name)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0
            
            return result
        
        except self.expected_exception as e:
            # Contar fallo
            self._failure_count += 1
            self._last_failure_time = datetime.utcnow()
            
            logger.warning(
                "circuit_breaker_failure",
                name=self.name,
                failure_count=self._failure_count,
                threshold=self.failure_threshold,
                error=str(e)
            )
            
            # Si alcanzamos el threshold, abrir el circuito
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.error(
                    "circuit_breaker_opened",
                    name=self.name,
                    failure_count=self._failure_count
                )
            
            raise
    
    def _should_attempt_reset(self) -> bool:
        """
        Verifica si es tiempo de intentar recuperación.
        
        Returns:
            True si pasó el timeout desde el último fallo
        """
        if not self._last_failure_time:
            return False
        
        elapsed = datetime.utcnow() - self._last_failure_time
        return elapsed.total_seconds() >= self.recovery_timeout
    
    def _reset(self) -> None:
        """Resetea el circuito a estado CLOSED."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
    
    def get_status(self) -> dict:
        """Retorna el estado actual del circuito."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "threshold": self.failure_threshold,
        }
