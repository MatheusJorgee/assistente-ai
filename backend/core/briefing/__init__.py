"""
Módulo de Briefing Matinal da Quinta-Feira.

Reúne clima (OpenWeather) + notícias (RSS Google News) e compõe um resumo
falado natural via LLM. Projetado para rodar uma vez na inicialização do PC.
"""

from .weather import get_weather
from .news import get_top_news
from .briefing_service import gerar_briefing

__all__ = ["get_weather", "get_top_news", "gerar_briefing"]
