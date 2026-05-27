"""
Servicio de procesamiento de leads.
FASE 4: Integración completa con rate limiting y error handling.
"""

from typing import Optional, TYPE_CHECKING
from models.lead import LeadInput
from models.qualification import QualificationResult
from utils.logger import get_logger
from utils.validators import sanitize_input, detect_prompt_injection, validate_text_length
from utils.rate_limiter import RateLimiter
from handlers.error_handler import ErrorHandler
from config.settings import Settings
import time

if TYPE_CHECKING:
    from services.llm_service import LLMService
    from services.sheets_service import GoogleSheetsService
    from services.telegram_service import TelegramService

logger = get_logger(__name__)


class LeadProcessor:
    """
    Orquestador principal del procesamiento de leads.

    FASE 4 FEATURES:
    - Rate limiting por usuario
    - Manejo robusto de errores con retry
    - Logging completo de latencias
    - Traducción de errores a mensajes amigables
    - Procesamiento asincrónico optimizado
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

        # Rate limiter
        self.rate_limiter = RateLimiter(
            per_user_limit=settings.rate_limit_per_minute,
            global_limit=5  # 5 requests por segundo a APIs
        )

        logger.info("lead_processor_initialized")

    async def process_lead(
        self,
        raw_text: str,
        telegram_user_id: int,
        telegram_username: Optional[str] = None,
    ) -> Optional[QualificationResult]:
        """
        Procesa un lead desde inicio a fin.

        PASOS:
        1. Rate limiting
        2. Validar input
        3. Verificar prompt injection
        4. Procesar con LLM
        5. Guardar en Google Sheets
        6. Enviar respuesta a Telegram
        7. Log de latencia y éxito

        Args:
            raw_text: Texto libre del lead
            telegram_user_id: ID del usuario de Telegram
            telegram_username: Username de Telegram (opcional)

        Returns:
            Resultado de cualificación si fue exitoso, None si falló
        """
        start_time = time.time()
        request_id = f"{telegram_user_id}_{int(time.time() * 1000)}"

        try:
            logger.info(
                "lead_processor_start",
                request_id=request_id,
                telegram_user_id=telegram_user_id,
                text_length=len(raw_text)
            )

            # ============ PASO 1: RATE LIMITING ============
            logger.debug("lead_processor_checking_rate_limit", request_id=request_id)
            await self.rate_limiter.wait_if_needed(telegram_user_id)

            # ============ PASO 2: VALIDACIÓN DE INPUT ============
            lead = self._validate_input(
                raw_text=raw_text,
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
            )

            # ============ PASO 3: VERIFICAR PROMPT INJECTION ============
            if self.settings.enable_prompt_injection_check:
                if detect_prompt_injection(lead.raw_text):
                    logger.warning(
                        "prompt_injection_detected",
                        request_id=request_id,
                        telegram_user_id=telegram_user_id
                    )
                    # En FASE 5 manejaremos esto más sofisticadamente

            # ============ PASO 4: PROCESAR CON LLM ============
            logger.debug("lead_processor_calling_llm", request_id=request_id)
            result = await self.llm_service.qualify_lead(lead)

            # ============ PASO 5: PERSISTIR EN GOOGLE SHEETS ============
            decision_text = "CUALIFICADO" if result.qualification.is_qualified else "NO CUALIFICADO"

            logger.debug(
                "lead_processor_saving_to_sheets",
                request_id=request_id,
                decision=decision_text
            )

            sheets_success = await self.sheets_service.append_lead_record(
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
                raw_text=raw_text,
                decision=decision_text,
                reason=result.qualification.reason,
            )

            if not sheets_success:
                logger.warning(
                    "lead_processor_sheets_save_failed",
                    request_id=request_id
                )
                # Continuamos, no es crítico

            # ============ PASO 6: ENVIAR RESPUESTA A TELEGRAM ============
            logger.debug(
                "lead_processor_sending_telegram",
                request_id=request_id,
                chat_id=telegram_user_id
            )

            await self._send_telegram_response(
                telegram_user_id=telegram_user_id,
                qualification=result.qualification,
            )

            # ============ PASO 7: LOG DE ÉXITO ============
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "lead_processor_success",
                request_id=request_id,
                telegram_user_id=telegram_user_id,
                is_qualified=result.qualification.is_qualified,
                elapsed_ms=f"{elapsed_ms:.2f}",
                sheets_saved=sheets_success
            )

            # Advertencia si la latencia es alta
            if elapsed_ms > 5000:  # 5 segundos
                logger.warning(
                    "lead_processor_high_latency",
                    request_id=request_id,
                    elapsed_ms=f"{elapsed_ms:.2f}"
                )

            return result

        except ValueError as e:
            # Errores de validación (input inválido)
            elapsed_ms = (time.time() - start_time) * 1000
            logger.warning(
                "lead_processor_validation_failed",
                request_id=request_id,
                telegram_user_id=telegram_user_id,
                error=str(e),
                elapsed_ms=f"{elapsed_ms:.2f}"
            )

            user_message = ErrorHandler.get_user_message(e)
            await self._send_telegram_error(telegram_user_id, user_message)
            return None

        except Exception as e:
            # Errores inesperados (LLM, Sheets, etc)
            elapsed_ms = (time.time() - start_time) * 1000
            error_details = ErrorHandler.get_error_details(e)

            logger.error(
                "lead_processor_failed",
                request_id=request_id,
                telegram_user_id=telegram_user_id,
                elapsed_ms=f"{elapsed_ms:.2f}",
                **error_details
            )

            user_message = ErrorHandler.get_user_message(e)
            await self._send_telegram_error(telegram_user_id, user_message)
            return None

    def _validate_input(
        self,
        raw_text: str,
        telegram_user_id: int,
        telegram_username: Optional[str],
    ) -> LeadInput:
        """
        Valida el input del usuario.

        VALIDACIONES:
        1. Longitud mínima/máxima
        2. No vacío después de sanitizar
        3. Creación de modelo Pydantic

        Args:
            raw_text: Texto a validar
            telegram_user_id: ID del usuario
            telegram_username: Username

        Returns:
            LeadInput validado

        Raises:
            ValueError: Si la validación falla
        """
        try:
            # Validar longitud
            if not validate_text_length(raw_text):
                raise ValueError(
                    "El mensaje debe tener entre 10 y 2000 caracteres."
                )

            # Sanitizar
            sanitized_text = sanitize_input(raw_text)

            # Crear modelo Pydantic
            lead = LeadInput(
                raw_text=sanitized_text,
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
            )

            logger.debug(
                "lead_processor_input_validated",
                telegram_user_id=telegram_user_id
            )

            return lead

        except ValueError as e:
            logger.warning(
                "lead_processor_input_validation_failed",
                telegram_user_id=telegram_user_id,
                error=str(e)
            )
            raise

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
        from config.constants import (
            TELEGRAM_RESPONSE_QUALIFIED,
            TELEGRAM_RESPONSE_NOT_QUALIFIED
        )

        try:
            if qualification.is_qualified:
                message = TELEGRAM_RESPONSE_QUALIFIED.format(
                    reason=qualification.reason
                )
            else:
                message = TELEGRAM_RESPONSE_NOT_QUALIFIED.format(
                    reason=qualification.reason
                )

            success = await self.telegram_service.send_message(
                chat_id=telegram_user_id,
                message=message,
                parse_mode="Markdown"
            )

            if not success:
                logger.warning(
                    "lead_processor_telegram_response_failed",
                    telegram_user_id=telegram_user_id
                )

        except Exception as e:
            logger.error(
                "lead_processor_send_response_error",
                telegram_user_id=telegram_user_id,
                error=str(e)
            )

    async def _send_telegram_error(
        self,
        telegram_user_id: int,
        error_message: str,
    ) -> None:
        """
        Envía un mensaje de error a Telegram.

        Args:
            telegram_user_id: ID del chat
            error_message: Mensaje de error (ya amigable para usuario)
        """
        try:
            await self.telegram_service.send_message(
                chat_id=telegram_user_id,
                message=error_message,
                parse_mode="Markdown"
            )

        except Exception as e:
            logger.error(
                "lead_processor_send_error_failed",
                telegram_user_id=telegram_user_id,
                error=str(e)
            )
