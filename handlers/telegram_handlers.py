"""
Handlers para eventos de Telegram.
Recibe mensajes y los delega al procesador de leads.
"""

from typing import Optional, TYPE_CHECKING
from utils.logger import get_logger
from config.settings import Settings

if TYPE_CHECKING:
    from services.lead_processor import LeadProcessor

logger = get_logger(__name__)


class TelegramHandlers:
    """
    Manejador de eventos de Telegram.
    """

    def __init__(self, lead_processor: "LeadProcessor"):
        """
        Inicializa los handlers.

        Args:
            lead_processor: Procesador de leads
        """
        self.lead_processor = lead_processor
        logger.info("telegram_handlers_initialized")

    async def handle_message(
        self,
        message_text: str,
        user_id: int,
        username: Optional[str] = None,
    ) -> None:
        """
        Maneja un mensaje de texto recibido de Telegram.

        Args:
            message_text: Contenido del mensaje
            user_id: ID del usuario
            username: Username del usuario
        """
        logger.debug(
            "telegram_handle_message",
            user_id=user_id,
            message_length=len(message_text)
        )

        await self.lead_processor.process_lead(
            raw_text=message_text,
            telegram_user_id=user_id,
            telegram_username=username,
        )
