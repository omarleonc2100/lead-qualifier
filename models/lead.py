"""
Modelos de datos para leads.
Usa Pydantic para validación automática y serialización.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


class LeadInput(BaseModel):
    """Modelo que representa los datos brutos de un lead recibido."""

    raw_text: str = Field(
        ...,
        description="Texto libre del lead tal como fue recibido",
        min_length=10,
        max_length=2000
    )
    telegram_user_id: int = Field(..., description="ID del usuario de Telegram")
    telegram_username: Optional[str] = Field(None, description="Username de Telegram")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Cuándo se recibió")

    @field_validator("raw_text")
    @classmethod
    def validate_raw_text(cls, v: str) -> str:
        """
        Valida que el texto no esté vacío después de limpiar espacios.
        """
        v = v.strip()
        if not v:
            raise ValueError("El texto del lead no puede estar vacío")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "raw_text": "Somos una empresa de consultoría en Madrid con 20 empleados. Buscamos automatizar nuestros procesos de ventas.",
                "telegram_user_id": 123456789,
                "telegram_username": "example_user",
                "timestamp": "2024-03-20T15:30:00"
            }
        }


class LeadMetadata(BaseModel):
    """Metadata extraída del lead para auditoría y debugging."""

    extracted_company_type: Optional[str] = Field(None, description="Tipo de empresa detectado")
    extracted_employees: Optional[int] = Field(None, description="Número de empleados detectado")
    extracted_region: Optional[str] = Field(None, description="Región detectada")
    extracted_interests: list[str] = Field(default_factory=list, description="Intereses detectados")
    processing_latency_ms: Optional[float] = Field(None, description="Latencia del procesamiento en ms")

    class Config:
        json_schema_extra = {
            "example": {
                "extracted_company_type": "consulting",
                "extracted_employees": 20,
                "extracted_region": "Spain",
                "extracted_interests": ["automation", "sales"],
                "processing_latency_ms": 1234.5
            }
        }
