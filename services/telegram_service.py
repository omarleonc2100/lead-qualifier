"""
Servicio de Telegram.
Abstrae la integración con Telegram Bot API.
"""

from abc import ABC, abstractmethod
from typing import Optional
from utils.logger import get_logger
from config.settings import Settings

logger = get_logger(__name__)


class TelegramServiceInterface(ABC):
    """
    Interfaz para servicios de Telegram.
    """

    @abstractmethod
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


class TelegramService(TelegramServiceInterface):
    """
    Implementación del servicio de Telegram.
    Usa python-telegram-bot.
    """

    def __init__(self, settings: Settings):
        """
        Inicializa el servicio de Telegram.

        Args:
            settings: Configuración de la aplicación
        """
        self.settings = settings
        self._application = None

        logger.info("telegram_service_initialized")

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
            parse_mode: Modo de parsing

        Returns:
            True si fue exitoso
        """
        try:
            # Será implementado en FASE 2
            logger.debug(
                "telegram_send_message_placeholder",
                chat_id=chat_id,
                message_length=len(message)
            )
            return True

        except Exception as e:
            logger.error(
                "telegram_send_message_failed",
                chat_id=chat_id,
                error=str(e)
            )
            return False
