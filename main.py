"""
Punto de entrada principal de la aplicación.
Inicializa todos los servicios e inicia el bot.
"""

import asyncio
import logging
from config.settings import Settings
from utils.logger import setup_logger, get_logger

logger = get_logger(__name__)


async def main():
    """
    Función principal. Inicializa la aplicación.
    """
    # Cargar configuración
    settings = Settings()

    # Configurar logging
    setup_logger(settings)

    logger.info(
        "application_startup",
        environment=settings.environment,
        llm_provider=settings.llm_provider
    )

    # FASE 2: Aquí inicializaremos los servicios
    # Por ahora solo inicializamos la configuración

    logger.info("application_ready", version="1.0.0")

    # En desarrollo, mantener la aplicación corriendo
    if settings.is_development():
        logger.info("development_mode_active")
        try:
            await asyncio.sleep(float('inf'))
        except KeyboardInterrupt:
            logger.info("application_shutdown")


if __name__ == "__main__":
    asyncio.run(main())
