"""
Tests para Google Sheets Service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestGoogleSheetsService:
    """Tests para GoogleSheetsService."""

    def test_sheets_service_placeholder(self):
        """
        Placeholder de tests para GoogleSheetsService.
        Los tests reales se implementan en FASE 2 con la autenticación real.
        """
        # TODO: Implementar en FASE 2
        assert True

    @pytest.mark.asyncio
    async def test_get_header_row(self):
        """
        Verifica que get_header_row retorna los encabezados correctos.
        """
        from config.constants import GOOGLE_SHEETS_HEADER

        # Verificar que los headers están definidos correctamente
        assert "Fecha" in GOOGLE_SHEETS_HEADER
        assert "Decisión" in GOOGLE_SHEETS_HEADER
        assert "Motivo" in GOOGLE_SHEETS_HEADER
        assert len(GOOGLE_SHEETS_HEADER) == 6
