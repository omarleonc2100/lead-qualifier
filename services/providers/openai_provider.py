"""
Provider de OpenAI.
Se completa en FASE 3.
"""

from models.lead import LeadInput
from models.qualification import QualificationResult
from utils.logger import get_logger
from config.settings import Settings
from config.constants import SYSTEM_PROMPT

logger = get_logger(__name__)


class OpenAIProvider:
    """
    Provider para OpenAI GPT models.
    Implementación completa en FASE 3.
    """
    
    def __init__(self, settings: Settings):
        """
        Inicializa el provider de OpenAI.
        
        Args:
            settings: Configuración de la aplicación
        """
        self.settings = settings
        logger.info(
            "openai_provider_initialized",
            model=settings.openai_model
        )
    
    async def qualify_lead(self, lead: LeadInput) -> QualificationResult:
        """
        Cualifica un lead usando OpenAI GPT.
        
        IMPLEMENTACIÓN EN FASE 3 CON STRUCTURED OUTPUTS.
        
        Args:
            lead: Datos del lead
        
        Returns:
            Resultado de cualificación
        """
        # Será implementado en FASE 3
        raise NotImplementedError("OpenAI Provider se implementa en FASE 3")
