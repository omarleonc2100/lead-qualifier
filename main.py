"""
Punto de entrada principal de la aplicación.
FASE 3: Agregamos test de conexión con LLM antes de iniciar.
"""

import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

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
        
        # Servicios
        self.sheets_service: Optional[GoogleSheetsService] = None
        self.telegram_service: Optional[TelegramService] = None
        self.llm_service: Optional[LLMService] = None
        self.lead_processor: Optional[LeadProcessor] = None
        self.handlers: Optional[TelegramHandlers] = None
    
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
                    f"❌ Credenciales de Google no encontradas en {creds_path}\n"
                    f"   Pasos para configurar:\n"
                    f"   1. Descarga json de service account desde Google Cloud Console\n"
                    f"   2. Guárdalo en: {creds_path}\n"
                    f"   3. Comparte tu Google Sheet con el email del service account"
                )
            
            logger.info("sheets_service_ready")
            
            # ============ TELEGRAM ============
            logger.info("initializing_telegram_service")
            self.telegram_service = TelegramService(self.settings)
            logger.info("telegram_service_ready")
            
            # ============ LLM ============
            logger.info("initializing_llm_service")
            self.llm_service = LLMService(self.settings)
            
            # TEST: Verificar conexión con LLM
            logger.info(
                "testing_llm_connection",
                provider=self.llm_service.get_provider_name()
            )
            llm_connected = await self.llm_service.test_connection()
            
            if not llm_connected:
                raise RuntimeError(
                    f"❌ No se pudo conectar con {self.settings.llm_provider}\n"
                    f"   Verifica:\n"
                    f"   - Clave API correcta en .env\n"
                    f"   - Acceso a internet disponible\n"
                    f"   - Cuota de API disponible"
                )
            
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
        
        except FileNotFoundError as e:
            logger.error("application_setup_file_not_found", error=str(e))
            print(f"\n{e}")
            raise
        except RuntimeError as e:
            logger.error("application_setup_runtime_error", error=str(e))
            print(f"\n{e}")
            raise
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
                llm_provider=self.settings.llm_provider,
                llm_model=self.llm_service.get_provider_name()
            )
            
            print("\n" + "=" * 60)
            print("✅ Bot de Orbyn iniciado correctamente")
            print("=" * 60)
            print(f"📍 Proveedor LLM: {self.settings.llm_provider.upper()}")
            print(f"🤖 Modelo: {self.llm_service._get_model_name()}")
            print(f"📊 Google Sheet: {self.settings.google_sheet_id}")
            print("=" * 60)
            print("\n⏳ Esperando mensajes en Telegram...\n")
            
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
        print(f"\n❌ Error cargando configuración: {e}")
        print(f"\n   Por favor, verifica que el archivo .env existe y tiene todas las variables requeridas:")
        print(f"   - TELEGRAM_BOT_TOKEN")
        print(f"   - OPENAI_API_KEY (o ANTHROPIC_API_KEY)")
        print(f"   - GOOGLE_SHEET_ID")
        print(f"   - GOOGLE_SHEETS_CREDENTIALS_PATH")
        raise
    
    # Configurar logging
    setup_logger(settings)
    
    logger.info(
        "application_startup",
        environment=settings.environment,
        llm_provider=settings.llm_provider,
        version="3.0.0"
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
        print(f"\n❌ Error fatal: {e}")
        exit(1)
