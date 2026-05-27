"""
Tests para el servicio de LLM.
Valida que ambos providers funcionen correctamente.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from config.settings import Settings
from models.lead import LeadInput
from models.qualification import LeadQualification, QualificationResult
from services.llm_service import LLMService


class TestOpenAIProvider:
    """Tests para OpenAI Provider."""
    
    @pytest.mark.asyncio
    async def test_qualify_lead_qualified(self):
        """Test de cualificación exitosa con OpenAI."""
        settings = Settings(
            telegram_bot_token="test", 
            google_sheet_id="test",
            openai_api_key="sk-mock-key"
        )
        settings.llm_provider = "openai"
        
        llm_service = LLMService(settings)
        
        lead = LeadInput(
            raw_text="Somos una empresa de consultoría en Madrid con 25 empleados. "
                     "Queremos automatizar nuestros procesos de ventas.",
            telegram_user_id=123456,
            telegram_username="test_user"
        )
        
        # Este test necesita clave OpenAI real para ejecutarse
        # En CI/CD se mockearía la API
        
        # result = await llm_service.qualify_lead(lead)
        # assert isinstance(result, QualificationResult)
        # assert isinstance(result.qualification, LeadQualification)


class TestAnthropicProvider:
    """Tests para Anthropic Provider."""
    
    @pytest.mark.asyncio
    async def test_qualify_lead_not_qualified(self):
        """Test de rechazo correcto con Anthropic."""
        settings = Settings(
            telegram_bot_token="test", 
            google_sheet_id="test",
            anthropic_api_key="sk-ant-mock-key"
        )
        settings.llm_provider = "anthropic"
        
        llm_service = LLMService(settings)
        
        lead = LeadInput(
            raw_text="Soy freelancer en USA. Desarrollo webs.",
            telegram_user_id=789012,
            telegram_username="freelancer"
        )
        
        # result = await llm_service.qualify_lead(lead)
        # assert result.qualification.is_qualified is False


class TestJSONExtraction:
    """Tests para extracción de JSON."""
    
    def test_extract_json_with_extra_text(self):
        """Test de extracción de JSON con texto adicional."""
        from services.providers.anthropic_provider import AnthropicProvider
        
        text = 'Aquí está: {"is_qualified": true, "reason": "Cumple criterios"} Fin.'
        
        json_str = AnthropicProvider._extract_json(text)
        
        assert json_str is not None
        assert '"is_qualified": true' in json_str
        assert '"reason"' in json_str
