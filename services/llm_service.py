"""
Servicio de LLM. Define interfaz y orquestación.
Soporta múltiples proveedores (OpenAI, Anthropic, etc).
"""

from abc import ABC, abstractmethod
from typing import Optional
from models.lead import LeadInput
from models.qualification import LeadQualification, QualificationResult
from utils.logger import get_logger
from config.settings import Settings
from config.constants import SYSTEM_PROMPT
import json
from datetime import datetime

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
            LLMServiceError: Si hay error en la llamada al LLM
        """
        pass


class LLMService(LLMServiceInterface):
    """
    Servicio de LLM orquestador.
    Delega a implementaciones específicas según el proveedor configurado.
    """

    def __init__(self, settings: Settings):
        """
        Inicializa el servicio de LLM.

        Args:
            settings: Configuración de la aplicación
        """
        self.settings = settings
        self.provider = settings.llm_provider.lower()

        logger.info(
            "llm_service_initialized",
            provider=self.provider,
            model=self._get_model_name()
        )

        # Lazy import de implementaciones específicas
        if self.provider == "openai":
            from services.providers.openai_provider import OpenAIProvider
            self._provider_impl = OpenAIProvider(settings)
        elif self.provider == "anthropic":
            from services.providers.anthropic_provider import AnthropicProvider
            self._provider_impl = AnthropicProvider(settings)
        else:
            raise ValueError(f"Proveedor de LLM no soportado: {self.provider}")

    async def qualify_lead(self, lead: LeadInput) -> QualificationResult:
        """
        Cualifica un lead usando el proveedor configurado.

        Args:
            lead: Datos del lead

        Returns:
            Resultado de cualificación
        """
        try:
            logger.debug(
                "llm_qualify_lead_start",
                telegram_user_id=lead.telegram_user_id,
                text_length=len(lead.raw_text)
            )

            # Llamar a la implementación específica del proveedor
            result = await self._provider_impl.qualify_lead(lead)

            logger.info(
                "llm_qualify_lead_success",
                telegram_user_id=lead.telegram_user_id,
                is_qualified=result.qualification.is_qualified
            )

            return result

        except Exception as e:
            logger.error(
                "llm_qualify_lead_failed",
                telegram_user_id=lead.telegram_user_id,
                error=str(e)
            )
            raise

    def _get_model_name(self) -> str:
        """Retorna el nombre del modelo según el proveedor."""
        if self.provider == "openai":
            return self.settings.openai_model
        elif self.provider == "anthropic":
            return self.settings.anthropic_model
        return "unknown"
