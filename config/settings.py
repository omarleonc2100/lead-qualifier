"""
Configuración centralizada usando Pydantic Settings.
Lee variables de entorno de forma segura y con validación de tipos.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional, List
from pathlib import Path
import logging


class Settings(BaseSettings):
    """
    Configuración centralizada de la aplicación.
    Hereda de BaseSettings para leer automáticamente desde variables de entorno.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # ============ TELEGRAM ============
    telegram_bot_token: str = Field(..., description="Token del bot de Telegram")
    telegram_chat_id: Optional[str] = Field(None, description="Chat ID para logs internos")

    # ============ LLM ============
    llm_provider: str = Field(
        default="openai",
        description="Proveedor de LLM: openai o anthropic"
    )
    openai_api_key: Optional[str] = Field(None, description="API key de OpenAI")
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="Modelo de OpenAI a usar"
    )
    anthropic_api_key: Optional[str] = Field(None, description="API key de Anthropic")
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Modelo de Anthropic a usar"
    )

    # ============ GOOGLE SHEETS ============
    google_sheets_credentials_path: Path = Field(
        default="./credentials/google_service_account.json",
        description="Ruta al archivo de credenciales de Google"
    )
    google_sheet_id: str = Field(..., description="ID de la Google Sheet")
    google_sheet_range: str = Field(
        default="Leads!A:F",
        description="Rango de la Google Sheet"
    )

    # ============ ICP CONFIG ============
    icp_min_employees: int = Field(
        default=5,
        description="Número mínimo de empleados del ICP"
    )
    icp_allowed_regions: List[str] = Field(
        default=["Spain", "Colombia", "Mexico", "Argentina", "Chile", "Peru", "Ecuador"],
        description="Regiones permitidas en ICP"
    )
    icp_company_types: List[str] = Field(
        default=["consulting", "services", "technology", "marketing"],
        description="Tipos de empresa permitidos en ICP"
    )
    icp_required_interests: List[str] = Field(
        default=["automation", "ai", "artificial-intelligence"],
        description="Intereses requeridos en ICP"
    )

    # ============ APPLICATION ============
    log_level: str = Field(
        default="INFO",
        description="Nivel de logging"
    )
    environment: str = Field(
        default="development",
        description="Entorno de ejecución: development, staging, production"
    )
    api_timeout: int = Field(
        default=30,
        description="Timeout en segundos para llamadas a APIs externas"
    )
    max_retries: int = Field(
        default=3,
        description="Número máximo de reintentos en caso de fallo"
    )

    # ============ SECURITY ============
    enable_prompt_injection_check: bool = Field(
        default=True,
        description="Habilitar validación contra prompt injection"
    )
    rate_limit_per_minute: int = Field(
        default=10,
        description="Límite de requests por minuto por usuario"
    )

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Valida que el ambiente sea uno de los permitidos."""
        allowed_envs = ["development", "staging", "production"]
        if v not in allowed_envs:
            raise ValueError(f"Environment must be one of {allowed_envs}")
        return v.lower()

    @field_validator("llm_provider", mode="before")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        """Valida que el proveedor de LLM sea válido."""
        allowed_providers = ["openai", "anthropic"]
        if v not in allowed_providers:
            raise ValueError(f"LLM provider must be one of {allowed_providers}")
        return v.lower()

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Valida que el nivel de log sea válido."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed_levels:
            raise ValueError(f"Log level must be one of {allowed_levels}")
        return v.upper()

    def get_log_level(self) -> int:
        """Retorna el nivel de logging como constante de logging."""
        return getattr(logging, self.log_level)

    def is_production(self) -> bool:
        """Retorna True si está en producción."""
        return self.environment == "production"

    def is_development(self) -> bool:
        """Retorna True si está en desarrollo."""
        return self.environment == "development"
