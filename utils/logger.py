"""
Configuración centralizada de logging.
Usa structlog para logs estructurados y fáciles de parsear.
"""

import logging
import structlog
from typing import Optional
from config.settings import Settings


def setup_logger(settings: Settings) -> None:
    """
    Configura el sistema de logging para toda la aplicación.
    Usa structlog para logs estructurados.
    """

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=settings.get_log_level(),
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Obtiene un logger ya configurado para un módulo.

    Args:
        name: Nombre del módulo (__name__)

    Returns:
        Logger estructurado
    """
    return structlog.get_logger(name)
