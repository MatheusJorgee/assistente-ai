"""
Inicializador de ferramentas.
Registra todas as ferramenta no ToolRegistry.
"""

from typing import Optional

# Imports resilientes para funcionar de qualquer cwd
try:
    from backend.core.tool_registry import get_di_container
    from backend.tools.terminal_tools import ExecutarTerminalTool, AprenderemExecutarTool
    from backend.tools.media_tools import (
        TocarMusicaSpotifyTool,
        TocarYoutubeTool,
        ControlarReproducaoTool,
        AbrirOuPesquisarTool
    )
    from backend.tools.vision_tools import CapturarVisaoTool, AnalisarVisaoComGeminiTool
    from backend.tools.memory_tools import GuardarMemoriaTool, BuscarMemoriaTool, ResolverAlvoComAprendizadoTool
except ModuleNotFoundError:
    # Fallback para modo script (quando rodado de dentro de backend)
    from core.tool_registry import get_di_container
    from tools.terminal_tools import ExecutarTerminalTool, AprenderemExecutarTool
    from tools.media_tools import (
        TocarMusicaSpotifyTool,
        TocarYoutubeTool,
        ControlarReproducaoTool,
        AbrirOuPesquisarTool
    )
    from tools.vision_tools import CapturarVisaoTool, AnalisarVisaoComGeminiTool
    from tools.memory_tools import GuardarMemoriaTool, BuscarMemoriaTool, ResolverAlvoComAprendizadoTool


def inicializar_ferramentas(
    oraculo_engine = None,
    database = None,
    spotify_client = None,
    youtube_controller = None,
    media_controller = None,
    ui_controller = None,
    gemini_client = None
):
    """
    Inicializa e registra todas as ferramentas no ToolRegistry.
    
    Args:
        oraculo_engine: Instância do OraculoEngine
        database: Instância do BaseDadosMemoria
        spotify_client: Cliente Spotify pronto
        youtube_controller: Controller YouTube
        media_controller: Controller de mídia genérico
        ui_controller: Controller de UI/abertura de apps
        gemini_client: Cliente Gemini
    """
    di = get_di_container()
    registry = di.tool_registry
    
    # Ferramentas de Terminal
    terminal_tool = ExecutarTerminalTool()
    registry.register(terminal_tool, aliases=['cmd', 'powershell', 'shell'])
    
    # Ferramenta de Aprendizado + Execução
    aprender_tool = AprenderemExecutarTool(oraculo_engine, database)
    registry.register(aprender_tool, aliases=['learn', 'oracle_exec'])
    
    # Ferramentas de Mídia
    spotify_tool = TocarMusicaSpotifyTool(spotify_client)
    registry.register(spotify_tool, aliases=['spotify', 'play_spotify'])
    
    youtube_tool = TocarYoutubeTool(youtube_controller)
    registry.register(youtube_tool, aliases=['youtube', 'play_youtube', 'yt'])
    
    media_control_tool = ControlarReproducaoTool(media_controller)
    registry.register(media_control_tool, aliases=['media', 'control', 'pause', 'play'])
    
    open_search_tool = AbrirOuPesquisarTool(ui_controller, oraculo_engine, database)
    registry.register(open_search_tool, aliases=['open', 'search', 'browser'])
    
    # Ferramentas de Visão
    capture_vision_tool = CapturarVisaoTool()
    registry.register(capture_vision_tool, aliases=['screenshot', 'screen', 'vision'])
    
    analyze_vision_tool = AnalisarVisaoComGeminiTool(gemini_client)
    # Injetar capture_tool para reutilização
    analyze_vision_tool.capture_tool = capture_vision_tool
    registry.register(analyze_vision_tool, aliases=['analyze_screen', 'vision_ai'])
    
    # Ferramentas de Memória
    save_memory_tool = GuardarMemoriaTool(database)
    registry.register(save_memory_tool, aliases=['memory', 'save', 'remember'])
    
    search_memory_tool = BuscarMemoriaTool(database)
    registry.register(search_memory_tool, aliases=['search_memory', 'recall'])
    
    resolve_target_tool = ResolverAlvoComAprendizadoTool(oraculo_engine, database)
    registry.register(resolve_target_tool, aliases=['resolve', 'disambiguate'])
    
    print(f"[OK] {len(registry.list_tools())} ferramentas registradas com sucesso")
    return registry
