"""
Factory canÃ´nica de ferramentas para Function Calling.

Centraliza criaÃ§Ã£o e registro das tools em um Ãºnico ponto de entrada.
"""

try:
    from ..tools.terminal_tool import TerminalTool
    from ..tools.media_tool import MediaTool
    from ..tools.system_tool import SystemTool
    from ..tools.vision_tool import VisionTool
    from ..tools.os_tools import OSCommandTool, ProcessControlTool
    from ..tools.file_ops_tool import FileOpsTool
    from ..tools.memory_tools import MemoryTool
    from ..tools.clipboard_tool import ClipboardTool
    from ..tools.network_scan_tool import NetworkScanTool
    from ..tools.vlc_tool import VLCTool
    from ..tools.base import ToolRegistry
    from ..memory import MemoryManager
    from .. import (
        AuditLogger,
        FileSystemAdapter,
        PowerShellExecutor,
        ProcessAdapter,
        ToolCallTelemetry,
        create_default_policy_engine,
    )
except ImportError:
    from .terminal_tool import TerminalTool
    from .media_tool import MediaTool
    from .system_tool import SystemTool
    from .vision_tool import VisionTool
    from .os_tools import OSCommandTool, ProcessControlTool
    from .file_ops_tool import FileOpsTool
    from .memory_tools import MemoryTool
    from .clipboard_tool import ClipboardTool
    from .network_scan_tool import NetworkScanTool
    from .vlc_tool import VLCTool
    from .base import ToolRegistry
    from ..memory import MemoryManager
    from .. import (
        AuditLogger,
        FileSystemAdapter,
        PowerShellExecutor,
        ProcessAdapter,
        ToolCallTelemetry,
        create_default_policy_engine,
    )


def inicializar_ferramentas(event_publisher=None) -> ToolRegistry:
    """
    Factory canÃ´nica que cria e registra ferramentas disponÃ­veis para o cÃ©rebro.
    
    Returns:
        ToolRegistry com todas as ferramentas registradas
    """
    registry = ToolRegistry()
    
    # Registrar ferramentas de alto nÃ­vel
    registry.register(TerminalTool())
    registry.register(MediaTool())
    registry.register(SystemTool())
    registry.register(VisionTool())

    # v2 Host Capability Layer (novo stack com Policy + Adapters)
    policy_engine = create_default_policy_engine()
    telemetry = ToolCallTelemetry(AuditLogger(), event_publisher=event_publisher)

    ps_executor = PowerShellExecutor(policy_engine=policy_engine)
    process_adapter = ProcessAdapter(policy_engine=policy_engine)
    fs_adapter = FileSystemAdapter(policy_engine=policy_engine)

    registry.register(
        OSCommandTool(executor=ps_executor, telemetry=telemetry),
        aliases=["os_command", "powershell_v2", "executar_powershell_v2"],
    )
    registry.register(
        ProcessControlTool(
            process_adapter=process_adapter,
            policy_engine=policy_engine,
            telemetry=telemetry,
        ),
        aliases=["process_control", "sistema_processos_v2", "listar_processos_v2"],
    )
    registry.register(
        FileOpsTool(fs_adapter=fs_adapter, telemetry=telemetry),
        aliases=["file_ops", "filesystem_v2", "v2_file_ops"],
    )

    # Long-term memory tools
    memory_manager = MemoryManager()
    registry.register(
        MemoryTool(memory_manager=memory_manager),
        aliases=["memory", "memory_engine", "memory_retrieval"],
    )

    # Host utilities (zero-trace)
    registry.register(
        ClipboardTool(),
        aliases=["clipboard", "copy_to_clipboard"],
    )

    # Rede local
    registry.register(
        NetworkScanTool(),
        aliases=["scan_network", "lan_scan", "discover_devices"],
    )

    # VLC via HTTP API (requer VLC com web interface ativada)
    registry.register(
        VLCTool(),
        aliases=["vlc", "media_vlc"],
    )

    return registry


# Exports
__all__ = [
    "ToolRegistry",
    "TerminalTool",
    "MediaTool",
    "SystemTool",
    "VisionTool",
    "OSCommandTool",
    "ProcessControlTool",
    "FileOpsTool",
    "MemoryTool",
    "ClipboardTool",
    "NetworkScanTool",
    "VLCTool",
    "inicializar_ferramentas",
]

