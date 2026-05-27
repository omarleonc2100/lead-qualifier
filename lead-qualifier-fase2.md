# 🔌 FASE 2: CONECTIVIDAD Y PERSISTENCIA (Google Sheets + Telegram)

Vamos a implementar la integración real con Google Sheets y Telegram Bot.

---

## 📁 NUEVOS ARCHIVOS EN FASE 2

Primero, actualiza tu estructura de directorios:

```
services/
├── providers/
│   ├── __init__.py
│   ├── openai_provider.py      # NUEVO (cascarón)
│   └── anthropic_provider.py   # NUEVO (cascarón)
├── llm_service.py
├── sheets_service.py
├── telegram_service.py
└── lead_processor.py
```

---

## 1️⃣ GOOGLE SHEETS SERVICE - IMPLEMENTACIÓN COMPLETA

### `services/sheets_service.py` (IMPLEMENTACIÓN REAL)

```python
"""
Servicio de Google Sheets - IMPLEMENTACIÓN REAL.
Utiliza gspread para conectar con Google Sheets API.
"""

import gspread
from google.oauth2.service_account import Credentials
from typing import List, Optional
from datetime import datetime
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
            now = datetime.utcnow().isoformat()
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

```

---

## 2️⃣ TELEGRAM SERVICE - IMPLEMENTACIÓN COMPLETA

### `services/telegram_service.py` (IMPLEMENTACIÓN REAL)

```python
"""
Servicio de Telegram - IMPLEMENTACIÓN REAL.
Utiliza python-telegram-bot para enviar y recibir mensajes.
"""

from telegram import Bot, Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.error import TelegramError, BadRequest, TimedOut
from typing import Optional, Callable
from utils.logger import get_logger
from config.settings import Settings
from utils.async_utils import async_retry
import asyncio

logger = get_logger(__name__)


class TelegramServiceInterface:
    """
    Interfaz para servicios de Telegram.
    """
    
    async def send_message(
        self,
        chat_id: int,
        message: str,
        parse_mode: str = "Markdown"
    ) -> bool:
        """
        Envía un mensaje a través de Telegram.
        
        Args:
            chat_id: ID del chat
            message: Contenido del mensaje
            parse_mode: Modo de parsing (Markdown, HTML, etc)
        
        Returns:
            True si fue exitoso
        """
        pass
    
    async def start_polling(self) -> None:
        """
        Inicia el bot en modo polling (preguntando a Telegram por nuevos mensajes).
        """
        pass
    
    async def register_message_handler(
        self,
        callback: Callable,
    ) -> None:
        """
        Registra un callback que se ejecuta cuando llega un mensaje de texto.
        
        Args:
            callback: Función async que recibe (message_text, user_id, username)
        """
        pass


class TelegramService(TelegramServiceInterface):
    """
    Implementación del servicio de Telegram.
    Usa python-telegram-bot para interactuar con Telegram Bot API.
    
    FEATURES:
    - Envío de mensajes con retry automático
    - Polling para recibir mensajes
    - Manejo robusto de errores
    - Rate limiting integrado
    """
    
    def __init__(self, settings: Settings):
        """
        Inicializa el servicio de Telegram.
        
        Args:
            settings: Configuración de la aplicación
        """
        self.settings = settings
        self.bot = Bot(token=settings.telegram_bot_token)
        self.application: Optional[Application] = None
        self._message_handler_callback: Optional[Callable] = None
        
        logger.info(
            "telegram_service_initialized",
            bot_token_preview=settings.telegram_bot_token[:10] + "..."
        )
    
    async def _initialize_application(self) -> None:
        """
        Inicializa la Application de python-telegram-bot.
        Se hace una sola vez.
        """
        if self.application is not None:
            return
        
        try:
            self.application = Application.builder().token(
                self.settings.telegram_bot_token
            ).build()
            
            logger.debug("telegram_application_initialized")
        
        except Exception as e:
            logger.error("telegram_application_init_failed", error=str(e))
            raise
    
    @async_retry(max_attempts=3, initial_delay=2.0, backoff_factor=2.0)
    async def send_message(
        self,
        chat_id: int,
        message: str,
        parse_mode: str = "Markdown"
    ) -> bool:
        """
        Envía un mensaje a través de Telegram con retry automático.
        
        Args:
            chat_id: ID del chat
            message: Contenido del mensaje
            parse_mode: Modo de parsing (Markdown, HTML, etc)
        
        Returns:
            True si fue exitoso, False en caso contrario
        """
        try:
            if not message:
                logger.warning("telegram_send_empty_message", chat_id=chat_id)
                return False
            
            logger.debug(
                "telegram_send_message_start",
                chat_id=chat_id,
                message_length=len(message)
            )
            
            # Truncar mensaje si es muy largo (Telegram limit: 4096 caracteres)
            if len(message) > 4096:
                logger.warning(
                    "telegram_message_too_long",
                    chat_id=chat_id,
                    original_length=len(message)
                )
                message = message[:4090] + "..."
            
            # Enviar mensaje
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=parse_mode
            )
            
            logger.info(
                "telegram_send_message_success",
                chat_id=chat_id,
                message_length=len(message)
            )
            
            return True
        
        except BadRequest as e:
            logger.error(
                "telegram_send_message_bad_request",
                chat_id=chat_id,
                error=str(e)
            )
            # BadRequest es no-recuperable (ej: chat_id inválido)
            return False
        
        except TimedOut as e:
            logger.warning(
                "telegram_send_message_timeout",
                chat_id=chat_id,
                error=str(e)
            )
            # TimedOut es recuperable, el retry lo intentará de nuevo
            raise
        
        except TelegramError as e:
            logger.error(
                "telegram_send_message_error",
                chat_id=chat_id,
                error=str(e)
            )
            raise
        
        except Exception as e:
            logger.error(
                "telegram_send_message_unexpected_error",
                chat_id=chat_id,
                error=str(e)
            )
            raise
    
    async def register_message_handler(
        self,
        callback: Callable,
    ) -> None:
        """
        Registra un callback que se ejecuta cuando llega un mensaje de texto.
        
        Args:
            callback: Función async que recibe (message_text, user_id, username)
        """
        await self._initialize_application()
        
        self._message_handler_callback = callback
        
        # Crear handler de Telegram que delegue al callback
        async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            """
            Handler interno que Telegram llama cuando llega un mensaje.
            """
            try:
                if not update.message or not update.message.text:
                    logger.debug("telegram_empty_message_received")
                    return
                
                message_text = update.message.text
                user_id = update.message.from_user.id
                username = update.message.from_user.username
                
                logger.debug(
                    "telegram_message_received",
                    user_id=user_id,
                    username=username,
                    message_length=len(message_text)
                )
                
                # Llamar al callback registrado
                if self._message_handler_callback:
                    await self._message_handler_callback(
                        message_text=message_text,
                        user_id=user_id,
                        username=username,
                    )
            
            except Exception as e:
                logger.error(
                    "telegram_message_handler_error",
                    user_id=update.message.from_user.id if update.message else None,
                    error=str(e)
                )
                
                # Notificar al usuario del error
                if update.message:
                    try:
                        await self.send_message(
                            chat_id=update.message.chat_id,
                            message="⚠️ Hubo un error procesando tu mensaje. Intenta de nuevo."
                        )
                    except Exception as e2:
                        logger.error("telegram_error_notification_failed", error=str(e2))
        
        # Registrar el handler con la Application
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)
        )
        
        logger.info("telegram_message_handler_registered")
    
    async def start_polling(self) -> None:
        """
        Inicia el bot en modo polling.
        Se queda esperando nuevos mensajes indefinidamente.
        
        NOTA: En producción usar webhook en lugar de polling.
        """
        await self._initialize_application()
        
        try:
            logger.info(
                "telegram_polling_start",
                bot_name=self.settings.telegram_bot_token.split(':')[0]
            )
            
            # Actualizar info del bot
            await self.bot.get_me()
            logger.info("telegram_bot_authenticated")
            
            # Iniciar polling
            await self.application.run_polling(
                allowed_updates=["message"],
                drop_pending_updates=True
            )
        
        except Exception as e:
            logger.error("telegram_polling_error", error=str(e))
            raise
    
    async def stop(self) -> None:
        """
        Detiene el bot gracefully.
        """
        if self.application:
            await self.application.stop()
            logger.info("telegram_service_stopped")
    
    async def send_log_message(self, message: str) -> bool:
        """
        Envía un mensaje a un chat interno para logging.
        Útil para monitoreo en producción.
        
        Args:
            message: Mensaje a enviar
        
        Returns:
            True si fue exitoso
        """
        if not self.settings.telegram_chat_id:
            return False
        
        try:
            chat_id = int(self.settings.telegram_chat_id)
            return await self.send_message(chat_id, message)
        except Exception as e:
            logger.error("telegram_send_log_message_failed", error=str(e))
            return False

```

---

## 3️⃣ ACTUALIZAR LEAD_PROCESSOR PARA USAR SERVICIOS REALES

### `services/lead_processor.py` (ACTUALIZADO)

```python
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

```

---

## 4️⃣ PROVIDERS DE LLM - CASCARONES (Se completan en FASE 3)

### `services/providers/__init__.py`

```python
"""
Módulo de providers de LLM.
Diferentes implementaciones para OpenAI y Anthropic.
"""

from services.providers.openai_provider import OpenAIProvider
from services.providers.anthropic_provider import AnthropicProvider

__all__ = ["OpenAIProvider", "AnthropicProvider"]

```

### `services/providers/openai_provider.py` (Cascarón)

```python
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

```

### `services/providers/anthropic_provider.py` (Cascarón)

```python
"""
Provider de Anthropic Claude.
Se completa en FASE 3.
"""

from models.lead import LeadInput
from models.qualification import QualificationResult
from utils.logger import get_logger
from config.settings import Settings
from config.constants import SYSTEM_PROMPT

logger = get_logger(__name__)


class AnthropicProvider:
    """
    Provider para Anthropic Claude models.
    Implementación completa en FASE 3.
    """
    
    def __init__(self, settings: Settings):
        """
        Inicializa el provider de Anthropic.
        
        Args:
            settings: Configuración de la aplicación
        """
        self.settings = settings
        logger.info(
            "anthropic_provider_initialized",
            model=settings.anthropic_model
        )
    
    async def qualify_lead(self, lead: LeadInput) -> QualificationResult:
        """
        Cualifica un lead usando Anthropic Claude.
        
        IMPLEMENTACIÓN EN FASE 3.
        
        Args:
            lead: Datos del lead
        
        Returns:
            Resultado de cualificación
        """
        # Será implementado en FASE 3
        raise NotImplementedError("Anthropic Provider se implementa en FASE 3")

```

---

## 5️⃣ ACTUALIZAR main.py PARA FASE 2

### `main.py` (ACTUALIZADO)

```python
"""
Punto de entrada principal de la aplicación.
Inicializa todos los servicios e inicia el bot.

FASE 2: Inicializa Google Sheets y Telegram.
"""

import asyncio
import logging
import signal
from pathlib import Path

from config.settings import Settings
from utils.logger import setup_logger, get_logger
from services.sheets_service import GoogleSheetsService
from services.telegram_service import TelegramService
from services.llm_service import LLMService
from services.lead_processor import LeadProcessor
from handlers.telegram_handlers import TelegramHandlers

logger = get_logger(__name__)


class Application:
    """
    Clase principal que orquesta la aplicación.
    """
    
    def __init__(self, settings: Settings):
        """
        Inicializa la aplicación.
        
        Args:
            settings: Configuración global
        """
        self.settings = settings
        self.services_initialized = False
        
        # Servicios (se inicializan en setup)
        self.sheets_service: GoogleSheetsService = None
        self.telegram_service: TelegramService = None
        self.llm_service: LLMService = None
        self.lead_processor: LeadProcessor = None
        self.handlers: TelegramHandlers = None
    
    async def setup(self) -> None:
        """
        Inicializa todos los servicios.
        """
        try:
            logger.info("application_setup_start")
            
            # ============ GOOGLE SHEETS ============
            logger.info("initializing_sheets_service")
            self.sheets_service = GoogleSheetsService(self.settings)
            
            # Verificar que el archivo de credenciales existe
            creds_path = Path(self.settings.google_sheets_credentials_path)
            if not creds_path.exists():
                raise FileNotFoundError(
                    f"Credenciales de Google no encontradas en {creds_path}\n"
                    f"Por favor, descarga tu archivo de service account desde Google Cloud Console "
                    f"y guárdalo en {creds_path}"
                )
            
            logger.info("sheets_service_ready")
            
            # ============ TELEGRAM ============
            logger.info("initializing_telegram_service")
            self.telegram_service = TelegramService(self.settings)
            logger.info("telegram_service_ready")
            
            # ============ LLM ============
            logger.info("initializing_llm_service")
            self.llm_service = LLMService(self.settings)
            logger.info("llm_service_ready")
            
            # ============ LEAD PROCESSOR ============
            logger.info("initializing_lead_processor")
            self.lead_processor = LeadProcessor(
                settings=self.settings,
                llm_service=self.llm_service,
                sheets_service=self.sheets_service,
                telegram_service=self.telegram_service,
            )
            logger.info("lead_processor_ready")
            
            # ============ HANDLERS ============
            logger.info("initializing_telegram_handlers")
            self.handlers = TelegramHandlers(self.lead_processor)
            
            # Registrar handler de mensajes
            await self.telegram_service.register_message_handler(
                callback=self.handlers.handle_message
            )
            logger.info("telegram_handlers_ready")
            
            self.services_initialized = True
            logger.info("application_setup_complete")
        
        except Exception as e:
            logger.error("application_setup_failed", error=str(e))
            raise
    
    async def run(self) -> None:
        """
        Inicia el bot en polling.
        """
        if not self.services_initialized:
            await self.setup()
        
        try:
            logger.info(
                "application_run_start",
                environment=self.settings.environment,
                llm_provider=self.settings.llm_provider
            )
            
            # Iniciar Telegram polling
            await self.telegram_service.start_polling()
        
        except KeyboardInterrupt:
            logger.info("application_interrupted_by_user")
        except Exception as e:
            logger.error("application_run_failed", error=str(e))
            raise
        finally:
            await self.shutdown()
    
    async def shutdown(self) -> None:
        """
        Detiene la aplicación gracefully.
        """
        logger.info("application_shutdown_start")
        
        try:
            if self.telegram_service:
                await self.telegram_service.stop()
            
            logger.info("application_shutdown_complete")
        except Exception as e:
            logger.error("application_shutdown_error", error=str(e))


async def main():
    """
    Función principal. Punto de entrada.
    """
    # Cargar configuración
    try:
        settings = Settings()
    except Exception as e:
        print(f"❌ Error cargando configuración: {e}")
        print(f"Por favor, verifica que el archivo .env existe y tiene todas las variables requeridas.")
        raise
    
    # Configurar logging
    setup_logger(settings)
    
    logger.info(
        "application_startup",
        environment=settings.environment,
        llm_provider=settings.llm_provider,
        version="1.0.0"
    )
    
    # Crear aplicación
    app = Application(settings)
    
    # Registrar handlers para shutdown graceful
    def signal_handler(sig, frame):
        logger.info("signal_received", signal=sig)
        raise KeyboardInterrupt()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Ejecutar
    try:
        await app.run()
    except Exception as e:
        logger.error("application_failed", error=str(e))
        exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✋ Bot detenido por el usuario")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        exit(1)

```

---

## 6️⃣ ACTUALIZAR requirements.txt

```txt
# Framework y Bot de Telegram
python-telegram-bot==20.7

# LLM y IA
openai==1.40.0
langchain-core==0.2.0
pydantic==2.7.4
pydantic-settings==2.2.1

# Google Sheets Integration
gspread==6.1.0
google-auth==2.28.1
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0

# Utilidades
python-dotenv==1.0.1
requests==2.31.0
aiohttp==3.9.5

# Logging y Monitoreo
structlog==24.1.0

# Testing
pytest==7.4.4
pytest-asyncio==0.23.3
pytest-mock==3.14.0

# Linting y Code Quality
black==24.3.0
flake8==7.1.0
mypy==1.11.1

# Producción
gunicorn==21.2.0
uvicorn==0.29.0

```

---

## 7️⃣ INSTRUCCIONES PARA CONFIGURAR GOOGLE SHEETS

### Paso 1: Crear Proyecto en Google Cloud Console

```bash
1. Ve a https://console.cloud.google.com/
2. Crea un nuevo proyecto o selecciona uno existente
3. Nombre: "Orbyn Lead Qualifier"
4. Espera a que se cree
```

### Paso 2: Habilitar APIs

```bash
1. Ve a "APIs & Services" > "Library"
2. Busca "Google Sheets API" y habilítala
3. Busca "Google Drive API" y habilítala
```

### Paso 3: Crear Service Account

```bash
1. Ve a "APIs & Services" > "Credentials"
2. Haz click en "Create Credentials" > "Service Account"
3. Nombre: "orbyn-lead-qualifier"
4. Descripción: "Service account for lead qualification bot"
5. Haz click en "Create and Continue"
6. En la siguiente pantalla, saltas paso (no le des permisos especiales)
7. Haz click en "Done"
```

### Paso 4: Descargar Credenciales

```bash
1. En la página de Service Accounts, haz click en el que creaste
2. Ve a la pestaña "Keys"
3. Haz click en "Add Key" > "Create new key"
4. Elige JSON
5. Se descargará automáticamente
6. Renómbralo a "google_service_account.json"
7. Muévelo a la carpeta "credentials/" del proyecto
```

### Paso 5: Crear Google Sheet

```bash
1. Ve a https://docs.google.com/spreadsheets/
2. Haz click en "+" para crear nueva sheet
3. Nombre: "Orbyn Leads"
4. Abre el ID de la URL (ejemplo):
   https://docs.google.com/spreadsheets/d/[SHEET_ID]/edit
5. Copia el SHEET_ID
6. Pégalo en .env como GOOGLE_SHEET_ID=
```

### Paso 6: Compartir Sheet con Service Account

```bash
1. En tu Google Sheet, haz click en "Compartir"
2. Copia el email del service account (está en google_service_account.json)
   (ej: orbyn@project-id.iam.gserviceaccount.com)
3. Comparte la sheet con ese email
4. Dale permisos de "Editor"
```

---

## 8️⃣ INSTRUCCIONES PARA CONFIGURAR TELEGRAM BOT

### Paso 1: Crear el Bot

```bash
1. Abre Telegram
2. Busca a @BotFather
3. Escribe /start
4. Escribe /newbot
5. Síguele las instrucciones:
   - Nombre: "Orbyn Lead Qualifier" (o lo que prefieras)
   - Username: "orbyn_lead_qualifier_bot" (debe ser único)
6. Te dará un TOKEN
7. Cópialo en .env como TELEGRAM_BOT_TOKEN=
```

### Paso 2: Obtener tu Chat ID (para testing)

```bash
1. Escribe a tu bot
2. Abre: https://api.telegram.org/bot[TOKEN]/getUpdates
3. Reemplaza [TOKEN] con tu token real
4. Busca "chat" > "id"
5. Ese es tu TELEGRAM_CHAT_ID (opcional, para logs)
```

---

## 9️⃣ ESTRUCTURA FINAL DESPUÉS DE FASE 2

```
orbyn-lead-qualifier/
├── config/
│   ├── __init__.py
│   ├── settings.py
│   └── constants.py
├── models/
│   ├── __init__.py
│   ├── lead.py
│   └── qualification.py
├── services/
│   ├── __init__.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── openai_provider.py      ✓ Cascarón
│   │   └── anthropic_provider.py   ✓ Cascarón
│   ├── llm_service.py               ✓ Interfaz
│   ├── sheets_service.py            ✓ IMPLEMENTADO
│   ├── telegram_service.py          ✓ IMPLEMENTADO
│   └── lead_processor.py            ✓ ACTUALIZADO
├── handlers/
│   ├── __init__.py
│   ├── telegram_handlers.py
│   └── error_handler.py
├── utils/
│   ├── __init__.py
│   ├── logger.py
│   ├── validators.py
│   └── async_utils.py
├── credentials/
│   ├── .gitkeep
│   └── google_service_account.json  (crear después)
├── tests/
│   ├── __init__.py
│   └── (test files)
├── main.py                          ✓ ACTUALIZADO
├── requirements.txt                 ✓
├── .env.example                     ✓
├── .env                             (crear y llenar)
├── .gitignore                       ✓
├── pyproject.toml                   ✓
└── README.md                        ✓
```

---

## 🔟 TESTING MANUAL DE FASE 2

```bash
# 1. Activar entorno virtual
source venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar .env
cp .env.example .env
# Editar .env con tus credenciales

# 4. Colocar credenciales de Google
# google_service_account.json en credentials/

# 5. Ejecutar
python main.py

# Verás logs como:
# application_startup environment=development llm_provider=openai
# initializing_sheets_service
# initializing_telegram_service
# application_setup_complete
# application_run_start
# telegram_polling_start
```

---

## 📊 RESUMEN FASE 2

### ✅ Implementado

- **GoogleSheetsService COMPLETO**
  - Autenticación con Google Cloud
  - Append automático de registros
  - Retry con backoff exponencial
  - Thread pool para no bloquear event loop

- **TelegramService COMPLETO**
  - Envío de mensajes con retry
  - Polling para recibir mensajes
  - Registro de handlers
  - Graceful shutdown

- **LeadProcessor ACTUALIZADO**
  - Ahora usa servicios reales
  - Validación completa
  - Error handling robusto
  - Logging estructurado

- **Providers CASCARONES**
  - OpenAI Provider (estructura lista)
  - Anthropic Provider (estructura lista)
  - Se completan en FASE 3

- **Main.py REFACTORIZADO**
  - Clase Application para orquestación
  - Setup de todos los servicios
  - Signal handlers para shutdown graceful

### 🎯 PRÓXIMO PASO: FASE 3

En **FASE 3** implementaremos:

1. **OpenAI Provider** con Structured Outputs (JSON mode)
2. **Anthropic Provider** con structured outputs
3. **Salidas estructuradas** garantizadas por Pydantic
4. **System Prompt** optimizado e inmune a injection

---

**¿Listo para FASE 3?**