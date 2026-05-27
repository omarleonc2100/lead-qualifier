"""
Servicio de procesamiento de leads.
Orquesta el flujo completo: validación -> LLM -> Google Sheets -> Telegram.

ACTUALIZADO PARA FASE 2: Ahora usa servicios reales.
"""

from typing import Optional
from models.lead import LeadInput
from models.qualification import QualificationResult
from utils.logger import get_logger
from utils.validators import sanitize_input, detect_prompt_injection, validate_text_length
from config.settings import Settings
from config.constants import TELEGRAM_RESPONSE_ERROR
from datetime import datetime
import time

logger = get_logger(__name__)


class LeadProcessor:
    """
    Orquestador principal del procesamiento de leads.
    Coordina LLM, Google Sheets y Telegram.
    
    FLUJO:
    1. Validar input (Pydantic + custom validators)
    2. Detectar prompt injection
    3. Llamar LLM para cualificar
    4. Guardar en Google Sheets
    5. Enviar respuesta a Telegram
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
        
        PASOS:
        1. Validar input
        2. Verificar prompt injection
        3. Procesar con LLM
        4. Guardar en Google Sheets
        5. Enviar respuesta a Telegram
        
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
            
            # ============ PASO 1: VALIDACIÓN DE INPUT ============
            lead = self._validate_input(
                raw_text=raw_text,
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
            )
            
            # ============ PASO 2: VERIFICAR PROMPT INJECTION ============
            if self.settings.enable_prompt_injection_check:
                if detect_prompt_injection(lead.raw_text):
                    logger.warning(
                        "prompt_injection_detected",
                        request_id=request_id,
                        telegram_user_id=telegram_user_id
                    )
                    # En FASE 5 manejaremos esto más sofisticadamente
            
            # ============ PASO 3: PROCESAR CON LLM ============
            logger.debug("lead_processor_calling_llm", request_id=request_id)
            result = await self.llm_service.qualify_lead(lead)
            
            # ============ PASO 4: PERSISTIR EN GOOGLE SHEETS ============
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
            
            # ============ PASO 5: ENVIAR RESPUESTA A TELEGRAM ============
            logger.debug(
                "lead_processor_sending_telegram",
                request_id=request_id,
                chat_id=telegram_user_id
            )
            
            await self._send_telegram_response(
                telegram_user_id=telegram_user_id,
                qualification=result.qualification,
            )
            
            # ============ LOG DE ÉXITO ============
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "lead_processor_success",
                request_id=request_id,
                telegram_user_id=telegram_user_id,
                is_qualified=result.qualification.is_qualified,
                elapsed_ms=f"{elapsed_ms:.2f}",
                sheets_saved=sheets_success
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
            
            await self._send_telegram_error(
                telegram_user_id,
                "El formato de tu mensaje no es válido. Intenta describir tu empresa con más detalle."
            )
            return None
        
        except Exception as e:
            # Errores inesperados (LLM, Sheets, etc)
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                "lead_processor_failed",
                request_id=request_id,
                telegram_user_id=telegram_user_id,
                error=str(e),
                error_type=type(e).__name__,
                elapsed_ms=f"{elapsed_ms:.2f}"
            )
            
            await self._send_telegram_error(
                telegram_user_id,
                "Ocurrió un error procesando tu solicitud. Por favor, intenta de nuevo en unos momentos."
            )
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
        3. Creación de modelo Pydantic (valida automáticamente tipos y constraints)
        
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
            
            # Crear modelo Pydantic (valida automáticamente tipos y constraints)
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
            error_message: Mensaje de error
        """
        try:
            message = TELEGRAM_RESPONSE_ERROR.format(
                error_message=error_message[:100]
            )
            
            await self.telegram_service.send_message(
                chat_id=telegram_user_id,
                message=message,
                parse_mode="Markdown"
            )
        
        except Exception as e:
            logger.error(
                "lead_processor_send_error_failed",
                telegram_user_id=telegram_user_id,
                error=str(e)
            )
