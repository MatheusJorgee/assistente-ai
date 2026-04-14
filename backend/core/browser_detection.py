"""
Identificação de Ambiente (Browser & Tabs Detection)
Sistema para detectar navegadores instalados, seus executáveis e abrir com browser específico.

Suporta: Edge, Chrome, Brave, Firefox (Windows)
"""

import subprocess
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Callable, Any
from dataclasses import dataclass
from enum import Enum
import shutil

# Importar winreg apenas em Windows
try:
    import winreg
except ImportError:
    winreg = None  # Fallback para non-Windows


class BrowserType(Enum):
    """Navegadores suportados."""
    EDGE = "edge"
    CHROME = "chrome"
    BRAVE = "brave"
    FIREFOX = "firefox"
    DEFAULT = "default"


@dataclass
class BrowserRegistry:
    """Registro de navegador instalado."""
    type: BrowserType
    name: str
    executable_path: Optional[str] = None
    is_installed: bool = False
    
    def to_dict(self):
        return {
            'type': self.type.value,
            'name': self.name,
            'executable_path': self.executable_path,
            'is_installed': self.is_installed
        }


class BrowserDetector:
    """
    Detecta navegadores instalados no Windows.
    Localiza caminhos de executáveis via Registry e PATH.
    """
    
    # Caminhos típicos onde navegadores podem estar
    COMMON_PATHS = {
        BrowserType.EDGE: [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        BrowserType.CHROME: [
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Users\{user}\AppData\Local\Google\Chrome\Application\chrome.exe",
        ],
        BrowserType.BRAVE: [
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Users\{user}\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
        BrowserType.FIREFOX: [
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Users\{user}\AppData\Local\Mozilla Firefox\firefox.exe",
        ],
    }
    
    # Chaves do Registry para encontrar navegadores
    REGISTRY_KEYS = {
        BrowserType.EDGE: [
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Edge\Client"),
        ],
        BrowserType.CHROME: [
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome"),
        ],
        BrowserType.BRAVE: [
            (winreg.HKEY_LOCAL_MACHINE, r"Software\BraveSoftware\Brave"),
        ],
        BrowserType.FIREFOX: [
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Mozilla\Mozilla Firefox"),
        ],
    }
    
    def __init__(self, event_bus_callback: Optional[Callable] = None):
        """
        Args:
            event_bus_callback: Função para emitir eventos (async)
        """
        self._browsers: Dict[BrowserType, BrowserRegistry] = {}
        self._event_bus = event_bus_callback
        self._detected = False
    
    async def _emit_event(self, event_type: str, data: Any = None):
        """Emitir evento via EventBus."""
        if self._event_bus:
            try:
                await self._event_bus(event_type, data)
            except Exception as e:
                print(f"[ERRO] Falha ao emitir evento {event_type}: {e}")
    
    def _check_registry(self, hkey, subkey) -> Optional[str]:
        """
        Tenta localizar executável no Registry do Windows.
        
        Args:
            hkey: Chave do registry
            subkey: Subchave
            
        Returns:
            Caminho do executável ou None
        """
        if not winreg:
            return None  # Não é Windows
        
        try:
            with winreg.OpenKey(hkey, subkey) as key:
                # Procura por "InstallLocation" ou "Path"
                for attr_name in ['InstallLocation', 'Path']:
                    try:
                        value, _ = winreg.QueryValueEx(key, attr_name)
                        if value and Path(value).exists():
                            return value
                    except:
                        continue
        except:
            pass
        
        return None
    
    def _find_browser_executable(self, browser_type: BrowserType) -> Optional[str]:
        """
        Localiza caminho do executável de um navegador.
        
        Estratégia:
        1. Procurar em caminhos comuns
        2. Verificar Registry (apenas Windows)
        3. Usar 'where' command (PATH)
        
        Args:
            browser_type: Tipo de navegador
            
        Returns:
            Caminho completo do executável ou None
        """
        # Estratégia 1: Caminhos comuns
        common_paths = self.COMMON_PATHS.get(browser_type, [])
        username = Path.home().name
        
        for path_template in common_paths:
            path = path_template.replace('{user}', username)
            if Path(path).exists():
                return path
        
        # Estratégia 2: Registry (apenas Windows)
        if winreg:
            registry_keys = self.REGISTRY_KEYS.get(browser_type, [])
            for hkey, subkey in registry_keys:
                registry_path = self._check_registry(hkey, subkey)
                if registry_path:
                    return registry_path
        
        # Estratégia 3: 'where' command (Windows) / 'which' (Unix)
        try:
            exe_name = {
                BrowserType.EDGE: "msedge.exe" if subprocess.os.name == 'nt' else "msedge",
                BrowserType.CHROME: "chrome.exe" if subprocess.os.name == 'nt' else "google-chrome",
                BrowserType.BRAVE: "brave.exe" if subprocess.os.name == 'nt' else "brave",
                BrowserType.FIREFOX: "firefox.exe" if subprocess.os.name == 'nt' else "firefox",
            }.get(browser_type)
            
            if exe_name:
                cmd = 'where' if subprocess.os.name == 'nt' else 'which'
                result = subprocess.run(
                    [cmd, exe_name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return result.stdout.strip().split('\n')[0]
        except:
            pass
        
        return None
    
    async def detect_installed_browsers(self) -> Dict[BrowserType, BrowserRegistry]:
        """
        Detecta navegadores instalados no sistema.
        
        Returns:
            Dicionário {BrowserType: BrowserRegistry}
        """
        detected = {}
        
        for browser_type in [BrowserType.EDGE, BrowserType.CHROME, BrowserType.BRAVE, BrowserType.FIREFOX]:
            exe_path = self._find_browser_executable(browser_type)
            
            registry = BrowserRegistry(
                type=browser_type,
                name=browser_type.value.title(),
                executable_path=exe_path,
                is_installed=exe_path is not None
            )
            
            detected[browser_type] = registry
            self._browsers[browser_type] = registry
            
            await self._emit_event('browser_detected', {
                'browser': browser_type.value,
                'executable': exe_path
            })
        
        self._detected = True
        return detected
    
    async def open_url(
        self,
        url: str,
        browser_type: Optional[BrowserType] = None
    ) -> bool:
        """
        Abre URL em navegador específico.
        
        Args:
            url: URL a abrir
            browser_type: Tipo de navegador (None = padrão do sistema)
            
        Returns:
            True se conseguiu abrir
        """
        # Se não foi detectado ainda, fazer detecção
        if not self._detected:
            await self.detect_installed_browsers()
        
        # Se browser_type não especificado, usar padrão
        if browser_type is None:
            browser_type = BrowserType.DEFAULT
        
        try:
            if browser_type == BrowserType.DEFAULT:
                # Usar navegador padrão do Windows
                import webbrowser
                webbrowser.open(url)
                await self._emit_event('url_opened', {
                    'url': url,
                    'browser': 'system_default'
                })
                return True
            
            # Procurar navegador específico
            browser_registry = self._browsers.get(browser_type)
            
            if not browser_registry or not browser_registry.is_installed:
                await self._emit_event('browser_not_found', {
                    'browser': browser_type.value
                })
                return False
            
            # Abrir com navegador específico
            subprocess.Popen(
                [browser_registry.executable_path, url],
                start_new_session=True
            )
            
            await self._emit_event('url_opened', {
                'url': url,
                'browser': browser_type.value,
                'executable': browser_registry.executable_path
            })
            
            return True
        
        except Exception as e:
            await self._emit_event('browser_open_error', {
                'url': url,
                'browser': browser_type.value if browser_type else 'unknown',
                'error': str(e)
            })
            return False
    
    async def get_installed_browsers(self) -> List[BrowserRegistry]:
        """
        Lista navegadores instalados.
        
        Returns:
            Lista de BrowserRegistry para navegadores instalados
        """
        if not self._detected:
            await self.detect_installed_browsers()
        
        return [reg for reg in self._browsers.values() if reg.is_installed]
    
    def get_browser_by_name(self, name: str) -> Optional[BrowserRegistry]:
        """
        Localiza navegador por nome (fuzzy match).
        
        Args:
            name: Nome ou parte do nome (ex: "Chrome", "edge", "brave")
            
        Returns:
            BrowserRegistry ou None
        """
        name_lower = name.lower()
        
        for browser_type, registry in self._browsers.items():
            if name_lower in registry.name.lower() or name_lower in browser_type.value.lower():
                if registry.is_installed:
                    return registry
        
        return None
    
    async def list_open_tabs(self, browser_type: BrowserType) -> List[str]:
        """
        EXPERIMENTAL: Tenta listar abas abertas em navegador.
        
        Limitações: Funciona apenas em Edge/Chrome via DevTools Protocol
        Requer extensão ou script auxiliar
        
        Args:
            browser_type: Tipo de navegador
            
        Returns:
            Lista de URLs das abas abertas
        """
        # Feature futura - requer integração com Remote Debugging Protocol
        # Por enquanto, apenas esboço
        await self._emit_event('tabs_listing_requested', {
            'browser': browser_type.value,
            'note': 'Feature não totalmente implementada - requer DevTools Protocol'
        })
        
        return []


# === HELPER FUNCTIONS ===

async def create_browser_detector(event_bus_callback: Optional[Callable] = None) -> BrowserDetector:
    """
    Factory para criar BrowserDetector e fazer detecção inicial.
    
    Args:
        event_bus_callback: Callback para eventos
        
    Returns:
        BrowserDetector com navegadores já detectados
    """
    detector = BrowserDetector(event_bus_callback)
    await detector.detect_installed_browsers()
    return detector


async def open_browser_window(url: str, browser_name: str = "default") -> bool:
    """
    Helper para abrir URL em navegador específico.
    
    Args:
        url: URL a abrir
        browser_name: Nome do navegador ("chrome", "edge", "brave", "firefox", "default")
        
    Returns:
        True se conseguiu abrir
    """
    detector = await create_browser_detector()
    
    # Mapear nome para BrowserType
    browser_map = {
        'chrome': BrowserType.CHROME,
        'edge': BrowserType.EDGE,
        'brave': BrowserType.BRAVE,
        'firefox': BrowserType.FIREFOX,
        'default': BrowserType.DEFAULT,
    }
    
    browser_type = browser_map.get(browser_name.lower(), BrowserType.DEFAULT)
    return await detector.open_url(url, browser_type)
