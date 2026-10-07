"""Google Agenda via iCal (sem OAuth): leitura de compromissos."""

from .ical import proximos_eventos, eventos_de_hoje, formatar

__all__ = ["proximos_eventos", "eventos_de_hoje", "formatar"]
