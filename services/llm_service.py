"""
Servicio de LLM. Orquestación y delegación a providers.
FASE 3: Ahora usa providers reales con Structured Outputs.
"""

from abc import ABC, abstractmethod
from typing import Optional
from models.lead import LeadInput
from models.qualification import QualificationResult
from utils.logger import get_logger
from config.settings import Settings
from config.constants import SYSTEM_PROMPT
import time

logger = get_logger(__name__)


class LLMServiceInterface(ABC):
    """
    Interfaz abstracta para servicios de LLM.
    Permite cambiar entre proveedores sin modificar el código.
    """
    
    @abstractmethod
    async def qualify_lead(self, lead: LeadInput) -> QualificationResult:
        """
        Cualifica un lead usando el LLM.
        
        Args:
            lead: Datos del lead a calificar
        
        Returns:
            Resultado de cualificación estructurado
        
        Raises:
            Exception: Si hay error en la llamada al LLM
        """
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Prueba la conexión con el proveedor de LLM.
        
        Returns:
            True si la conexión es válida
        """
        pass


class LLMService(LLMServiceInterface):
    """
    Servicio de LLM orquestador.
    Delega a implementaciones específicas según el proveedor configurado.
    
    PROVEEDORES SOPORTADOS:
    - openai: GPT-4o mini (recomendado para costo)
    - anthropic: Claude 3.5 Sonnet (mejor contexto)
    
    FEATURES:
    - Carga dinámica de providers
    - Fallback automático (FASE 5)
    - Test de conexión en startup
    - Logging detallado
    """
    
    def __init__(self, settings: Settings):
        """
        Inicializa el servicio de LLM.
        
        Args:
            settings: Configuración de la aplicación
        
        Raises:
            ValueError: Si el proveedor no es soportado
        """
        self.settings = settings
        self.provider = settings.llm_provider.lower()
        self._provider_impl: Optional[LLMServiceInterface] = None
        
        logger.info(
            "llm_service_initialized",
            provider=self.provider,
            model=self._get_model_name()
        )
        
        # Inicializar el provider específico
        self._initialize_provider()
    
    def _initialize_provider(self) -> None:
        """
        Inicializa el provider según la configuración.
        
        Raises:
            ValueError: Si el proveedor no es soportado
            ImportError: Si las dependencias no están instaladas
        """
        try:
            if self.provider == "openai":
                from services.providers.openai_provider import OpenAIProvider
                self._provider_impl = OpenAIProvider(self.settings)
                logger.debug("openai_provider_loaded")
            
            elif self.provider == "anthropic":
                from services.providers.anthropic_provider import AnthropicProvider
                self._provider_impl = AnthropicProvider(self.settings)
                logger.debug("anthropic_provider_loaded")
            
            else:
                raise ValueError(
                    f"Proveedor de LLM no soportado: {self.provider}. "
                    f"Usa 'openai' o 'anthropic'"
                )
        
        except ImportError as e:
            logger.error(
                "llm_provider_import_error",
                provider=self.provider,
                error=str(e)
            )
            raise
        except Exception as e:
            logger.error(
                "llm_provider_init_error",
                provider=self.provider,
                error=str(e)
            )
            raise
    
    async def qualify_lead(self, lead: LeadInput) -> QualificationResult:
        """
        Cualifica un lead usando el proveedor configurado.
        
        Args:
            lead: Datos del lead
        
        Returns:
            Resultado de cualificación estructurado
        
        Raises:
            Exception: Si hay error en la llamada al LLM
        """
        if not self._provider_impl:
            raise RuntimeError("Provider de LLM no inicializado")
        
        try:
            logger.debug(
                "llm_qualify_lead_start",
                provider=self.provider,
                telegram_user_id=lead.telegram_user_id,
                text_length=len(lead.raw_text)
            )
            
            # Delegar al provider
            result = await self._provider_impl.qualify_lead(lead)
            
            logger.info(
                "llm_qualify_lead_success",
                provider=self.provider,
                telegram_user_id=lead.telegram_user_id,
                is_qualified=result.qualification.is_qualified
            )
            
            return result
        
        except Exception as e:
            logger.error(
                "llm_qualify_lead_failed",
                provider=self.provider,
                telegram_user_id=lead.telegram_user_id,
                error=str(e),
                error_type=type(e).__name__
            )
            raise

    async def test_connection(self) -> bool:
        """
        Prueba la conexión con el proveedor de LLM.
        
        Returns:
            True si la conexión es válida
        """
        if not self._provider_impl:
            logger.error("llm_test_connection_provider_not_initialized")
            return False
        
        try:
            logger.debug("llm_test_connection_start", provider=self.provider)
            
            result = await self._provider_impl.test_connection()
            
            if result:
                logger.info("llm_test_connection_success", provider=self.provider)
            else:
                logger.warning("llm_test_connection_failed", provider=self.provider)
            
            return result
        
        except Exception as e:
            logger.error(
                "llm_test_connection_error",
                provider=self.provider,
                error=str(e)
            )
            return False
    
    def _get_model_name(self) -> str:
        """
        Retorna el nombre del modelo según el proveedor.
        
        Returns:
            Nombre del modelo
        """
        if self.provider == "openai":
            return self.settings.openai_model
        elif self.provider == "anthropic":
            return self.settings.anthropic_model
        return "unknown"
    
    def get_provider_name(self) -> str:
        """Retorna el nombre del proveedor configurado."""
        return self.provider
