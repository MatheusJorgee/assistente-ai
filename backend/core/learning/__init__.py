"""
Aprendizado contínuo da Quinta-Feira: reflexão periódica sobre as conversas
e hábitos do dia, destilando fatos estáveis para a memória de longo prazo —
e curiosidade ativa: pesquisas autônomas na internet (com guarda de segurança)
que viram aprendizado e assunto espontâneo.
"""

from .reflection_service import ReflectionService
from .curiosity_service import CuriosityService
from .search_guard import SearchGuard

__all__ = ["ReflectionService", "CuriosityService", "SearchGuard"]
