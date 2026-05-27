"""
Modelos para la respuesta de cualificación del LLM.
Utiliza Pydantic para garantizar salidas estructuradas consistentes.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


class LeadQualification(BaseModel):
    """
    Respuesta estructurada de la cualificación de un lead.
    Este modelo se usa para forzar salidas de LLM consistentes.
    """

    is_qualified: bool = Field(
        ...,
        description="Si el lead cumple con el ICP: True si cualificado, False en caso contrario"
    )
    reason: str = Field(
        ...,
        description="Explicación concisa en 2-3 líneas del por qué fue cualificado o no",
        min_length=10,
        max_length=500
    )

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        """
        Valida que la razón sea clara y no contenga caracteres inválidos.
        """
        v = v.strip()
        if len(v) < 10:
            raise ValueError("La razón debe tener al menos 10 caracteres")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "is_qualified": True,
                "reason": "Empresa de consultoría con 20 empleados en Madrid, interesada en automatizar procesos. Cumple todos los criterios del ICP."
            }
        }


class QualificationResult(BaseModel):
    """
    Resultado completo de cualificación incluye metadata y auditoría.
    """

    lead_id: Optional[str] = Field(None, description="ID único del lead generado")
    qualification: LeadQualification = Field(..., description="Resultado de cualificación")
    metadata: Optional[dict] = Field(default_factory=dict, description="Metadata adicional")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Cuándo se creó")
    model_used: str = Field(..., description="Modelo de LLM usado")

    class Config:
        json_schema_extra = {
            "example": {
                "lead_id": "lead_123456",
                "qualification": {
                    "is_qualified": True,
                    "reason": "Empresa de servicios con 15 empleados en Barcelona, interés en IA."
                },
                "metadata": {"processing_time_ms": 1234},
                "model_used": "gpt-4o-mini"
            }
        }
