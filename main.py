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
