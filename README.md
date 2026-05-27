# 🤖 Orbyn Lead Qualifier Bot

**Agente de cualificación de leads conectado a Telegram para Orbyn Fintech**

Un bot inteligente que evalúa leads en tiempo real contra un ICP predefinido, con persistencia en Google Sheets y respuestas automáticas en Telegram.

---

## 📋 Tabla de Contenidos

- [Características](#características)
- [Arquitectura](#arquitectura)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Uso](#uso)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Roadmap](#roadmap)

---

## ✨ Características

✅ **Cualificación en tiempo real**: Analiza leads con LLM (OpenAI/Claude)
✅ **ICP Robusto**: Valida 4 criterios principales (tipo, tamaño, ubicación, interés)
✅ **Telegram Integration**: Respuestas directas en el chat
✅ **Google Sheets Logging**: Persistencia automatizada de resultados
✅ **Arquitectura Modular**: Fácil de testear y escalar
✅ **Manejo de Errores**: Retry logic con backoff exponencial
✅ **Defensa contra Prompt Injection**: Validaciones básicas
✅ **Logging Estructurado**: Monitoreo completo con structlog

---

## 🏗️ Arquitectura

```
Telegram User
    ↓
Telegram Bot (Handler)
    ↓
LeadProcessor (Orquestador)
    ├─→ Validate Input (Pydantic)
    ├─→ Detect Injection (Validator)
    ├─→ LLM Service (OpenAI/Claude)
    ├─→ Google Sheets Service (Persistencia)
    └─→ Telegram Service (Respuesta)
```

### Módulos Principales

- **config/**: Configuración centralizada (Settings, Constantes)
- **models/**: Modelos de datos (Pydantic)
- **services/**: Lógica de negocio (LLM, Sheets, Telegram, Processor)
- **handlers/**: Manejadores de eventos
- **utils/**: Utilidades (Logger, Validators, Async utils)
- **tests/**: Suite de pruebas

---

## 🚀 Instalación

### Requisitos

- Python 3.10+
- pip
- Cuenta de Telegram Bot (BotFather)
- Credenciales de Google Cloud (service account)
- API key de OpenAI o Anthropic

### Pasos

```bash
# 1. Clonar repositorio
git clone <repo-url>
cd orbyn-lead-qualifier

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# 5. Colocar credenciales de Google
# Guardar google_service_account.json en credentials/

# 6. Ejecutar
python main.py
```

---

## ⚙️ Configuración

### Variables de Entorno Requeridas

```bash
TELEGRAM_BOT_TOKEN=          # Token del bot (BotFather)
OPENAI_API_KEY=             # API key de OpenAI
GOOGLE_SHEET_ID=            # ID de la Google Sheet destino
GOOGLE_SHEETS_CREDENTIALS_PATH=  # Ruta a credenciales de Google
```

### ICP Predefinido

- **Tipo**: Servicios, Consultoría, Tecnología
- **Tamaño**: Mínimo 5 empleados
- **Ubicación**: España, Colombia, Mexico, Argentina, Chile, Peru, Ecuador
- **Interés**: Automatización, IA, Transformación Digital

---

## 📊 Estructura del Proyecto

```
orbyn-lead-qualifier/
├── config/
│   ├── settings.py         # Configuración Pydantic
│   └── constants.py        # ICP, templates, patterns
├── models/
│   ├── lead.py            # LeadInput, LeadMetadata
│   └── qualification.py    # LeadQualification, QualificationResult
├── services/
│   ├── llm_service.py     # LLM Service interface
│   ├── sheets_service.py  # Google Sheets interface
│   ├── telegram_service.py # Telegram Bot interface
│   └── lead_processor.py  # Orquestador principal
├── handlers/
│   ├── telegram_handlers.py
│   └── error_handler.py
├── utils/
│   ├── logger.py
│   ├── validators.py
│   └── async_utils.py
├── tests/
│   └── (test files)
├── main.py                # Punto de entrada
└── requirements.txt
```

---

## 🧪 Testing

```bash
# Ejecutar tests
pytest tests/

# Con coverage
pytest --cov=. tests/

# Tests específicos
pytest tests/test_models.py -v
```

---

## 📅 Roadmap

- [x] FASE 1: Arquitectura y configuración base
- [ ] FASE 2: Google Sheets + Telegram Integration
- [ ] FASE 3: LLM Structured Outputs (Pydantic)
- [ ] FASE 4: Flujo completo y procesamiento asincrónico
- [ ] FASE 5: Testing, error handling y producción

---

## 📝 Notas Técnicas

### Defensa contra Prompt Injection

FASE 1 incluye:
- Validación de patrones conocidos
- Sanitización de inputs
- System prompt inmune a injections (separación clara de instrucciones)

En FASE 5 mejoraremos:
- Detección más sofisticada
- Rate limiting por usuario
- Validación de contexto

### Optimización de Costes

- Uso de `gpt-4o-mini` (más barato que GPT-4)
- Prompt structure optimizado
- Caching de respuestas (FASE 5)

---

## 📞 Contacto

Orbyn Fintech - sales@orbyn.ai