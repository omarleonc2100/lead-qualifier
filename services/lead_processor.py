"""
Servicio de procesamiento de leads.
Orquesta el flujo completo: validación -> LLM -> Google Sheets -> Telegram.
"""

from typing import Optional, TYPE_CHECKING
from models.lead import LeadInput
from models.qualification import QualificationResult
from utils.logger import get_logger
from utils.validators import sanitize_input, detect_prompt_injection
from config.settings import Settings
from datetime import datetime
import time

if TYPE_CHECKING:
    from services.llm_service import LLMService
    from services.sheets_service import GoogleSheetsService
    from services.telegram_service import TelegramService

logger = get_logger(__name__)


class LeadProcessor:
    """
    Orquestador principal del procesamiento de leads.
    Coordina LLM, Google Sheets y Telegram.
    """

    def __init__(
        self,
        settings: Settings,
        llm_service: "LLMService",
        sheets_service: "GoogleSheetsService",
        telegram_service: "TelegramService",
    ):
        """
        Inicializa el procesador de leads.

        Args:
            settings: Configuración global
            llm_service: Servicio de LLM
            sheets_service: Servicio de Google Sheets
            telegram_service: Servicio de Telegram
        """
        self.settings = settings
        self.llm_service = llm_service
        self.sheets_service = sheets_service
        self.telegram_service = telegram_service

        logger.info("lead_processor_initialized")

    async def process_lead(
        self,
        raw_text: str,
        telegram_user_id: int,
        telegram_username: Optional[str] = None,
    ) -> Optional[QualificationResult]:
        """
        Procesa un lead desde inicio a fin.
        Orquesta: validación -> LLM -> persistencia -> respuesta Telegram.

        Args:
            raw_text: Texto libre del lead
            telegram_user_id: ID del usuario de Telegram
            telegram_username: Username de Telegram (opcional)

        Returns:
            Resultado de cualificación si fue exitoso, None si falló
        """
        start_time = time.time()

        try:
            logger.info(
                "lead_processor_start",
                telegram_user_id=telegram_user_id,
                text_length=len(raw_text)
            )

            # PASO 1: Validación de input
            lead = self._validate_input(
                raw_text=raw_text,
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
            )

            # PASO 2: Verificar Prompt Injection
            if self.settings.enable_prompt_injection_check:
                if detect_prompt_injection(lead.raw_text):
                    logger.warning(
                        "prompt_injection_detected",
                        telegram_user_id=telegram_user_id
                    )
                    # En FASE 5 manejaremos esto de forma más sofisticada

            # PASO 3: Procesar con LLM
            result = await self.llm_service.qualify_lead(lead)

            # PASO 4: Persistir en Google Sheets
            decision_text = "CUALIFICADO" if result.qualification.is_qualified else "NO CUALIFICADO"
            await self.sheets_service.append_lead_record(
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
                raw_text=raw_text,
                decision=decision_text,
                reason=result.qualification.reason,
            )

            # PASO 5: Enviar respuesta a Telegram
            await self._send_telegram_response(
                telegram_user_id=telegram_user_id,
                qualification=result.qualification,
            )

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "lead_processor_success",
                telegram_user_id=telegram_user_id,
                is_qualified=result.qualification.is_qualified,
                elapsed_ms=elapsed_ms
            )

            return result

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                "lead_processor_failed",
                telegram_user_id=telegram_user_id,
                error=str(e),
                elapsed_ms=elapsed_ms
            )

            # Notificar error a Telegram
            await self._send_telegram_error(telegram_user_id, str(e))
            return None

    def _validate_input(
        self,
        raw_text: str,
        telegram_user_id: int,
        telegram_username: Optional[str],
    ) -> LeadInput:
        """
        Valida el input del usuario.

        Args:
            raw_text: Texto a validar
            telegram_user_id: ID del usuario
            telegram_username: Username

        Returns:
            LeadInput validado

        Raises:
            ValueError: Si la validación falla
        """
        # Sanitizar
        sanitized_text = sanitize_input(raw_text)

        # Crear modelo Pydantic (valida automáticamente)
        lead = LeadInput(
            raw_text=sanitized_text,
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
        )

        return lead

    async def _send_telegram_response(
        self,
        telegram_user_id: int,
        qualification,
    ) -> None:
        """
        Envía la respuesta de cualificación a Telegram.

        Args:
            telegram_user_id: ID del chat
            qualification: Resultado de cualificación
        """
        from config.constants import TELEGRAM_RESPONSE_QUALIFIED, TELEGRAM_RESPONSE_NOT_QUALIFIED

        if qualification.is_qualified:
            message = TELEGRAM_RESPONSE_QUALIFIED.format(reason=qualification.reason)
        else:
            message = TELEGRAM_RESPONSE_NOT_QUALIFIED.format(reason=qualification.reason)

        await self.telegram_service.send_message(telegram_user_id, message)

    async def _send_telegram_error(
        self,
        telegram_user_id: int,
        error_message: str,
    ) -> None:
        """
        Envía un mensaje de error a Telegram.

        Args:
            telegram_user_id: ID del chat
            error_message: Mensaje de error
        """
        from config.constants import TELEGRAM_RESPONSE_ERROR

        message = TELEGRAM_RESPONSE_ERROR.format(error_message=error_message[:100])
        await self.telegram_service.send_message(telegram_user_id, message)
