"""
Tests para servicios de LLM (mocked).
Se integran con el proveedor real en fases posteriores.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from models.lead import LeadInput
from models.qualification import LeadQualification, QualificationResult


class TestLLMServiceInterface:
    """Tests básicos del LLMService (interfaz y orquestación)."""

    def test_llm_service_placeholder(self):
        """
        Placeholder de tests para LLMService.
        Los tests reales se implementan en FASE 3 con los proveedores.
        """
        # TODO: Implementar en FASE 3
        assert True
