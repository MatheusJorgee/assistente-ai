"""
Core arquitetural: Tool Registry, DI Container, EventBus + v2.1 Modules.
"""

from .tool_registry import (
    Tool,
    ToolMetadata,
    ToolRegistry,
    EventBus,
    DIContainer,
    get_di_container
)

# v2.1 Modules
from .latency_aware import (
    LatencyAwarenessDetector,
    TaskComplexity,
    IntermediateMessage
)

from .media_queue import (
    create_media_queue,
    MediaQueue,
    MediaState,
    MediaItem,
    LoopMode
)

from .browser_detection import (
    create_browser_detector,
    BrowserDetector,
    BrowserType
)

from .search_reasoning import (
    DescriptiveSearchReasoningEngine,
    SearchResult,
    SearchConfidenceLevel
)

from .preferences import (
    create_preferences_engine,
    PreferenceRulesEngine,
    RuleCondition,
    RuleAction,
    PreferenceRule
)

# New: YouTube Loop + WhatsApp
from .youtube_loop import (
    create_youtube_loop_manager,
    YouTubeLoopManager,
    YouTubeLoopMode,
    YouTubeVideo,
    LoopSession as YouTubeLoopSession
)

from .whatsapp_sender import (
    create_whatsapp_sender,
    WhatsAppMessageSender,
    WhatsAppMessage,
    MessageStatus
)

__all__ = [
    # Core
    'Tool',
    'ToolMetadata',
    'ToolRegistry',
    'EventBus',
    'DIContainer',
    'get_di_container',
    
    # v2.1 Modules
    'LatencyAwarenessDetector',
    'TaskComplexity',
    'IntermediateMessage',
    'create_media_queue',
    'MediaQueue',
    'MediaState',
    'MediaItem',
    'LoopMode',
    'create_browser_detector',
    'BrowserDetector',
    'BrowserType',
    'DescriptiveSearchReasoningEngine',
    'SearchResult',
    'SearchConfidenceLevel',
    'create_preferences_engine',
    'PreferenceRulesEngine',
    'RuleCondition',
    'RuleAction',
    'PreferenceRule',
    
    # New Features
    'create_youtube_loop_manager',
    'YouTubeLoopManager',
    'YouTubeLoopMode',
    'YouTubeVideo',
    'YouTubeLoopSession',
    'create_whatsapp_sender',
    'WhatsAppMessageSender',
    'WhatsAppMessage',
    'MessageStatus'
]
