"""
Services - ExposiÃ§Ã£o de database, voz e outras dependÃªncias.
"""

try:
    from services.database import (
        Database,
        Message,
        Event,
        Image,
        get_database,
    )
    from services.voice_provider import (
        VoiceProvider,
        ElevenLabsProvider,
        PyTTSX3Provider,
        VoiceManager,
        get_voice_manager,
    )
except ImportError:
    from .database import (
        Database,
        Message,
        Event,
        Image,
        get_database,
    )
    from .voice_provider import (
        VoiceProvider,
        ElevenLabsProvider,
        PyTTSX3Provider,
        VoiceManager,
        get_voice_manager,
    )

__all__ = [
    # Database
    "Database",
    "Message",
    "Event",
    "Image",
    "get_database",
    # Voice
    "VoiceProvider",
    "ElevenLabsProvider",
    "PyTTSX3Provider",
    "VoiceManager",
    "get_voice_manager",
]

