"""
BRAIN/__init__.py - Exports do MÃ³dulo CÃ³rtex
=============================================

Facilita imports simples:
    from brain import QuintaFeiraBrain
    from core.gemini_provider import GeminiAdapter
"""

from .quinta_feira_brain import QuintaFeiraBrain, BrainResponse, VisionBuffer, MessageHistory

try:
    from core.gemini_provider import GeminiAdapter
except ImportError:
    from core.gemini_provider import GeminiAdapter

__all__ = [
    "QuintaFeiraBrain",
    "BrainResponse",
    "VisionBuffer",
    "MessageHistory",
    "GeminiAdapter",
]

