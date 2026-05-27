"""
Servicio de Google Sheets.
Abstrae la integración con Google Sheets API.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from utils.logger import get_logger
from config.settings import Settings
from config.constants import GOOGLE_SHEETS_HEADER
import asyncio

logger = get_logger(__name__)


class GoogleSheetsServiceInterface(ABC):
    """
    Interfaz para servicios de persistencia en Google Sheets.
    """

    @abstractmethod
    async def append_lead_record(
        self,
        telegram_user_id: int,
        telegram_username: Optional[str],
        raw_text: str,
        decision: str,
        reason: str,
    ) -> bool:
        """
        Añade un registro de lead a la Google Sheet.

        Args:
            telegram_user_id: ID del usuario de Telegram
            telegram_username: Username de Telegram
            raw_text: Texto original del lead
            decision: Decisión (CUALIFICADO / NO CUALIFICADO)
            reason: Razón de la decisión

        Returns:
            True si fue exitoso, False en caso contrario
        """
        pass

    @abstractmethod
    async def get_header_row(self) -> List[str]:
        """Obtiene la fila de encabezados."""
        pass


class GoogleSheetsService(GoogleSheetsServiceInterface):
    """
    Implementación del servicio de Google Sheets.
    Usa gspread para interactuar con Google Sheets API.
    """

    def __init__(self, settings: Settings):
        """
        Inicializa el servicio de Google Sheets.

        Args:
            settings: Configuración de la aplicación
        """
        self.settings = settings
        self._client = None
        self._worksheet = None

        logger.info(
            "sheets_service_initialized",
            sheet_id=settings.google_sheet_id
        )

    async def _ensure_authenticated(self) -> None:
        """
        Asegura que esté autenticado con Google.
        Implementación diferida hasta FASE 2.
        """
        if self._client is None:
            # Será implementado en FASE 2
            raise NotImplementedError("Autenticación con Google Sheets se implementa en FASE 2")

    async def append_lead_record(
        self,
        telegram_user_id: int,
        telegram_username: Optional[str],
        raw_text: str,
        decision: str,
        reason: str,
    ) -> bool:
        """
        Añade un registro a la Google Sheet de forma asincrónica.

        Args:
            telegram_user_id: ID del usuario
            telegram_username: Username
            raw_text: Texto del lead
            decision: CUALIFICADO o NO CUALIFICADO
            reason: Razón de la decisión

        Returns:
            True si fue exitoso
        """
        try:
            # Será implementado en FASE 2
            # Por ahora retornamos True para no bloquear arquitectura
            logger.debug(
                "sheets_append_record_placeholder",
                decision=decision,
                telegram_user_id=telegram_user_id
            )
            return True

        except Exception as e:
            logger.error(
                "sheets_append_record_failed",
                error=str(e),
                decision=decision
            )
            return False

    async def get_header_row(self) -> List[str]:
        """Retorna los encabezados de la sheet."""
        return GOOGLE_SHEETS_HEADER
