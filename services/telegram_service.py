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
