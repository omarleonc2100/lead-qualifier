"""
Módulo de configuración centralizada del proyecto.
Exporta la configuración global para ser usada en toda la aplicación.
"""

from config.settings import Settings
from config.constants import ICP_CRITERIA, COMPANY_TYPES, REGIONS

__all__ = ["Settings", "ICP_CRITERIA", "COMPANY_TYPES", "REGIONS"]

# Singleton de configuración
settings = Settings()
