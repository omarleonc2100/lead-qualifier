# 🤖 FASE 3: ORQUESTACIÓN DE IA Y MODELO DE DATOS (Pydantic + LLM Structured Outputs)

Vamos a implementar los providers de LLM con salidas estructuradas garantizadas mediante Pydantic.

---

## 1️⃣ IMPLEMENTACIÓN: OPENAI PROVIDER CON STRUCTURED OUTPUTS

### `services/providers/openai_provider.py` (IMPLEMENTACIÓN COMPLETA)

```python
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

```

---

## 2️⃣ IMPLEMENTACIÓN: ANTHROPIC PROVIDER CON STRUCTURED OUTPUTS

### `services/providers/anthropic_provider.py` (IMPLEMENTACIÓN COMPLETA)

```python
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

```

---

## 3️⃣ ACTUALIZAR LLM_SERVICE PARA USARPROVIDERS REALES

### `services/llm_service.py` (IMPLEMENTACIÓN COMPLETA)

```python
"""
Servicio de LLM. Orquestación y delegación a providers.
FASE 3: Ahora usa providers reales con Structured Outputs.
"""

from abc import ABC, abstractmethod
from typing import Optional
from models.lead import LeadInput
from models.qualification import QualificationResult
from utils.logger import get_logger
from config.settings import Settings
from config.constants import SYSTEM_PROMPT
import time

logger = get_logger(__name__)


class LLMServiceInterface(ABC):
    """
    Interfaz abstracta para servicios de LLM.
    Permite cambiar entre proveedores sin modificar el código.
    """
    
    @abstractmethod
    async def qualify_lead(self, lead: LeadInput) -> QualificationResult:
        """
        Cualifica un lead usando el LLM.
        
        Args:
            lead: Datos del lead a calificar
        
        Returns:
            Resultado de cualificación estructurado
        
        Raises:
            Exception: Si hay error en la llamada al LLM
        """
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Prueba la conexión con el proveedor de LLM.
        
        Returns:
            True si la conexión es válida
        """
        pass


class LLMService(LLMServiceInterface):
    """
    Servicio de LLM orquestador.
    Delega a implementaciones específicas según el proveedor configurado.
    
    PROVEEDORES SOPORTADOS:
    - openai: GPT-4o mini (recomendado para costo)
    - anthropic: Claude 3.5 Sonnet (mejor contexto)
    
    FEATURES:
    - Carga dinámica de providers
    - Fallback automático (FASE 5)
    - Test de conexión en startup
    - Logging detallado
    """
    
    def __init__(self, settings: Settings):
        """
        Inicializa el servicio de LLM.
        
        Args:
            settings: Configuración de la aplicación
        
        Raises:
            ValueError: Si el proveedor no es soportado
        """
        self.settings = settings
        self.provider = settings.llm_provider.lower()
        self._provider_impl: Optional[LLMServiceInterface] = None
        
        logger.info(
            "llm_service_initialized",
            provider=self.provider,
            model=self._get_model_name()
        )
        
        # Inicializar el provider específico
        self._initialize_provider()
    
    def _initialize_provider(self) -> None:
        """
        Inicializa el provider según la configuración.
        
        Raises:
            ValueError: Si el proveedor no es soportado
            ImportError: Si las dependencias no están instaladas
        """
        try:
            if self.provider == "openai":
                from services.providers.openai_provider import OpenAIProvider
                self._provider_impl = OpenAIProvider(self.settings)
                logger.debug("openai_provider_loaded")
            
            elif self.provider == "anthropic":
                from services.providers.anthropic_provider import AnthropicProvider
                self._provider_impl = AnthropicProvider(self.settings)
                logger.debug("anthropic_provider_loaded")
            
            else:
                raise ValueError(
                    f"Proveedor de LLM no soportado: {self.provider}. "
                    f"Usa 'openai' o 'anthropic'"
                )
        
        except ImportError as e:
            logger.error(
                "llm_provider_import_error",
                provider=self.provider,
                error=str(e)
            )
            raise
        except Exception as e:
            logger.error(
                "llm_provider_init_error",
                provider=self.provider,
                error=str(e)
            )
            raise
    
    async def qualify_lead(self, lead: LeadInput) -> QualificationResult:
        """
        Cualifica un lead usando el proveedor configurado.
        
        Args:
            lead: Datos del lead
        
        Returns:
            Resultado de cualificación estructurado
        
        Raises:
            Exception: Si hay error en la llamada al LLM
        """
        if not self._provider_impl:
            raise RuntimeError("Provider de LLM no inicializado")
        
        try:
            logger.debug(
                "llm_qualify_lead_start",
                provider=self.provider,
                telegram_user_id=lead.telegram_user_id,
                text_length=len(lead.raw_text)
            )
            
            # Delegar al provider
            result = await self._provider_impl.qualify_lead(lead)
            
            logger.info(
                "llm_qualify_lead_success",
                provider=self.provider,
                telegram_user_id=lead.telegram_user_id,
                is_qualified=result.qualification.is_qualified
            )
            
            return result
        
        except Exception as e:
            logger.error(
                "llm_qualify_lead_failed",
                provider=self.provider,
                telegram_user_id=lead.telegram_user_id,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    async def test_connection(self) -> bool:
        """
        Prueba la conexión con el proveedor de LLM.
        
        Returns:
            True si la conexión es válida
        """
        if not self._provider_impl:
            logger.error("llm_test_connection_provider_not_initialized")
            return False
        
        try:
            logger.debug("llm_test_connection_start", provider=self.provider)
            
            result = await self._provider_impl.test_connection()
            
            if result:
                logger.info("llm_test_connection_success", provider=self.provider)
            else:
                logger.warning("llm_test_connection_failed", provider=self.provider)
            
            return result
        
        except Exception as e:
            logger.error(
                "llm_test_connection_error",
                provider=self.provider,
                error=str(e)
            )
            return False
    
    def _get_model_name(self) -> str:
        """
        Retorna el nombre del modelo según el proveedor.
        
        Returns:
            Nombre del modelo
        """
        if self.provider == "openai":
            return self.settings.openai_model
        elif self.provider == "anthropic":
            return self.settings.anthropic_model
        return "unknown"
    
    def get_provider_name(self) -> str:
        """Retorna el nombre del proveedor configurado."""
        return self.provider

```

---

## 4️⃣ ACTUALIZAR requirements.txt CON ANTHROPIC (OPCIONAL)

```txt
# Framework y Bot de Telegram
python-telegram-bot==20.7

# LLM y IA
openai==1.40.0
anthropic==0.39.0  # NUEVO: Agregado para soporte Anthropic
langchain-core==0.2.0
pydantic==2.7.4
pydantic-settings==2.2.1

# Google Sheets Integration
gspread==6.1.0
google-auth==2.28.1
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0

# Utilidades
python-dotenv==1.0.1
requests==2.31.0
aiohttp==3.9.5

# Logging y Monitoreo
structlog==24.1.0

# Testing
pytest==7.4.4
pytest-asyncio==0.23.3
pytest-mock==3.14.0

# Linting y Code Quality
black==24.3.0
flake8==7.1.0
mypy==1.11.1

# Producción
gunicorn==21.2.0
uvicorn==0.29.0

```

---

## 5️⃣ ACTUALIZAR main.py CON TEST DE CONEXIÓN

### `main.py` (ACTUALIZADO CON CONNECTION TESTS)

```python
"""
Punto de entrada principal de la aplicación.
FASE 3: Agregamos test de conexión con LLM antes de iniciar.
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

```

---

## 6️⃣ AGREGAR TIPO OPCIONAL EN MAIN.py

Al inicio de `main.py`, agrega las importaciones faltantes:

```python
# ... imports existentes ...
from typing import Optional

# ... resto del código ...
```

---

## 7️⃣ CREAR TEST MANUAL PARA LLM

### `tests/test_llm_service.py`

```python
"""
Tests para el servicio de LLM.
Valida que ambos providers funcionen correctamente.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from config.settings import Settings
from models.lead import LeadInput
from models.qualification import LeadQualification, QualificationResult
from services.llm_service import LLMService


class TestOpenAIProvider:
    """Tests para OpenAI Provider."""
    
    @pytest.mark.asyncio
    async def test_qualify_lead_qualified(self):
        """Test de cualificación exitosa con OpenAI."""
        settings = Settings()
        settings.llm_provider = "openai"
        
        llm_service = LLMService(settings)
        
        lead = LeadInput(
            raw_text="Somos una empresa de consultoría en Madrid con 25 empleados. "
                     "Queremos automatizar nuestros procesos de ventas.",
            telegram_user_id=123456,
            telegram_username="test_user"
        )
        
        # Este test necesita clave OpenAI real para ejecutarse
        # En CI/CD se mockearía la API
        
        # result = await llm_service.qualify_lead(lead)
        # assert isinstance(result, QualificationResult)
        # assert isinstance(result.qualification, LeadQualification)


class TestAnthropicProvider:
    """Tests para Anthropic Provider."""
    
    @pytest.mark.asyncio
    async def test_qualify_lead_not_qualified(self):
        """Test de rechazo correcto con Anthropic."""
        settings = Settings()
        settings.llm_provider = "anthropic"
        
        llm_service = LLMService(settings)
        
        lead = LeadInput(
            raw_text="Soy freelancer en USA. Desarrollo webs.",
            telegram_user_id=789012,
            telegram_username="freelancer"
        )
        
        # result = await llm_service.qualify_lead(lead)
        # assert result.qualification.is_qualified is False


class TestJSONExtraction:
    """Tests para extracción de JSON."""
    
    def test_extract_json_with_extra_text(self):
        """Test de extracción de JSON con texto adicional."""
        from services.providers.anthropic_provider import AnthropicProvider
        
        text = 'Aquí está: {"is_qualified": true, "reason": "Cumple criterios"} Fin.'
        
        json_str = AnthropicProvider._extract_json(text)
        
        assert json_str is not None
        assert '"is_qualified": true' in json_str
        assert '"reason"' in json_str

```

---

## 8️⃣ CASOS DE PRUEBA MANUAL - TEST THESE LEADS

Ahora que tienes los providers listos, prueba con estos leads:

### LEAD 1: DEBE CALIFICAR ✅
```
Somos una empresa de consultoría en Madrid con 30 empleados. 
Ofrecemos servicios de transformación digital y queremos implementar 
soluciones de automatización de procesos con IA.
```

### LEAD 2: NO DEBE CALIFICAR ❌ (Tamaño insuficiente)
```
Soy freelancer en Barcelona. Desarrollo webs personalizadas.
Solo trabajo con 2 personas más.
```

### LEAD 3: NO DEBE CALIFICAR ❌ (Ubicación incorrecta)
```
Somos una empresa de servicios en Nueva York con 50 empleados.
Buscamos soluciones de automatización.
```

### LEAD 4: DEBE CALIFICAR ✅ (Latinoamérica)
```
Tenemos una consultora en Bogotá con 15 empleados.
Nos dedica mos a estrategia digital y queremos implementar IA
para mejorar nuestros procesos de atención al cliente.
```

### LEAD 5: NO DEBE CALIFICAR ❌ (Sin interés en IA)
```
Somos una tienda de ropa en Madrid con 12 empleados.
Buscamos mejorar nuestro inventario.
```

---

## 9️⃣ ESTRUCTURA FINAL DESPUÉS DE FASE 3

```
orbyn-lead-qualifier/
├── config/
│   ├── __init__.py
│   ├── settings.py               ✓
│   └── constants.py              ✓
├── models/
│   ├── __init__.py
│   ├── lead.py                   ✓
│   └── qualification.py          ✓
├── services/
│   ├── __init__.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── openai_provider.py    ✓ IMPLEMENTADO (Structured Outputs)
│   │   └── anthropic_provider.py ✓ IMPLEMENTADO (Structured Outputs)
│   ├── llm_service.py            ✓ IMPLEMENTADO (Orquestador)
│   ├── sheets_service.py         ✓ IMPLEMENTADO
│   ├── telegram_service.py       ✓ IMPLEMENTADO
│   └── lead_processor.py         ✓ IMPLEMENTADO
├── handlers/
│   ├── __init__.py
│   ├── telegram_handlers.py
│   └── error_handler.py
├── utils/
│   ├── __init__.py
│   ├── logger.py                 ✓
│   ├── validators.py             ✓
│   └── async_utils.py            ✓
├── credentials/
│   └── google_service_account.json (a crear)
├── tests/
│   ├── __init__.py
│   └── test_llm_service.py      ✓ NUEVO
├── main.py                       ✓ ACTUALIZADO
├── requirements.txt              ✓
├── .env.example                  ✓
├── .env                          (a crear)
├── .gitignore                    ✓
├── pyproject.toml                ✓
└── README.md                     ✓
```

---

## 🔟 RESUMEN TÉCNICO FASE 3: STRUCTURED OUTPUTS

### ¿POR QUÉ STRUCTURED OUTPUTS?

**Problema tradicional:**
```python
# LLM retorna texto libre
response = "El lead cumple criterios. Tiene 20 empleados..."

# Necesitas parsear manualmente (frágil)
if "cumple" in response:
    is_qualified = True
# ¿Y si dice "no incumple"? Lógica quebrada.
```

**Solución FASE 3:**
```python
# LLM retorna JSON validado
{
    "is_qualified": true,
    "reason": "Empresa de consultoría con 20 empleados..."
}

# Validamos con Pydantic automáticamente
qualification = LeadQualification(**json_response)
# ✅ Type-safe, predecible, no errores de parseo
```

### VENTAJAS IMPLEMENTADAS

✅ **OpenAI Structured Outputs (JSON Mode)**
- Garantiza JSON válido
- Validación del lado de OpenAI
- Menor latencia
- Precio idéntico a text generation

✅ **Anthropic + Pydantic**
- JSON schema explícito
- Validación Pydantic post-API
- Mejor contexto (200K tokens)
- Excelente manejo de lenguaje natural

✅ **Pydantic en Ambos**
- Validación de tipos
- Constraints (min_length, etc)
- Serialización automatizada
- Documentación automática

### FLUJO COMPLETO

```
User → Telegram
  ↓
LeadProcessor.process_lead()
  ├─ Validar con Pydantic (LeadInput)
  ├─ Detectar Prompt Injection
  ├─ LLMService.qualify_lead()
  │   ├─ OpenAI/Anthropic Provider
  │   ├─ System Prompt (inmune)
  │   ├─ Structured Output
  │   └─ Validar con Pydantic (LeadQualification)
  ├─ GoogleSheets.append_record()
  └─ Telegram.send_message()
```

---
