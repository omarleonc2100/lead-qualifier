"""
Servicio de Google Sheets - IMPLEMENTACIÓN REAL.
Utiliza gspread para conectar con Google Sheets API.
"""

import gspread
from google.oauth2.service_account import Credentials
from typing import List, Optional
from datetime import datetime, timezone
from pathlib import Path
from utils.logger import get_logger
from config.settings import Settings
from config.constants import GOOGLE_SHEETS_HEADER
from utils.async_utils import async_retry
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = get_logger(__name__)

# Executor para operaciones síncronas en threads separados
_executor = ThreadPoolExecutor(max_workers=2)


class GoogleSheetsServiceInterface:
    """
    Interfaz para servicios de persistencia en Google Sheets.
    """

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

    async def get_header_row(self) -> List[str]:
        """Obtiene la fila de encabezados."""
        pass


class GoogleSheetsService(GoogleSheetsServiceInterface):
    """
    Implementación del servicio de Google Sheets.
    Usa gspread para interactuar con Google Sheets API.

    NOTAS:
    - Las operaciones de gspread son síncronas, las envolvemos en async
    - Implementa retry automático con backoff exponencial
    - Maneja autenticación con service account de Google Cloud
    """

    def __init__(self, settings: Settings):
        """
        Inicializa el servicio de Google Sheets.

        Args:
            settings: Configuración de la aplicación

        Raises:
            FileNotFoundError: Si el archivo de credenciales no existe
            Exception: Si la autenticación falla
        """
        self.settings = settings
        self._client: Optional[gspread.Client] = None
        self._worksheet: Optional[gspread.Worksheet] = None
        self._is_authenticated = False

        logger.info(
            "sheets_service_init",
            sheet_id=settings.google_sheet_id,
            credentials_path=settings.google_sheets_credentials_path
        )

    async def _authenticate(self) -> None:
        """
        Autentica con Google Sheets API usando service account.
        Se ejecuta en un thread separado para no bloquear el event loop.

        Raises:
            FileNotFoundError: Si el archivo de credenciales no existe
            Exception: Si la autenticación falla
        """
        if self._is_authenticated:
            return

        try:
            credentials_path = Path(self.settings.google_sheets_credentials_path)

            if not credentials_path.exists():
                error_msg = f"Credenciales no encontradas en {credentials_path}"
                logger.error("sheets_auth_credentials_not_found", path=str(credentials_path))
                raise FileNotFoundError(error_msg)

            logger.debug("sheets_auth_loading_credentials", path=str(credentials_path))

            # Cargar credenciales en un thread separado
            loop = asyncio.get_event_loop()
            credentials = await loop.run_in_executor(
                _executor,
                self._load_credentials_sync,
                credentials_path
            )

            # Crear cliente en thread separado
            self._client = await loop.run_in_executor(
                _executor,
                self._create_client_sync,
                credentials
            )

            # Abrir la worksheet
            await self._open_worksheet()

            self._is_authenticated = True
            logger.info("sheets_auth_success", sheet_id=self.settings.google_sheet_id)

        except FileNotFoundError as e:
            logger.error("sheets_auth_file_not_found", error=str(e))
            raise
        except Exception as e:
            logger.error("sheets_auth_failed", error=str(e))
            raise

    @staticmethod
    def _load_credentials_sync(credentials_path: Path) -> Credentials:
        """
        Carga credenciales de forma síncrona.
        Se ejecuta en un thread separado.

        Args:
            credentials_path: Ruta al archivo de credenciales JSON

        Returns:
            Objeto Credentials de Google
        """
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]

        return Credentials.from_service_account_file(
            str(credentials_path),
            scopes=scopes
        )

    @staticmethod
    def _create_client_sync(credentials: Credentials) -> gspread.Client:
        """
        Crea cliente de gspread de forma síncrona.
        Se ejecuta en un thread separado.

        Args:
            credentials: Credenciales autenticadas

        Returns:
            Cliente gspread autenticado
        """
        return gspread.authorize(credentials)

    async def _open_worksheet(self) -> None:
        """
        Abre la worksheet específica.
        Se ejecuta en un thread separado.

        Raises:
            Exception: Si no puede abrir la worksheet
        """
        if not self._client:
            raise RuntimeError("Cliente de gspread no inicializado")

        try:
            loop = asyncio.get_event_loop()

            # Abrir spreadsheet en thread separado
            spreadsheet = await loop.run_in_executor(
                _executor,
                self._client.open_by_key,
                self.settings.google_sheet_id
            )

            # Obtener la primera worksheet (por defecto)
            self._worksheet = await loop.run_in_executor(
                _executor,
                lambda: spreadsheet.sheet1
            )

            logger.debug(
                "sheets_worksheet_opened",
                title=self._worksheet.title if self._worksheet else "unknown"
            )

        except Exception as e:
            logger.error("sheets_open_worksheet_failed", error=str(e))
            raise

    async def _ensure_header_row(self) -> None:
        """
        Verifica que la fila de encabezados exista.
        Si no existe, la crea.
        """
        try:
            if not self._worksheet:
                raise RuntimeError("Worksheet no está abierta")

            loop = asyncio.get_event_loop()

            # Obtener primera fila en thread separado
            first_row = await loop.run_in_executor(
                _executor,
                lambda: self._worksheet.row_values(1)
            )

            # Si no hay encabezados, crearlos
            if not first_row or first_row[0] != "Fecha":
                logger.info("sheets_creating_header_row")
                await loop.run_in_executor(
                    _executor,
                    lambda: self._worksheet.insert_row(GOOGLE_SHEETS_HEADER, index=1)
                )
                logger.info("sheets_header_row_created")

        except Exception as e:
            logger.error("sheets_ensure_header_failed", error=str(e))
            # No levantamos excepción, continuamos

    @async_retry(max_attempts=3, initial_delay=1.0)
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
        Incluye retry automático con backoff exponencial.

        Args:
            telegram_user_id: ID del usuario
            telegram_username: Username
            raw_text: Texto del lead
            decision: CUALIFICADO o NO CUALIFICADO
            reason: Razón de la decisión

        Returns:
            True si fue exitoso, False en caso contrario
        """
        try:
            # Autenticar si es necesario
            await self._authenticate()

            # Asegurar que exista fila de encabezados
            await self._ensure_header_row()

            # Preparar datos
            now = datetime.now(timezone.utc).isoformat()
            username_str = telegram_username or f"user_{telegram_user_id}"

            # Truncar texto largo para no saturar la sheet
            raw_text_truncated = raw_text[:500] if len(raw_text) > 500 else raw_text
            reason_truncated = reason[:200] if len(reason) > 200 else reason

            row_data = [
                now,                    # Fecha
                username_str,          # Usuario Telegram
                raw_text_truncated,    # Datos Recibidos
                decision,              # Decisión
                reason_truncated,      # Motivo
                str(telegram_user_id)  # Timestamp/User ID
            ]

            logger.debug(
                "sheets_append_record_preparing",
                user_id=telegram_user_id,
                decision=decision
            )

            # Añadir fila en thread separado
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                _executor,
                lambda: self._worksheet.append_row(row_data)
            )

            logger.info(
                "sheets_append_record_success",
                telegram_user_id=telegram_user_id,
                decision=decision
            )

            return True

        except Exception as e:
            logger.error(
                "sheets_append_record_failed",
                telegram_user_id=telegram_user_id,
                error=str(e)
            )
            return False

    async def get_header_row(self) -> List[str]:
        """
        Obtiene la fila de encabezados.

        Returns:
            Lista de encabezados
        """
        await self._authenticate()

        try:
            loop = asyncio.get_event_loop()
            header = await loop.run_in_executor(
                _executor,
                lambda: self._worksheet.row_values(1) if self._worksheet else GOOGLE_SHEETS_HEADER
            )

            return header or GOOGLE_SHEETS_HEADER

        except Exception as e:
            logger.error("sheets_get_header_failed", error=str(e))
            return GOOGLE_SHEETS_HEADER

    async def get_all_records(self) -> List[dict]:
        """
        Obtiene todos los registros de leads (para analytics/debugging).

        Returns:
            Lista de diccionarios con todos los leads
        """
        await self._authenticate()

        try:
            loop = asyncio.get_event_loop()
            records = await loop.run_in_executor(
                _executor,
                lambda: self._worksheet.get_all_records() if self._worksheet else []
            )

            logger.debug("sheets_get_all_records_success", count=len(records))
            return records

        except Exception as e:
            logger.error("sheets_get_all_records_failed", error=str(e))
            return []
