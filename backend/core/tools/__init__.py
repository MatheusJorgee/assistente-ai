"""
Factory canônica de ferramentas para Function Calling.

Centraliza criação e registro das tools em um único ponto de entrada.
"""

try:
    from ..tools.terminal_tool import TerminalTool
    from ..tools.media_tool import MediaTool
    from ..tools.system_tool import SystemTool
    from ..tools.vision_tool import VisionTool
    from ..tools.os_tools import OSCommandTool, ProcessControlTool
    from ..tools.file_ops_tool import FileOpsTool
    from ..tools.memory_tools import MemoryTool, MemorizarInformacaoTool
    from ..tools.clipboard_tool import ClipboardTool
    from ..tools.network_scan_tool import NetworkScanTool
    from ..tools.vlc_tool import VLCTool
    from ..tools.web_search_tool import WebSearchTool
    from ..tools.visor_tool import MostrarVisorTool
    from ..tools.abrir_programa_tool import AbrirProgramaTool
    from ..tools.whatsapp_tool import WhatsAppTool
    from ..tools.calc_tool import CalcTool
    from ..tools.reminder_tool import ReminderTool
    from ..tools.finance_tool import FinanceTool
    from ..tools.holograma_tool import HologramaTool
    from ..tools.skills_tool import SkillsTool
    from ..tools.propor_ferramenta_tool import ProporFerramentaTool
    from ..tools.abrir_e_olhar_tool import AbrirEOlharTool
    from ..tools.pendencias_tool import PendenciasTool
    from ..tools.file_search_tool import FileSearchTool
    from ..tools.discord_tool import DiscordTool
    from ..tools.calendar_tool import CalendarTool
    from ..tools.people_tool import PeopleTool
    from ..tools.document_tool import DocumentTool
    from ..tools.macro_tool import MacroTool
    from ..tools.schedule_tool import ScheduleTool
    from ..tools.idea_tool import IdeaTool
    from ..tools.focus_tool import FocusTool
    from ..tools.draft_tool import DraftTool
    from ..tools.discord_friends_tool import DiscordFriendsTool
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
    from .memory_tools import MemoryTool, MemorizarInformacaoTool
    from .clipboard_tool import ClipboardTool
    from .network_scan_tool import NetworkScanTool
    from .vlc_tool import VLCTool
    from .web_search_tool import WebSearchTool
    from .visor_tool import MostrarVisorTool
    from .abrir_programa_tool import AbrirProgramaTool
    from .whatsapp_tool import WhatsAppTool
    from .calc_tool import CalcTool
    from .reminder_tool import ReminderTool
    from .finance_tool import FinanceTool
    from .holograma_tool import HologramaTool
    from .skills_tool import SkillsTool
    from .propor_ferramenta_tool import ProporFerramentaTool
    from .abrir_e_olhar_tool import AbrirEOlharTool
    from .pendencias_tool import PendenciasTool
    from .file_search_tool import FileSearchTool
    from .discord_tool import DiscordTool
    from .calendar_tool import CalendarTool
    from .people_tool import PeopleTool
    from .document_tool import DocumentTool
    from .macro_tool import MacroTool
    from .schedule_tool import ScheduleTool
    from .idea_tool import IdeaTool
    from .focus_tool import FocusTool
    from .draft_tool import DraftTool
    from .discord_friends_tool import DiscordFriendsTool
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
    Factory canônica que cria e registra ferramentas disponíveis para o cérebro.
    
    Returns:
        ToolRegistry com todas as ferramentas registradas
    """
    registry = ToolRegistry()
    
    # Registrar ferramentas de alto nível
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

    # Long-term memory tool — ÚNICA tool de memória exposta à LLM.
    # Nome propositalmente claro e direto: memorizar_informacao.
    # Aliases 'memory_manager', 'memory' etc. apontam para ela para compat.
    registry.register(
        MemorizarInformacaoTool(),
        aliases=[
            "memorizar",
            "memorizar_fato",
            "memory_manager",
            "memory",
            "memory_engine",
            "memory_retrieval",
            "obsidian_memory",
            "memoria_nuclear",
            "salvar_obsidian",
            "anotar_memoria",
            "memoria_diaria",
            "memoria_curto_prazo",
            "salvar_memoria_obsidian",
        ],
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

    # Busca factual em tempo real (clima, notícias, status) — leve, sem navegador
    registry.register(
        WebSearchTool(),
        aliases=["web_search", "pesquisar_web", "buscar_online", "pesquisar_informacao"],
    )

    # Visor visual na própria página (card de notícia, gráfico, imagem)
    registry.register(
        MostrarVisorTool(),
        aliases=["visor", "mostrar_visor", "exibir_no_visor"],
    )

    # Abrir programas/jogos instalados pelo nome
    registry.register(
        AbrirProgramaTool(),
        aliases=["abrir", "abrir_app", "iniciar_programa", "executar_programa", "abrir_jogo"],
    )

    # WhatsApp Web (enviar, ler, triagem) via Edge CDP
    registry.register(
        WhatsAppTool(),
        aliases=["whatsapp_web", "enviar_whatsapp", "mensagem_whatsapp", "triagem_whatsapp", "ler_whatsapp"],
    )

    # Calculadora exata (raciocínio numérico sem erro de cabeça)
    registry.register(
        CalcTool(),
        aliases=["calc", "calculadora", "calcular_expressao", "matematica"],
    )

    # Lembretes e datas anuais (entrega proativa pelo monitor)
    registry.register(
        ReminderTool(),
        aliases=["lembrar", "lembretes", "agenda", "criar_lembrete", "aniversario"],
    )

    # Co-piloto financeiro (cotações keyless + watchlist com avisos)
    registry.register(
        FinanceTool(),
        aliases=["financas", "cotacao", "cotar", "watchlist", "investimentos", "cripto"],
    )

    # Hologramas (globo + painéis de viagem com dados abertos reais)
    registry.register(
        HologramaTool(),
        aliases=["holograma", "mapa_holografico", "onde_fica", "planejar_viagem", "viagem", "roteiro_viagem"],
    )

    # Skills de texto aprovadas (propor vai para a fila de aprovação)
    registry.register(SkillsTool(), aliases=["skill", "habilidades", "salvar_skill"])
    registry.register(ProporFerramentaTool(), aliases=["nova_ferramenta", "criar_ferramenta"])
    _abrir_olhar = AbrirEOlharTool()
    _abrir_olhar.set_registry(registry)
    registry.register(_abrir_olhar, aliases=["abrir_programa_e_olhar", "abrir_com_login"])
    registry.register(PendenciasTool(), aliases=["pendencia", "em_aberto"])

    # Busca de arquivos nas pastas do usuário
    registry.register(
        FileSearchTool(),
        aliases=["buscar_arquivo", "achar_arquivo", "localizar_arquivo", "encontrar_arquivo"],
    )

    # Triagem do Discord (contador de menções/DMs via título da janela)
    registry.register(
        DiscordTool(),
        aliases=["discord", "triagem_discord", "checar_discord"],
    )

    # Google Agenda via iCal (consulta de compromissos reais)
    registry.register(
        CalendarTool(),
        aliases=["agenda", "calendario", "compromissos", "google_agenda"],
    )

    # CRM pessoal: as pessoas da vida do Matheus
    registry.register(
        PeopleTool(),
        aliases=["pessoas", "contatos", "crm", "quem_e"],
    )

    # Leitura/resumo de documentos (PDF, docx, txt, md)
    registry.register(
        DocumentTool(),
        aliases=["ler_documento", "documento", "resumir_documento", "ler_pdf"],
    )

    # Macros/modos (uma cena disparada por um comando)
    registry.register(
        MacroTool(),
        aliases=["macro", "modo", "cena", "rotina_setup"],
    )

    # Ações agendadas que executam sozinhas no horário
    registry.register(
        ScheduleTool(),
        aliases=["agendar_acao", "agendar", "tarefa_agendada", "rotina_agendada"],
    )

    # Inbox de ideias (captura rápida)
    registry.register(
        IdeaTool(),
        aliases=["anotar_ideia", "ideia", "inbox", "anotar_rapido"],
    )

    # Coach de foco (pomodoro)
    registry.register(
        FocusTool(),
        aliases=["foco", "pomodoro", "sessao_foco", "concentrar"],
    )

    # Rascunho no estilo do Matheus
    registry.register(
        DraftTool(),
        aliases=["rascunhar", "redigir", "escrever_mensagem", "draft"],
    )

    # Amigos online no Discord (requer bot configurado)
    registry.register(
        DiscordFriendsTool(),
        aliases=["discord_amigos", "amigos_online", "quem_ta_online"],
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
    "WebSearchTool",
    "MostrarVisorTool",
    "AbrirProgramaTool",
    "WhatsAppTool",
    "CalcTool",
    "ReminderTool",
    "FinanceTool",
    "HologramaTool",
    "SkillsTool",
    "ProporFerramentaTool",
    "AbrirEOlharTool",
    "PendenciasTool",
    "FileSearchTool",
    "DiscordTool",
    "CalendarTool",
    "PeopleTool",
    "DocumentTool",
    "MacroTool",
    "ScheduleTool",
    "IdeaTool",
    "FocusTool",
    "DraftTool",
    "DiscordFriendsTool",
    "inicializar_ferramentas",
]

