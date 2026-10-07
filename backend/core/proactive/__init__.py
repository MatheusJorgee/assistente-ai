"""
Presença proativa da Quinta-Feira: sentidos (ContextSensor) + monitor que
observa o sistema/ambiente e fala com naturalidade quando algo importa.
"""

from .context_snapshot import ContextSensor
from .proactive_monitor import ProactiveMonitor

__all__ = ["ContextSensor", "ProactiveMonitor"]
