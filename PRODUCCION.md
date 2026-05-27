# 📋 GUÍA DE PRODUCCIÓN - ORBYN LEAD QUALIFIER

## Despliegue en Producción

Este documento cubre la migración de desarrollo a producción.

---

## 🚀 ANTES DE PRODUCCIÓN: CHECKLIST

- [ ] Todas las variables de entorno configuradas
- [ ] Google Sheets verificado y permisos correctos
- [ ] Telegram Bot token válido y bot públicamente disponible
- [ ] LLM API keys válidas y con cuota disponible
- [ ] Tests pasados (pytest tests/ --cov)
- [ ] Logging configurado para envío a servidor centralizado
- [ ] Monitoreo de alerts configurado
- [ ] Backups automáticos de Google Sheets habilitados

---

## 🔑 VARIABLES DE ENTORNO PRODUCCIÓN

```bash
# AMBIENTE
ENV=production
LOG_LEVEL=INFO  # No DEBUG en producción

# LLM (producción recomienda Anthropic por costo)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxx...
OPENAI_API_KEY=sk-xxxx...  # Fallback

# Telegram
TELEGRAM_BOT_TOKEN=xxxxx:yyyyy-zzzz

# Google Sheets
GOOGLE_SHEET_ID=xxxxx
GOOGLE_SHEETS_CREDENTIALS_PATH=/etc/secrets/google_sa.json

# Rate Limiting (producción más conservador)
RATE_LIMIT_PER_MINUTE=5  # Reducir de 10 a 5

# API Timeouts
API_TIMEOUT=30

# Injection Check (siempre habilitado)
ENABLE_PROMPT_INJECTION_CHECK=true
```

---

## 🐳 DEPLOYMENT CON DOCKER

### Dockerfile

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .

# Instalar Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import asyncio; from services.llm_service import LLMService; from config.settings import Settings; print('OK')"

# Ejecutar
CMD ["python", "main.py"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  lead-qualifier:
    build: .
    container_name: orbyn-lead-qualifier
    restart: always
    env_file: .env.prod
    volumes:
      - /etc/secrets:/etc/secrets:ro  # Google credentials read-only
      - ./logs:/app/logs  # Logs persistentes
    networks:
      - orbyn-network
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "3"

networks:
  orbyn-network:
    driver: bridge
```

---

## 📊 MONITOREO EN PRODUCCIÓN

### Métricas a Monitorear

```python
# En el logger, buscar:
- "lead_processor_high_latency": Latencia > 5s
- "circuit_breaker_opened": API externa está caída
- "llm_qualify_lead_primary_failed": Provider principal falló
- "prompt_injection_detected": Intento de injection
- "rate_limit_exceeded": Usuario excedió límite
```

### Alertas Recomendadas

```
1. Si circuit_breaker está OPEN > 5 minutos → enviar alert
2. Si latencia promedio > 3s → investigar
3. Si injection attempts > 10 por hora → analizar
4. Si ambos LLM providers fallan → pager duty
```

### Logs Centralizados

Recomendamos enviar logs a Datadog, New Relic o CloudWatch:

```python
# En utils/logger.py, agregaria Sentry
import sentry_sdk

sentry_sdk.init(
    dsn="https://xxxxx@sentry.io/project-id",
    traces_sample_rate=0.1,  # 10% de requests
    environment="production"
)
```

---

## 💰 OPTIMIZACIÓN DE COSTES

### Estrategia Recomendada

**Usar Anthropic como principal, OpenAI como fallback:**

```
Anthropic Claude 3.5 Sonnet:
- Input: $3 / 1M tokens
- Output: $15 / 1M tokens
- Mejor costo que GPT-4

Estimado por lead:
- Input: ~500 tokens (~$0.0015)
- Output: ~100 tokens (~$0.0015)
- Total: ~$0.003 por lead
- 10,000 leads/mes: $30
```

### Caché de Respuestas (FASE 6)

Para versiones futuras:

```python
# Cachear system prompt en Redis
# Si el mismo texto se evalúa 2x, usar caché
# Ahorro: ~90% en costes si hay duplicados
```

---

## 🛡️ SEGURIDAD EN PRODUCCIÓN

### Defensa contra Prompt Injection

**IMPLEMENTADO en FASE 4-5:**
1. Validación de patrones conocidos ✅
2. System prompt separado e inmune ✅
3. Salidas estructuradas (Pydantic) ✅
4. Rate limiting por usuario ✅

**PARA MEJORAR (FASE 6):**
- Detección de anomalías en prompts (palabra rarity scores)
- Sandboxing del LLM (JSON mode prevents instruction exec)
- Audit trail de todos los prompts

### Manejo de Secrets

```bash
# NUNCA en .env en producción
# Usar:
# - AWS Secrets Manager
# - HashiCorp Vault
# - Kubernetes Secrets
# - Google Secret Manager

# Ejemplo con Google Secrets:
gcloud secrets create telegram-bot-token --data-file=-
gcloud secrets add-iam-policy-binding telegram-bot-token \
  --member=serviceAccount:orbyn-bot@project.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

---

## 📈 ESCALABILIDAD

### Límites Actuales

- Single instance: ~100 leads/min (teorético)
- Bottleneck: LLM API (30s timeout)
- Google Sheets: rate limit ~300 writes/min

### Para Escalar (FASE 6)

```
1. Queue asincrónica (Redis/Celery)
   - Lead entra a queue
   - Workers procesan en paralelo
   - Retorna respuesta inmediatamente

2. Load balancing
   - N instancias de bot
   - Behind Nginx/HAProxy

3. Caché distribuido
   - Redis para resultados
   - TTL: 24h (leads similares)

4. Database real
   - PostgreSQL para logs
   - Elasticsearch para búsqueda
```

---

## 🆘 TROUBLESHOOTING

### Bot no responde

```bash
# 1. Verificar logs
docker logs orbyn-lead-qualifier | tail -100

# 2. Verificar circuit breaker status
# Buscar: "circuit_breaker_opened"

# 3. Verificar rate limits
# Buscar: "rate_limit_user_exceeded"

# 4. Restart
docker restart orbyn-lead-qualifier
```

### Latencia Alta (> 5s)

```
1. Verificar LLM provider:
   - ¿OpenAI está caído?
   - ¿Anthropic con rate limit?

2. Verificar Google Sheets:
   - ¿Está lento?
   - ¿Alcanzó quota?

3. Usar fallback provider

Logs:
- "lead_processor_high_latency"
- "llm_qualify_lead_primary_failed"
```

### Google Sheets Errors

```
Error: "403 Forbidden"
→ Service account no tiene permisos
→ Ir a Google Sheet, compartir con email del SA

Error: "Rate Limit Exceeded"
→ Demasiadas writes en corto tiempo
→ Implementar queue/batching

Error: "Not Found"
→ GOOGLE_SHEET_ID incorrecto
→ Copiar URL: /spreadsheets/d/[ID]/edit
```

---

## 📝 BACKUP Y DISASTER RECOVERY

### Backup de Google Sheets

```bash
# Script diario
0 2 * * * python scripts/backup_sheets.py

# Guardar en:
# - Google Drive respaldo
# - Cloud Storage (GCS)
# - Local comprimido
```

### Recovery Plan

```
1. Si bot se cae:
   - Restart automático (docker restart)
   - Heartbeat check cada 5 minutos

2. Si Google Sheets se corrompe:
   - Restore de backup diario
   - Máximo 24h de pérdida

3. Si LLM API no disponible:
   - Fallback automático a segundo provider
   - Mensajes quedan en queue
```

---

## 🔍 AUDITORÍA Y COMPLIANCE

### Logs Requeridos

```python
# Todos estos eventos se logean automáticamente:
- Cada lead recibido (telegram_user_id, timestamp)
- Decisión de cualificación
- Razón de rechazo
- Latencia del procesamiento
- Errores y reintentos
- Intentos de prompt injection (detectados)
```

### GDPR Compliance

```
1. Derecho al olvido: Poder eliminar data de un usuario
2. Portabilidad: Exportar datos de un usuario
3. Transparencia: Logs de qué se procesó

Implementación (FASE 6):
- Endpoint: DELETE /api/user/{telegram_id}
- Endpoint: GET /api/user/{telegram_id}/data
```

---

## 🎯 KPIs EN PRODUCCIÓN

### Métricas de Éxito

```
1. Disponibilidad: > 99.5%
2. Latencia P95: < 3 segundos
3. Accuracy ICP: > 95% (validar manualmente 10%)
4. Error rate: < 1%
5. Lead processing: 100+ por día
```

### Dashboard Recomendado

```
Datadog/Grafana dashboard con:
- Uptime (%)
- Latency (P50, P95, P99)
- Errors rate
- Circuit breaker status
- LLM provider health
- Google Sheets status
- Rate limit hits
- Injection attempts
```

---

## 📞 CONTACTO PARA EMERGENCIAS

```
On-call: +34 XXX XXX XXX
Email: devops@orbyn.ai
Slack: #lead-qualifier-production

Escalation:
1. DevOps team (30 min response)
2. Engineering manager (1h response)
3. VP Engineering (on-call on weekends)
```

---

## ✅ ÚLTIMA CHECKLIST ANTES DE LAUNCH

- [ ] Todos los tests pasan (100% coverage > 80%)
- [ ] Load testing realizado (simuló 1000 leads/min)
- [ ] Failover probado (LLM provider fallback funciona)
- [ ] Monitoreo y alertas activos
- [ ] Escalación de on-call documentada
- [ ] Runbooks creados para procedimientos comunes
- [ ] Team entrenado en manejo de incidentes
- [ ] Backup y disaster recovery plan comunicado
- [ ] Security audit completado
- [ ] Performance profiling realizado

**FECHA DE LAUNCH:** [A DEFINIR]
**OWNER:** [A ASIGNAR]
**APPROVED BY:** [A FIRMAR]
