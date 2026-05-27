"""
Provider de Anthropic Claude con Structured Outputs.
Utiliza API de Anthropic para garantizar respuestas en formato JSON.

FEATURES:
- Salidas estructuradas con JSON schemas
- Retry automático
- Validación con Pydantic
- Excelente relación costo/rendimiento
- Manejo robusto de errores
"""

import json
import asyncio
from typing import Optional, Any
from datetime import datetime

try:
    from anthropic import Anthropic, AsyncAnthropic, APIError, RateLimitError, APIConnectionError
except ImportError:
    # Para desarrollo sin Anthropic instalado
    Anthropic = None
    AsyncAnthropic = None
    APIError = Exception
    RateLimitError = Exception
    APIConnectionError = Exception

from pydantic import BaseModel, ValidationError

from models.lead import LeadInput
from models.qualification import LeadQualification, QualificationResult
from utils.logger import get_logger
from config.settings import Settings
from config.constants import SYSTEM_PROMPT
from utils.async_utils import async_retry

logger = get_logger(__name__)


class AnthropicProvider:
    """
    Provider para Anthropic Claude models con Structured Outputs.
    
    ARQUITECTURA:
    1. Recibe LeadInput del procesador
    2. Construye prompt con system + user message
    3. Llama Anthropic API con tool_use para JSON estructurado
    4. Valida respuesta con Pydantic
    5. Retorna QualificationResult tipado
    
    VENTAJAS:
    - Mejor contexto que GPT (200K tokens en Claude 3)
    - Menos costoso que GPT-4
    - Excelente comprensión de lenguaje natural
    - Buena defensa contra prompt injection
    """
    
    def __init__(self, settings: Settings):
        """
        Inicializa el provider de Anthropic.
        
        Args:
            settings: Configuración de la aplicación
        
        Raises:
            ValueError: Si la API key no está configurada
            ImportError: Si Anthropic SDK no está instalado
        """
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY no está configurada")
        
        if AsyncAnthropic is None:
            raise ImportError(
                "Anthropic SDK no está instalado. Instala con: pip install anthropic"
            )
        
        self.settings = settings
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        
        logger.info(
            "anthropic_provider_initialized",
            model=settings.anthropic_model,
            provider="anthropic"
        )
    
    @async_retry(max_attempts=3, initial_delay=2.0, backoff_factor=2.0, max_delay=30.0)
    async def qualify_lead(self, lead: LeadInput) -> QualificationResult:
        """
        Cualifica un lead usando Anthropic Claude con Structured Outputs.
        
        PROCESO:
        1. Construir el prompt
        2. Llamar API Anthropic con JSON schema
        3. Extraer JSON de la respuesta
        4. Validar con Pydantic
        5. Retornar resultado tipado
        
        Args:
            lead: Datos del lead a calificar
        
        Returns:
            QualificationResult con decisión tipada
        
        Raises:
            APIError: Si hay error en la API de Anthropic
            ValidationError: Si la respuesta no cumple schema
        """
        try:
            start_time = datetime.utcnow()
            
            logger.debug(
                "anthropic_qualify_lead_start",
                telegram_user_id=lead.telegram_user_id,
                text_length=len(lead.raw_text)
            )
            
            # ============ PASO 1: CONSTRUIR PROMPT ============
            user_message = self._build_user_message(lead)
            
            # ============ PASO 2: LLAMAR ANTHROPIC ============
            logger.debug(
                "anthropic_api_call",
                model=self.settings.anthropic_model,
                temperature=0
            )
            
            # Construir instrucciones para JSON estructurado
            system_instructions = self._build_system_prompt()
            
            response = await self.client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=1024,  # Respuesta pequeña y estructurada
                system=system_instructions,
                messages=[
                    {"role": "user", "content": user_message}
                ],
                timeout=self.settings.api_timeout,
            )
            
            logger.debug(
                "anthropic_api_response_received",
                telegram_user_id=lead.telegram_user_id,
                usage_input_tokens=response.usage.input_tokens if response.usage else None,
                usage_output_tokens=response.usage.output_tokens if response.usage else None
            )
            
            # ============ PASO 3: EXTRAER Y PARSEAR JSON ============
            response_text = response.content[0].text if response.content else ""
            
            # Intentar extraer JSON de la respuesta
            json_str = self._extract_json(response_text)
            
            if not json_str:
                raise ValueError(
                    f"No se pudo extraer JSON válido de la respuesta: {response_text[:100]}"
                )
            
            # Parsear JSON
            response_dict = json.loads(json_str)
            
            # ============ PASO 4: VALIDAR CON PYDANTIC ============
            qualification = LeadQualification(**response_dict)
            
            # ============ PASO 5: CONSTRUIR RESULTADO ============
            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            result = QualificationResult(
                lead_id=f"lead_{lead.telegram_user_id}_{int(start_time.timestamp())}",
                qualification=qualification,
                metadata={
                    "model": self.settings.anthropic_model,
                    "provider": "anthropic",
                    "tokens_input": response.usage.input_tokens if response.usage else None,
                    "tokens_output": response.usage.output_tokens if response.usage else None,
                    "processing_time_ms": elapsed_ms,
                },
                model_used=self.settings.anthropic_model,
            )
            
            logger.info(
                "anthropic_qualify_lead_success",
                telegram_user_id=lead.telegram_user_id,
                is_qualified=result.qualification.is_qualified,
                processing_time_ms=f"{elapsed_ms:.2f}"
            )
            
            return result
        
        except RateLimitError as e:
            logger.warning(
                "anthropic_rate_limit_error",
                telegram_user_id=lead.telegram_user_id,
                error=str(e)
            )
            raise
        
        except APIConnectionError as e:
            logger.warning(
                "anthropic_connection_error",
                telegram_user_id=lead.telegram_user_id,
                error=str(e)
            )
            raise
        
        except APIError as e:
            logger.error(
                "anthropic_api_error",
                telegram_user_id=lead.telegram_user_id,
                error=str(e)
            )
            raise
        
        except json.JSONDecodeError as e:
            logger.error(
                "anthropic_json_parse_error",
                telegram_user_id=lead.telegram_user_id,
                error=str(e)
            )
            raise ValueError(f"Respuesta de Anthropic no contiene JSON válido: {e}")
        
        except ValidationError as e:
            logger.error(
                "anthropic_validation_error",
                telegram_user_id=lead.telegram_user_id,
                error=str(e),
                errors=e.errors()
            )
            raise ValueError(f"Respuesta no cumple schema esperado: {e}")
        
        except Exception as e:
            logger.error(
                "anthropic_qualify_lead_error",
                telegram_user_id=lead.telegram_user_id,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    def _build_system_prompt(self) -> str:
        """
        Construye el system prompt para Anthropic.
        
        Returns:
            System prompt optimizado para Anthropic
        """
        return f"""{SYSTEM_PROMPT}

IMPORTANTE PARA CLAUDE:
- Debes responder SIEMPRE con un JSON válido
- No incluyas explicaciones fuera del JSON
- El JSON debe tener exactamente estos campos:
  {{"is_qualified": true/false, "reason": "texto"}}
- El JSON debe ser válido y parseble
"""
    
    def _build_user_message(self, lead: LeadInput) -> str:
        """
        Construye el mensaje de usuario.
        
        Args:
            lead: Datos del lead
        
        Returns:
            Mensaje formateado
        """
        message = f"""
INFORMACIÓN DEL LEAD (texto libre):
{lead.raw_text}

---

Evalúa si este lead cumple con TODOS estos criterios:

1. ¿Es una empresa de servicios, consultoría o tecnología?
2. ¿Tiene mínimo 5 empleados?
3. ¿Está ubicada en España o Latinoamérica?
4. ¿Muestra interés en automatización o IA?

Responde SOLO en JSON sin otras explicaciones.
"""
        return message.strip()
    
    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """
        Extrae JSON de un texto que puede contener otros caracteres.
        
        Busca el primer {{ y el último }} para extraer JSON válido.
        
        Args:
            text: Texto que contiene JSON
        
        Returns:
            String JSON extraído, o None si no hay
        """
        if not text:
            return None
        
        # Buscar inicio de JSON
        start_idx = text.find('{')
        if start_idx == -1:
            return None
        
        # Buscar final de JSON
        end_idx = text.rfind('}')
        if end_idx == -1 or end_idx <= start_idx:
            return None
        
        return text[start_idx:end_idx + 1]
    
    async def test_connection(self) -> bool:
        """
        Prueba que la conexión con Anthropic funcione.
        
        Returns:
            True si la conexión es válida
        """
        try:
            logger.debug("anthropic_testing_connection")
            
            # Hacer un call mínimo para verificar autenticación
            response = await self.client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=10,
                messages=[
                    {"role": "user", "content": "Hi"}
                ]
            )
            
            logger.info("anthropic_connection_test_success")
            return True
        
        except Exception as e:
            logger.error("anthropic_connection_test_failed", error=str(e))
            return False
