"""
Provider de OpenAI con Structured Outputs.
Utiliza JSON mode de OpenAI para garantizar respuestas consistentes.

FEATURES:
- Salidas estructuradas garantizadas con JSON Schema
- Retry automático en case de errores
- Validación con Pydantic
- Optimización de costes con gpt-4o-mini
- Manejo robusto de timeouts
"""

import json
import asyncio
from typing import Optional, Type
from openai import OpenAI, AsyncOpenAI, APIError, RateLimitError, APIConnectionError
from pydantic import BaseModel, ValidationError
from datetime import datetime

from models.lead import LeadInput
from models.qualification import LeadQualification, QualificationResult
from utils.logger import get_logger
from config.settings import Settings
from config.constants import SYSTEM_PROMPT
from utils.async_utils import async_retry

logger = get_logger(__name__)


class OpenAIProvider:
    """
    Provider para OpenAI GPT models con Structured Outputs.
    
    ARQUITECTURA:
    1. Recibe LeadInput del procesador
    2. Construye prompt con system + user message
    3. Llama OpenAI con JSON schema de Pydantic
    4. Valida respuesta con Pydantic
    5. Retorna QualificationResult tipado
    
    VENTAJAS DE STRUCTURED OUTPUTS:
    - Respuestas siempre en formato JSON válido
    - No hay parseo manual frágil
    - Validación automática del lado de OpenAI
    - Menor latencia que text generation + parseo
    """
    
    def __init__(self, settings: Settings):
        """
        Inicializa el provider de OpenAI.
        
        Args:
            settings: Configuración de la aplicación
        
        Raises:
            ValueError: Si la API key no está configurada
        """
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY no está configurada")
        
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        
        logger.info(
            "openai_provider_initialized",
            model=settings.openai_model,
            provider="openai"
        )
    
    @async_retry(max_attempts=3, initial_delay=2.0, backoff_factor=2.0, max_delay=30.0)
    async def qualify_lead(self, lead: LeadInput) -> QualificationResult:
        """
        Cualifica un lead usando OpenAI con Structured Outputs.
        
        PROCESO:
        1. Construir el prompt
        2. Llamar API OpenAI con JSON schema
        3. Parsear respuesta JSON
        4. Validar con Pydantic
        5. Retornar resultado tipado
        
        Args:
            lead: Datos del lead a calificar
        
        Returns:
            QualificationResult con decisión tipada
        
        Raises:
            APIError: Si hay error en la API de OpenAI
            ValidationError: Si la respuesta no cumple schema
        """
        try:
            start_time = datetime.utcnow()
            
            logger.debug(
                "openai_qualify_lead_start",
                telegram_user_id=lead.telegram_user_id,
                text_length=len(lead.raw_text)
            )
            
            # ============ PASO 1: CONSTRUIR PROMPT ============
            user_message = self._build_user_message(lead)
            
            # ============ PASO 2: LLAMAR OPENAI CON JSON SCHEMA ============
            logger.debug(
                "openai_api_call",
                model=self.settings.openai_model,
                temperature=0
            )
            
            response = await self.client.beta.chat.completions.parse(
                model=self.settings.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                response_format=LeadQualification,  # Pydantic model como schema
                temperature=0,  # Determinístico
                timeout=self.settings.api_timeout,
            )
            
            logger.debug(
                "openai_api_response_received",
                telegram_user_id=lead.telegram_user_id,
                usage_input_tokens=response.usage.prompt_tokens if response.usage else None,
                usage_output_tokens=response.usage.completion_tokens if response.usage else None
            )
            
            # ============ PASO 3: EXTRAER Y VALIDAR RESPUESTA ============
            # Con Structured Outputs, la respuesta ya está validada
            qualification = response.choices[0].message.parsed
            
            if not qualification:
                raise ValueError("OpenAI no retornó una respuesta parseada")
            
            # ============ PASO 4: CONSTRUIR RESULTADO ============
            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            result = QualificationResult(
                lead_id=f"lead_{lead.telegram_user_id}_{int(start_time.timestamp())}",
                qualification=qualification,
                metadata={
                    "model": self.settings.openai_model,
                    "provider": "openai",
                    "tokens_input": response.usage.prompt_tokens if response.usage else None,
                    "tokens_output": response.usage.completion_tokens if response.usage else None,
                    "processing_time_ms": elapsed_ms,
                },
                model_used=self.settings.openai_model,
            )
            
            logger.info(
                "openai_qualify_lead_success",
                telegram_user_id=lead.telegram_user_id,
                is_qualified=result.qualification.is_qualified,
                processing_time_ms=f"{elapsed_ms:.2f}"
            )
            
            return result
        
        except RateLimitError as e:
            # Rate limit: el retry lo intentará de nuevo
            logger.warning(
                "openai_rate_limit_error",
                telegram_user_id=lead.telegram_user_id,
                error=str(e)
            )
            raise
        
        except APIConnectionError as e:
            # Error de conexión: recuperable
            logger.warning(
                "openai_connection_error",
                telegram_user_id=lead.telegram_user_id,
                error=str(e)
            )
            raise
        
        except APIError as e:
            # Error de API general
            logger.error(
                "openai_api_error",
                telegram_user_id=lead.telegram_user_id,
                error=str(e),
                status_code=e.status_code if hasattr(e, 'status_code') else None
            )
            raise
        
        except ValidationError as e:
            # Error de validación Pydantic
            logger.error(
                "openai_validation_error",
                telegram_user_id=lead.telegram_user_id,
                error=str(e),
                errors=e.errors()
            )
            raise ValueError(f"Respuesta de OpenAI no cumple schema: {e}")
        
        except Exception as e:
            logger.error(
                "openai_qualify_lead_error",
                telegram_user_id=lead.telegram_user_id,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    def _build_user_message(self, lead: LeadInput) -> str:
        """
        Construye el mensaje de usuario para el LLM.
        
        ESTRUCTURA:
        - Contexto: qué es lo que hacemos
        - Lead data: los datos del lead
        - Task: qué queremos que haga
        
        Args:
            lead: Datos del lead
        
        Returns:
            String formateado como prompt
        """
        message = f"""
INFORMACIÓN DEL LEAD (texto libre):
{lead.raw_text}

---

Basándote ÚNICAMENTE en la información anterior, evalúa si este lead cumple con TODOS estos criterios:

1. ¿Es una empresa de servicios, consultoría o tecnología?
2. ¿Tiene mínimo 5 empleados?
3. ¿Está ubicada en España o Latinoamérica (Colombia, Mexico, Argentina, Chile, Peru, Ecuador)?
4. ¿Muestra interés en automatización, inteligencia artificial o transformación digital?

Responde SIEMPRE en JSON con la estructura exacta requerida.
"""
        return message.strip()
    
    async def test_connection(self) -> bool:
        """
        Prueba que la conexión con OpenAI funcione.
        Útil para validación en startup.
        
        Returns:
            True si la conexión es válida
        """
        try:
            logger.debug("openai_testing_connection")
            
            # Hacer un call mínimo para verificar autenticación
            response = await self.client.models.list()
            
            logger.info("openai_connection_test_success")
            return True
        
        except Exception as e:
            logger.error("openai_connection_test_failed", error=str(e))
            return False
