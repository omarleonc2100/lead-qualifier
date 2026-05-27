"""
Provider de Anthropic Claude.
Se completa en FASE 3.
"""

from models.lead import LeadInput
from models.qualification import QualificationResult
from utils.logger import get_logger
from config.settings import Settings
from config.constants import SYSTEM_PROMPT

logger = get_logger(__name__)


class AnthropicProvider:
    """
    Provider para Anthropic Claude models.
    Implementación completa en FASE 3.
    """
    
    def __init__(self, settings: Settings):
        """
        Inicializa el provider de Anthropic.
        
        Args:
            settings: Configuración de la aplicación
        """
        self.settings = settings
        logger.info(
            "anthropic_provider_initialized",
            model=settings.anthropic_model
        )
    
    async def qualify_lead(self, lead: LeadInput) -> QualificationResult:
        """
        Cualifica un lead usando Anthropic Claude.
        
        IMPLEMENTACIÓN EN FASE 3.
        
        Args:
            lead: Datos del lead
        
        Returns:
            Resultado de cualificación
        """
        # Será implementado en FASE 3
        raise NotImplementedError("Anthropic Provider se implementa en FASE 3")
