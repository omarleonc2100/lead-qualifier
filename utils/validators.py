"""
Validadores reutilizables para inputs y seguridad.
"""

import re
from typing import List
from config.constants import PROMPT_INJECTION_PATTERNS


def sanitize_input(text: str) -> str:
    """
    Sanitiza un texto de entrada removiendo caracteres peligrosos.

    Args:
        text: Texto a sanitizar

    Returns:
        Texto sanitizado
    """
    # Remover caracteres de control y normalizaciones básicas
    text = text.strip()
    # Remover múltiples espacios en blanco
    text = re.sub(r'\s+', ' ', text)
    return text


def detect_prompt_injection(text: str) -> bool:
    """
    Detecta intentos básicos de prompt injection.
    NOTA: Esta es una defensa básica. En producción se requieren medidas más robustas.

    Args:
        text: Texto a analizar

    Returns:
        True si se detecta posible injection, False en caso contrario
    """
    text_lower = text.lower()

    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.lower() in text_lower:
            return True

    return False


def validate_text_length(text: str, min_length: int = 10, max_length: int = 2000) -> bool:
    """
    Valida que el texto tenga una longitud aceptable.

    Args:
        text: Texto a validar
        min_length: Longitud mínima
        max_length: Longitud máxima

    Returns:
        True si es válido
    """
    return min_length <= len(text.strip()) <= max_length
