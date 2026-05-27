"""
Servicio de LLM con Fallback automático.
FASE 5: Si falla OpenAI, intenta con Anthropic automáticamente.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from models.lead import LeadInput
from models.qualification import QualificationResult
from utils.logger import get_logger
from config.settings import Settings
from utils.circuit_breaker import CircuitBreaker
import time

logger = get_logger(__name__)


class LLMServiceInterface(ABC):
    """Interfaz para servicios de LLM."""
    
    @abstractmethod
    async def qualify_lead(self, lead: LeadInput) -> QualificationResult:
        """Cualifica un lead."""
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """Prueba la conexión con el proveedor."""
        pass


class LLMService(LLMServiceInterface):
    """
    Servicio de LLM con fallback automático.
    
    ESTRATEGIA DE FALLBACK:
    1. Intentar con proveedor principal (configurado)
    2. Si falla, intentar con proveedor secundario
    3. Si ambos fallan, retornar error al usuario
    
    CIRCUIT BREAKERS:
    - Uno por proveedor para detectar outages
    - Auto-recuperación después de timeout
    """
    
    def __init__(self, settings: Settings):
        """
        Inicializa el servicio de LLM.
        
        Args:
            settings: Configuración de la aplicación
        """
        self.settings = settings
        self.provider = settings.llm_provider.lower()
        self._provider_impl: Optional[LLMServiceInterface] = None
        self._fallback_provider: Optional[LLMServiceInterface] = None
        
        # Circuit breakers
        self._circuit_breaker_primary: Optional[CircuitBreaker] = None
        self._circuit_breaker_fallback: Optional[CircuitBreaker] = None
        
        logger.info(
            "llm_service_initialized",
            provider=self.provider,
            model=self._get_model_name()
        )
        
        # Inicializar providers
        self._initialize_providers()
        self._initialize_circuit_breakers()
    
    def _initialize_providers(self) -> None:
        """Inicializa proveedor principal y fallback."""
        try:
            if self.provider == "openai":
                from services.providers.openai_provider import OpenAIProvider
                self._provider_impl = OpenAIProvider(self.settings)
                # Fallback: Anthropic
                if self.settings.anthropic_api_key:
                    from services.providers.anthropic_provider import AnthropicProvider
                    self._fallback_provider = AnthropicProvider(self.settings)
                    logger.info("llm_fallback_configured", fallback="anthropic")
            
            elif self.provider == "anthropic":
                from services.providers.anthropic_provider import AnthropicProvider
                self._provider_impl = AnthropicProvider(self.settings)
                # Fallback: OpenAI
                if self.settings.openai_api_key:
                    from services.providers.openai_provider import OpenAIProvider
                    self._fallback_provider = OpenAIProvider(self.settings)
                    logger.info("llm_fallback_configured", fallback="openai")
            
            else:
                raise ValueError(f"Proveedor no soportado: {self.provider}")
        
        except Exception as e:
            logger.error("llm_provider_init_error", error=str(e))
            raise
    
    def _initialize_circuit_breakers(self) -> None:
        """Inicializa circuit breakers para los providers."""
        self._circuit_breaker_primary = CircuitBreaker(
            name=f"llm_{self.provider}",
            failure_threshold=5,
            recovery_timeout=60,
        )
        
        if self._fallback_provider:
            fallback_name = "anthropic" if self.provider == "openai" else "openai"
            self._circuit_breaker_fallback = CircuitBreaker(
                name=f"llm_{fallback_name}",
                failure_threshold=5,
                recovery_timeout=60,
            )
    
    async def qualify_lead(self, lead: LeadInput) -> QualificationResult:
        """
        Cualifica un lead con fallback automático.
        
        ESTRATEGIA:
        1. Intentar con provider principal
        2. Si falla, intentar con fallback
        3. Si ambos fallan, retornar error
        
        Args:
            lead: Datos del lead
        
        Returns:
            Resultado de cualificación
        
        Raises:
            Exception: Si ambos providers fallan
        """
        if not self._provider_impl:
            raise RuntimeError("Provider de LLM no inicializado")
        
        # ============ INTENTAR PROVIDER PRINCIPAL ============
        try:
            logger.debug(
                "llm_qualify_lead_primary",
                provider=self.provider,
                telegram_user_id=lead.telegram_user_id
            )
            
            result = await self._circuit_breaker_primary.call(
                self._provider_impl.qualify_lead,
                lead
            )
            
            logger.info(
                "llm_qualify_lead_success",
                provider=self.provider,
                telegram_user_id=lead.telegram_user_id
            )
            
            return result
        
        except Exception as e:
            logger.warning(
                "llm_qualify_lead_primary_failed",
                provider=self.provider,
                error=str(e),
                error_type=type(e).__name__
            )
            
            # ============ INTENTAR FALLBACK ============
            if self._fallback_provider and self._circuit_breaker_fallback:
                try:
                    fallback_name = "anthropic" if self.provider == "openai" else "openai"
                    logger.info(
                        "llm_trying_fallback",
                        fallback=fallback_name,
                        telegram_user_id=lead.telegram_user_id
                    )
                    
                    result = await self._circuit_breaker_fallback.call(
                        self._fallback_provider.qualify_lead,
                        lead
                    )
                    
                    logger.info(
                        "llm_qualify_lead_fallback_success",
                        fallback=fallback_name,
                        telegram_user_id=lead.telegram_user_id
                    )
                    
                    return result
                
                except Exception as fallback_error:
                    logger.error(
                        "llm_qualify_lead_fallback_failed",
                        fallback=fallback_name,
                        error=str(fallback_error)
                    )
                    
                    # Ambos fallaron
                    raise RuntimeError(
                        f"Ambos providers de LLM fallaron. "
                        f"Principal: {str(e)[:100]}. "
                        f"Fallback: {str(fallback_error)[:100]}"
                    )
            else:
                # No hay fallback disponible
                raise
    
    async def test_connection(self) -> bool:
        """Prueba conexión con ambos providers si están disponibles."""
        if not self._provider_impl:
            logger.error("llm_test_no_provider")
            return False
        
        try:
            # Probar principal
            primary_ok = await self._provider_impl.test_connection()
            
            if not primary_ok:
                logger.warning("llm_test_primary_failed", provider=self.provider)
                return False
            
            # Probar fallback si existe
            if self._fallback_provider:
                fallback_ok = await self._fallback_provider.test_connection()
                if fallback_ok:
                    logger.info("llm_test_fallback_ok")
            
            return True
        
        except Exception as e:
            logger.error("llm_test_connection_error", error=str(e))
            return False
    
    def get_provider_status(self) -> dict:
        """Retorna estado de ambos providers."""
        return {
            "primary": self._circuit_breaker_primary.get_status() if self._circuit_breaker_primary else None,
            "fallback": self._circuit_breaker_fallback.get_status() if self._circuit_breaker_fallback else None,
        }
    
    def _get_model_name(self) -> str:
        """Retorna el nombre del modelo actual."""
        if self.provider == "openai":
            return self.settings.openai_model
        elif self.provider == "anthropic":
            return self.settings.anthropic_model
        return "unknown"
    
    def get_provider_name(self) -> str:
        """Retorna el nombre del proveedor."""
        return self.provider
