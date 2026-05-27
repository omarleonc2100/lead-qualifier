"""
Tests para modelos de datos (LeadInput, LeadMetadata, LeadQualification).
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from models.lead import LeadInput, LeadMetadata
from models.qualification import LeadQualification, QualificationResult


class TestLeadInput:
    """Tests para el modelo LeadInput."""

    def test_valid_lead_input(self):
        """Crea un LeadInput válido correctamente."""
        lead = LeadInput(
            raw_text="Somos una empresa de consultoría en Madrid con 20 empleados.",
            telegram_user_id=123456789,
            telegram_username="test_user"
        )
        assert lead.telegram_user_id == 123456789
        assert lead.telegram_username == "test_user"
        assert "consultoría" in lead.raw_text

    def test_lead_input_strips_whitespace(self):
        """Verifica que el texto se sanitiza quitando espacios extra."""
        lead = LeadInput(
            raw_text="  Texto con espacios al inicio y final  ",
            telegram_user_id=111
        )
        assert lead.raw_text == "Texto con espacios al inicio y final"

    def test_lead_input_too_short(self):
        """Falla si el texto es muy corto."""
        with pytest.raises(ValidationError):
            LeadInput(
                raw_text="Hola",
                telegram_user_id=111
            )

    def test_lead_input_too_long(self):
        """Falla si el texto supera el límite."""
        with pytest.raises(ValidationError):
            LeadInput(
                raw_text="A" * 2001,
                telegram_user_id=111
            )

    def test_lead_input_empty_text(self):
        """Falla si el texto está vacío después de strip."""
        with pytest.raises(ValidationError):
            LeadInput(
                raw_text="          ",
                telegram_user_id=111
            )

    def test_lead_input_no_username(self):
        """Acepta leads sin username (es opcional)."""
        lead = LeadInput(
            raw_text="Empresa de tecnología con 10 empleados en Colombia.",
            telegram_user_id=222
        )
        assert lead.telegram_username is None

    def test_lead_input_has_timestamp(self):
        """Verifica que el timestamp se genera automáticamente."""
        lead = LeadInput(
            raw_text="Empresa de marketing en Buenos Aires.",
            telegram_user_id=333
        )
        assert isinstance(lead.timestamp, datetime)


class TestLeadQualification:
    """Tests para el modelo LeadQualification."""

    def test_qualified_lead(self):
        """Crea una cualificación positiva correctamente."""
        qual = LeadQualification(
            is_qualified=True,
            reason="Empresa de consultoría con 20 empleados en Madrid. Interés en IA."
        )
        assert qual.is_qualified is True
        assert len(qual.reason) >= 10

    def test_not_qualified_lead(self):
        """Crea una cualificación negativa correctamente."""
        qual = LeadQualification(
            is_qualified=False,
            reason="Freelancer sin equipo. No cumple criterio de tamaño mínimo."
        )
        assert qual.is_qualified is False

    def test_reason_too_short(self):
        """Falla si la razón es muy corta."""
        with pytest.raises(ValidationError):
            LeadQualification(
                is_qualified=True,
                reason="Ok"
            )

    def test_reason_too_long(self):
        """Falla si la razón supera el límite de 500 caracteres."""
        with pytest.raises(ValidationError):
            LeadQualification(
                is_qualified=False,
                reason="X" * 501
            )

    def test_reason_strips_whitespace(self):
        """Verifica que la razón se sanitiza quitando espacios."""
        qual = LeadQualification(
            is_qualified=True,
            reason="   Cumple criterios del ICP para España.   "
        )
        assert qual.reason == "Cumple criterios del ICP para España."


class TestQualificationResult:
    """Tests para el modelo QualificationResult."""

    def test_full_result(self):
        """Crea un resultado completo correctamente."""
        result = QualificationResult(
            lead_id="lead_001",
            qualification=LeadQualification(
                is_qualified=True,
                reason="Empresa de servicios con 15 empleados en Barcelona."
            ),
            model_used="gpt-4o-mini"
        )
        assert result.lead_id == "lead_001"
        assert result.qualification.is_qualified is True
        assert result.model_used == "gpt-4o-mini"
        assert isinstance(result.created_at, datetime)

    def test_result_without_lead_id(self):
        """Acepta resultados sin lead_id (es opcional)."""
        result = QualificationResult(
            qualification=LeadQualification(
                is_qualified=False,
                reason="No cumple criterio de región geográfica permitida."
            ),
            model_used="claude-3-5-sonnet"
        )
        assert result.lead_id is None
