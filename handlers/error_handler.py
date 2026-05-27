"""
Manejador centralizado de errores.
"""

from utils.logger import get_logger

logger = get_logger(__name__)


class ErrorHandler:
    """
    Manejador centralizado de excepciones y errores.
    """

    @staticmethod
    def handle_llm_error(error: Exception) -> str:
        """Maneja errores del LLM."""
        logger.error("llm_error", error=str(error))
        return "Error al procesar con el sistema de IA"

    @staticmethod
    def handle_sheets_error(error: Exception) -> str:
        """Maneja errores de Google Sheets."""
        logger.error("sheets_error", error=str(error))
        return "Error al registrar en la base de datos"

    @staticmethod
    def handle_telegram_error(error: Exception) -> str:
        """Maneja errores de Telegram."""
        logger.error("telegram_error", error=str(error))
        return "Error al enviar el mensaje"
