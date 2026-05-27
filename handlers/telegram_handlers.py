"""
Handlers para eventos de Telegram.
FASE 4: Implementación completa con manejo de concurrencia y rate limiting.

FEATURES:
- Rate limiting por usuario
- Manejo de comandos (/start, /help)
- Procesamiento asincrónico de leads
- Debouncing (evitar duplicados)
- Mensajes de bienvenida y ayuda
"""

from typing import Optional, Dict
from datetime import datetime, timedelta
from utils.logger import get_logger
from config.settings import Settings
import asyncio

logger = get_logger(__name__)


class TelegramHandlers:
    """
    Manejador de eventos de Telegram.
    
    RESPONSABILIDADES:
    1. Recibir mensajes de Telegram
    2. Aplicar rate limiting
    3. Validar tipo de mensaje
    4. Delegar a LeadProcessor
    5. Manejar comandos especiales
    """
    
    def __init__(self, lead_processor: "LeadProcessor"):
        """
        Inicializa los handlers.
        
        Args:
            lead_processor: Procesador de leads
        """
        self.lead_processor = lead_processor
        
        # Rate limiting: {user_id: [timestamps]}
        self._user_requests: Dict[int, list] = {}
        
        # Debouncing: {user_id: timestamp_último_mensaje}
        self._user_last_request: Dict[int, datetime] = {}
        
        logger.info("telegram_handlers_initialized")
    
    async def handle_message(
        self,
        message_text: str,
        user_id: int,
        username: Optional[str] = None,
    ) -> None:
        """
        Maneja un mensaje de texto recibido de Telegram.
        
        FLUJO:
        1. Validar que no sea comando
        2. Aplicar rate limiting
        3. Aplicar debouncing
        4. Procesar con LeadProcessor
        
        Args:
            message_text: Contenido del mensaje
            user_id: ID del usuario
            username: Username del usuario
        """
        try:
            logger.debug(
                "telegram_handle_message",
                user_id=user_id,
                username=username,
                message_length=len(message_text)
            )
            
            # ============ PASO 1: VALIDAR COMANDO ============
            if message_text.startswith('/'):
                await self._handle_command(message_text, user_id)
                return
            
            # ============ PASO 2: RATE LIMITING ============
            if not self._check_rate_limit(user_id):
                logger.warning(
                    "rate_limit_exceeded",
                    user_id=user_id,
                    limit=self.lead_processor.settings.rate_limit_per_minute
                )
                await self.lead_processor.telegram_service.send_message(
                    chat_id=user_id,
                    message="⏱️ Estás enviando demasiados mensajes. Espera un momento antes de enviar otro."
                )
                return
            
            # ============ PASO 3: DEBOUNCING ============
            if not self._check_debounce(user_id):
                logger.debug("message_debounced", user_id=user_id)
                return
            
            # ============ PASO 4: PROCESAR LEAD ============
            # Procesar de forma no-bloqueante
            asyncio.create_task(
                self.lead_processor.process_lead(
                    raw_text=message_text,
                    telegram_user_id=user_id,
                    telegram_username=username,
                )
            )
        
        except Exception as e:
            logger.error(
                "telegram_handle_message_error",
                user_id=user_id,
                error=str(e)
            )
            
            try:
                await self.lead_processor.telegram_service.send_message(
                    chat_id=user_id,
                    message="⚠️ Ocurrió un error procesando tu mensaje. Por favor, intenta de nuevo."
                )
            except Exception as e2:
                logger.error("telegram_error_response_failed", error=str(e2))
    
    async def _handle_command(self, command: str, user_id: int) -> None:
        """
        Maneja comandos especiales (ej: /start, /help).
        
        Args:
            command: Comando recibido (ej: /start)
            user_id: ID del usuario
        """
        command = command.lower().strip()
        
        try:
            if command == "/start":
                await self._send_welcome_message(user_id)
            
            elif command == "/help":
                await self._send_help_message(user_id)
            
            elif command == "/info":
                await self._send_info_message(user_id)
            
            else:
                await self.lead_processor.telegram_service.send_message(
                    chat_id=user_id,
                    message="❓ Comando no reconocido. Escribe /help para ver los comandos disponibles."
                )
            
            logger.debug("command_handled", user_id=user_id, command=command)
        
        except Exception as e:
            logger.error("telegram_command_error", user_id=user_id, error=str(e))
    
    async def _send_welcome_message(self, user_id: int) -> None:
        """Envía mensaje de bienvenida."""
        message = """👋 ¡Bienvenido a Orbyn Lead Qualifier!

Soy un bot que evalúa si tu empresa cumple con los criterios de Orbyn.

📋 *¿Cómo funciono?*
1. Describe tu empresa en texto libre
2. Yo analizo si cumples con nuestro ICP
3. Te doy una respuesta inmediata

✅ *Criterios de cualificación:*
- Tipo: Empresa de servicios, consultoría o tecnología
- Tamaño: Mínimo 5 empleados
- Ubicación: España o Latinoamérica
- Interés: Automatización o Inteligencia Artificial

📝 *Ejemplo:*
"Somos una consultora en Madrid con 20 empleados, especializados en transformación digital y buscamos soluciones de IA"

🆘 *Comandos:*
/start - Este mensaje
/help - Cómo usar el bot
/info - Información sobre Orbyn

¡Adelante, cuéntame sobre tu empresa! 🚀"""
        
        await self.lead_processor.telegram_service.send_message(
            chat_id=user_id,
            message=message
        )
    
    async def _send_help_message(self, user_id: int) -> None:
        """Envía mensaje de ayuda."""
        message = """🆘 *Guía de Uso*

*Paso 1: Describe tu empresa*
Escribe un mensaje con información sobre tu empresa. Incluye:
- Tipo de empresa (consultoría, servicios, etc.)
- Cantidad de empleados
- Ubicación
- Qué soluciones buscas (automatización, IA, etc.)

*Paso 2: Recibe evaluación*
Yo analizo tu información y te digo si cumples con nuestro ICP.

*Ejemplo de mensaje:*
"Somos una consultora de marketing digital en Madrid con 15 empleados. Queremos automatizar nuestros procesos con IA"

*Respuesta posible:*
✅ CUALIFICADO - Cumples todos nuestros criterios

*Comandos disponibles:*
/start - Mensaje de bienvenida
/help - Este mensaje
/info - Más sobre Orbyn

¿Necesitas ayuda? Escribe /info para conocer más sobre Orbyn 👇"""
        
        await self.lead_processor.telegram_service.send_message(
            chat_id=user_id,
            message=message
        )
    
    async def _send_info_message(self, user_id: int) -> None:
        """Envía información sobre Orbyn."""
        message = """ℹ️ *Sobre Orbyn*

Orbyn es una plataforma fintech que ayuda a empresas a escalar mediante automatización e inteligencia artificial.

🎯 *Misión*
Conectar empresas de servicios y consultoría con soluciones de IA que les permitan crecer exponencialmente.

💼 *¿A quién buscamos?*
- Empresas de servicios y consultoría
- Mínimo 5 empleados
- Ubicadas en España o Latinoamérica
- Interesadas en automatización e IA

🚀 *¿Qué ofrecemos?*
- Soluciones de automatización
- Integración de IA en procesos
- Consultoría y estrategia digital
- Soporte técnico integral

📧 *Contacto*
Para más información: sales@orbyn.ai
Sitio web: www.orbyn.ai

¿Listo para transformar tu empresa? 🚀"""
        
        await self.lead_processor.telegram_service.send_message(
            chat_id=user_id,
            message=message
        )
    
    def _check_rate_limit(self, user_id: int) -> bool:
        """
        Verifica rate limiting (máximo N requests por minuto).
        
        Args:
            user_id: ID del usuario
        
        Returns:
            True si puede procesar, False si excedió límite
        """
        now = datetime.utcnow()
        one_minute_ago = now - timedelta(minutes=1)
        
        # Limpiar requests viejos
        if user_id in self._user_requests:
            self._user_requests[user_id] = [
                timestamp for timestamp in self._user_requests[user_id]
                if timestamp > one_minute_ago
            ]
        else:
            self._user_requests[user_id] = []
        
        # Verificar límite
        limit = self.lead_processor.settings.rate_limit_per_minute
        
        if len(self._user_requests[user_id]) >= limit:
            return False
        
        # Registrar request
        self._user_requests[user_id].append(now)
        
        return True
    
    def _check_debounce(self, user_id: int) -> bool:
        """
        Evita procesar mensajes duplicados muy seguidos (debounce).
        
        Args:
            user_id: ID del usuario
        
        Returns:
            True si debe procesarse, False si es muy reciente
        """
        now = datetime.utcnow()
        debounce_threshold = timedelta(seconds=2)  # 2 segundos entre mensajes
        
        if user_id in self._user_last_request:
            time_since_last = now - self._user_last_request[user_id]
            
            if time_since_last < debounce_threshold:
                return False
        
        # Registrar timestamp
        self._user_last_request[user_id] = now
        
        return True
