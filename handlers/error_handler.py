"""
Manejador centralizado de errores.
FASE 4: Mapeo de excepciones a mensajes amigables para el usuario.
"""

from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class ErrorHandler:
    """
    Manejador centralizado de excepciones.
    Traduce errores técnicos a mensajes amigables.
    """
    
    # Mapeo de tipos de error a mensajes para usuario
    ERROR_MESSAGES = {
        "llm_timeout": "⏱️ La evaluación tardó demasiado. Por favor, intenta de nuevo.",
        "llm_rate_limit": "⚠️ Estamos recibiendo muchas solicitudes. Intenta de nuevo en unos momentos.",
        "llm_auth_error": "🔐 Error de autenticación con el servicio de IA. Contacta a support.",
        "sheets_write_error": "📊 No pudimos guardar tu información. Intenta de nuevo.",
        "telegram_send_error": "📱 Error enviando respuesta. Por favor, intenta de nuevo.",
        "validation_error": "❌ El formato de tu mensaje no es válido. Por favor, proporciona más detalles.",
        "network_error": "🌐 Error de conexión. Verifica tu conexión a internet.",
        "unknown_error": "❓ Ocurrió un error inesperado. Por favor, intenta de nuevo.",
    }
    
    @staticmethod
    def classify_error(error: Exception) -> str:
        """
        Clasifica una excepción para determinar el tipo de error.
        
        Args:
            error: Excepción a clasificar
        
        Returns:
            Tipo de error (key en ERROR_MESSAGES)
        """
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        # Mapeo por tipo de excepción
        if "timeout" in error_str or "timed out" in error_str:
            return "llm_timeout"
        
        elif "rate" in error_str or "quota" in error_str:
            return "llm_rate_limit"
        
        elif "auth" in error_str or "unauthorized" in error_str or "forbidden" in error_str:
            return "llm_auth_error"
        
        elif "sheets" in error_str or "spreadsheet" in error_str:
            return "sheets_write_error"
        
        elif "telegram" in error_str or "chat_id" in error_str:
            return "telegram_send_error"
        
        elif "validation" in error_str or error_type == "ValidationError":
            return "validation_error"
        
        elif "connection" in error_str or "network" in error_str:
            return "network_error"
        
        return "unknown_error"
    
    @staticmethod
    def get_user_message(error: Exception) -> str:
        """
        Obtiene el mensaje amigable para el usuario.
        
        Args:
            error: Excepción
        
        Returns:
            Mensaje para mostrar al usuario
        """
        error_type = ErrorHandler.classify_error(error)
        message = ErrorHandler.ERROR_MESSAGES.get(
            error_type,
            ErrorHandler.ERROR_MESSAGES["unknown_error"]
        )
        
        logger.debug(
            "error_classified",
            error_type=error_type,
            original_error=str(error)
        )
        
        return message
    
    @staticmethod
    def should_retry(error: Exception) -> bool:
        """
        Determina si un error es recuperable y debe reintentar.
        
        Args:
            error: Excepción
        
        Returns:
            True si debe reintentar
        """
        error_type = ErrorHandler.classify_error(error)
        
        # Errores recuperables
        recoverable_errors = {
            "llm_timeout",
            "llm_rate_limit",
            "sheets_write_error",
            "network_error",
        }
        
        return error_type in recoverable_errors
    
    @staticmethod
    def get_error_details(error: Exception) -> dict:
        """
        Extrae detalles técnicos del error para logging.
        
        Args:
            error: Excepción
        
        Returns:
            Diccionario con detalles
        """
        return {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "error_classified": ErrorHandler.classify_error(error),
            "should_retry": ErrorHandler.should_retry(error),
        }
