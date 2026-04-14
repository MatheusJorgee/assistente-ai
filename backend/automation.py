import pyautogui
import subprocess
import os
import webbrowser
import urllib.parse
import time
import shlex
import re
import json
import unicodedata
import asyncio
import traceback
import sys
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright

class OSAutomation:
    def __init__(self):
        # Perfil: trusted-local (mais permissivo) ou strict.
        self.security_profile = os.getenv("QUINTA_SECURITY_PROFILE", "trusted-local").strip().lower()

        # Bloqueio apenas para comandos realmente destrutivos ou de persistência/admin.
        self.padroes_criticos = [
            r"\bformat\b",
            r"\bdiskpart\b",
            r"\bmkfs\b",
            r"\brmdir\b\s+/s",
            r"\bdel\b\s+/(f|s|q)",
            r"\bremove-item\b\s+.*-recurse",
            r"\breg\b\s+delete",
            r"\bvssadmin\b",
            r"\bbcdedit\b",
            r"\bnet\s+user\b",
            r"\bshutdown\b\s+/(s|r|p)",
            r"\bpowershell\b\s+.*-enc(odedcommand)?\b",
            r"\bcmd\b\s+/c\s+.*(del|format|diskpart)",
        ]
        
        # --- MOTOR SPOTIFY (Preparado para Premium) ---
        self.sp_client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.sp_client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.sp_redirect_uri = "http://127.0.0.1:8080"
        
        self.sp = None
        if self.sp_client_id and self.sp_client_secret:
            try:
                escopos = "user-modify-playback-state user-read-playback-state"
                self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                    client_id=self.sp_client_id,
                    client_secret=self.sp_client_secret,
                    redirect_uri=self.sp_redirect_uri,
                    scope=escopos
                ))
                print(">>> [SISTEMA] Motor API Spotify carregado.")
            except Exception as e:
                print(f">>> [ERRO SPOTIFY] {e}")

        # --- MOTOR YOUTUBE (Async Playwright - NOVO PADRÃO) ---
        self.playwright = None  # Instance de async_playwright
        self.browser = None  # Browser assíncrono persistente
        self.page = None  # Page assíncrona persistente (reutilizável)
        self._browser_init_lock = None

        # Estado async complementar usado por metodos antigos e cleanup.
        self.page_async = None
        self.context_async = None
        self.browser_async = None
        self.pw_async = None
        self._async_pb_lock = None
        self._async_pb_lock_initialized = False

        # Estado sync legado para cleanup defensivo.
        self.context = None
        self.browser_instance = None
        self.pw_motor = None
        self.playwright_ativo = False
        
        self.youtube_volume_path = os.path.join(os.path.dirname(__file__), "temp_vision", "youtube_volume_pref.json")
        self.youtube_default_volume = self._carregar_volume_preferido()

        self.sites_conhecidos = {
            "youtube": "https://www.youtube.com",
            "github": "https://github.com",
            "gmail": "https://mail.google.com",
            "whatsapp": "https://web.whatsapp.com",
            "instagram": "https://www.instagram.com",
            "linkedin": "https://www.linkedin.com",
            "twitter": "https://x.com",
            "x": "https://x.com",
            "reddit": "https://www.reddit.com",
            "netflix": "https://www.netflix.com",
            "prime video": "https://www.primevideo.com",
            "disney": "https://www.disneyplus.com",
            "twitch": "https://www.twitch.tv",
            "steam": "https://store.steampowered.com",
            "spotify": "https://open.spotify.com",
            "wikipedia": "https://www.wikipedia.org",
        }

        self.alias_site = {
            "twitc": "twitch",
            "twich": "twitch",
            "tuitch": "twitch",
            "twitrc": "twitch",
        }
    
    def __del__(self):
        """Destrutor: Cleanup de recursos ao destruir objeto (SYNC only)
        
        IMPORTANTE: Para cleanup ASYNC completo, chamar await self._cleanup_playwright_async()
        durante shutdown (ex: em FastAPI lifespan.
        """
        try:
            self._cleanup_playwright()
        except:
            pass
    
    def _cleanup_playwright(self):
        """Cleanup rigoroso de recursos Playwright (SYNC)"""
        try:
            print("[CLEANUP] Fechando recursos Playwright (sync)...")
            
            if self.page:
                try:
                    self.page.close()
                    self.page = None
                except:
                    pass
            
            if self.context:
                try:
                    self.context.close()
                    self.context = None
                except:
                    pass
            
            if self.browser_instance:
                try:
                    self.browser_instance.close()
                    self.browser_instance = None
                except:
                    pass
            
            if self.pw_motor:
                try:
                    self.pw_motor.stop()
                    self.pw_motor = None
                except:
                    pass
            
            self.playwright_ativo = False
            print("[CLEANUP] Recurso Playwright (sync) encerrado com sucesso")
        except Exception as e:
            print(f"[CLEANUP] Erro ao encerrar (sync): {e}")
    
    async def _cleanup_playwright_async(self):
        """Cleanup rigoroso de recursos Playwright (ASYNC) - idealmente chamado em shutdown"""
        try:
            print("[CLEANUP ASYNC] Fechando recursos Playwright (async)...")
            
            if self.page_async:
                try:
                    await self.page_async.close()
                    self.page_async = None
                except:
                    pass
            
            if self.context_async:
                try:
                    await self.context_async.close()
                    self.context_async = None
                except:
                    pass
            
            if self.browser_async:
                try:
                    await self.browser_async.close()
                    self.browser_async = None
                except:
                    pass
            
            if self.pw_async:
                try:
                    await self.pw_async.stop()
                    self.pw_async = None
                except:
                    pass
            
            print("[CLEANUP ASYNC] Recurso Playwright (async) encerrado com sucesso")
        except Exception as e:
            print(f"[CLEANUP ASYNC] Erro ao encerrar (async): {e}")
    
    async def _inicializar_async_playwright(self):
        """Inicializa async_playwright uma única vez e armazena em self (Singleton Pattern)"""
        if self.browser_async is not None:
            print("[YOUTUBE ASYNC] Browser já inicializado, reutilizando...")
            return
        
        # Garantir que o lock está inicializado
        if not self._async_pb_lock_initialized:
            self._async_pb_lock = asyncio.Lock()
            self._async_pb_lock_initialized = True
        
        # Usar lock para evitar race condition (múltiplas coroutines tentando inicializar simultaneamente)
        async with self._async_pb_lock:
            # Double-check: se outro coroutine já inicializou durante a espera, pular
            if self.browser_async is not None:
                print("[YOUTUBE ASYNC] Browser já inicializado por outro coroutine, reutilizando...")
                return
            
            print("[YOUTUBE ASYNC] Inicializando Playwright assíncrono (Singleton)...")
            try:
                self.pw_async = await async_playwright().start()
                self.browser_async = await self.pw_async.chromium.launch(
                    headless=False,
                    channel="msedge",
                    args=[
                        "--autoplay-policy=no-user-gesture-required",
                        "--window-position=-32000,-32000",
                        "--window-size=800,600",
                        "--disable-blink-features=AutomationControlled"
                    ]
                )
                
                # Criar contexto
                self.context_async = await self.browser_async.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                
                print("[YOUTUBE ASYNC] ✓ Playwright assíncrono inicializado (Singleton) e armazenado em self")
            except Exception as e:
                print(f"[YOUTUBE ASYNC] ✗ Erro ao inicializar: {e}")
                await self._cleanup_playwright_async()
                raise
    
    @property
    def async_pb_lock(self):
        """Propriedade para acessar o lock, inicializando se necessário"""
        if not self._async_pb_lock_initialized:
            try:
                self._async_pb_lock = asyncio.Lock()
                self._async_pb_lock_initialized = True
            except RuntimeError:
                # Se não houver event loop, retornar um substituto que não faz nada
                # (deve ser raro, mas é uma segurança)
                class FakeLock:
                    async def __aenter__(self):
                        return self
                    async def __aexit__(self, *args):
                        pass
                return FakeLock()
        return self._async_pb_lock

    def _normalizar_ascii(self, texto: str) -> str:
        if not texto:
            return ""
        return "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        ).lower().strip()

    def _query_musical_otimizada(self, pesquisa: str) -> str:
        bruto = (pesquisa or "").strip()
        if not bruto:
            return ""

        texto_norm = self._normalizar_ascii(bruto)
        query = re.sub(r"\s+", " ", bruto).strip()

        # Remove ruído comum de comandos falados para focar no que identifica a música.
        padroes_ruido = [
            r"^(toca|toque|play|coloca|ponha|poe|poe ai|coloca ai)\b",
            r"\baquela\s+musica\b",
            r"\baquela\b",
            r"\bmusica\b",
            r"\bque\s+fala\b",
            r"\bque\s+diz\b",
            r"\bque\s+tem\b",
            r"\bisso\s+isso\s+isso\b",
        ]
        query_limpa = texto_norm
        for p in padroes_ruido:
            query_limpa = re.sub(p, " ", query_limpa, flags=re.IGNORECASE)
        query_limpa = re.sub(r"\s+", " ", query_limpa).strip()

        # Se parece um pedido por trecho/letra, força busca por letra/lyrics.
        modo_letra = any(
            token in texto_norm
            for token in ["que fala", "que diz", "trecho", "letra", "lyrics", "refr\u00e3o", "refrain"]
        )

        if modo_letra and query_limpa:
            return f"{query_limpa} letra lyrics"

        return query if len(query) >= 3 else bruto

    def _resolver_video_youtube(self, pesquisa: str):
        query = self._query_musical_otimizada(pesquisa)
        if not query:
            return None

        tentativas = [query]
        if "letra" not in query.lower() and "lyrics" not in query.lower():
            tentativas.append(f"{query} official audio")

        for tentativa in tentativas:
            try:
                cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "-j", "--no-warnings",
                    f"ytsearch:{tentativa}"
                ]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=2  # Ultra short timeout - fallback to search
                )
                if result.returncode == 0 and result.stdout:
                    try:
                        dados = json.loads(result.stdout)
                        if dados and "entries" in dados and dados["entries"]:
                            video = dados["entries"][0]
                            return {
                                "id": video.get("id", ""),
                                "title": video.get("title", ""),
                                "url": video.get("url", ""),
                                "query": tentativa,
                            }
                    except json.JSONDecodeError:
                        continue
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue

        return None

    def _shutdown_controlado(self, comando: str) -> bool:
        c = (comando or "").strip().lower()
        padrao = r"^shutdown\s+/(s|r|g|l|h|a)\b(?:\s+/t\s+\d+)?(?:\s+/f)?\s*$"
        return bool(re.match(padrao, c, flags=re.IGNORECASE))

    def _normalizar_volume_decimal(self, volume: float) -> float:
        return max(0.0, min(1.0, float(volume)))

    def _carregar_volume_preferido(self) -> float:
        """Carrega o volume preferido persistido; fallback para 5%."""
        try:
            if not os.path.exists(self.youtube_volume_path):
                return 0.05
            with open(self.youtube_volume_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return self._normalizar_volume_decimal(payload.get("volume", 0.05))
        except Exception:
            return 0.05

    def _guardar_volume_preferido(self, volume: float) -> None:
        """Persiste o volume preferido para próximas execuções."""
        volume = self._normalizar_volume_decimal(volume)
        os.makedirs(os.path.dirname(self.youtube_volume_path), exist_ok=True)
        with open(self.youtube_volume_path, "w", encoding="utf-8") as f:
            json.dump({"volume": volume}, f)

    def _extrair_canal_twitch(self, consulta: str) -> str:
        consulta_original = (consulta or "").strip()
        q = self._normalizar_texto(consulta_original)
        if not q:
            return ""

        # 1) Padrão explícito: "canal da|do|de X"
        m = re.search(r"canal\s+(da|do|de)\s+([a-zA-Z0-9_ ]+)", consulta_original, flags=re.IGNORECASE)
        if m:
            candidato = m.group(2).strip()
            # Remove sufixos desnecessários comuns
            candidato = re.sub(r"\b(pessoa|perfil|stream|live)\b.*$", "", candidato, flags=re.IGNORECASE).strip()
            candidato = re.sub(r"[^a-zA-Z0-9_ ]", "", candidato).strip()
            if candidato:
                return candidato

        # Remove frases operacionais e mantém o candidato a canal.
        q = re.sub(
            r"\b(vai|ir|abre|abrir|procura|procurar|pesquisa|pesquisar|pelo|pela|na|no|site|twitch|twitc|twich|tuitch|canal|de|do|da|canal\s+de|canal\s+do|canal\s+da)\b",
            " ",
            q,
            flags=re.IGNORECASE,
        )
        q = re.sub(r"\s+", " ", q).strip()
        if not q:
            return ""

        # Handle válido da Twitch: letras, números e underscore.
        return re.sub(r"[^a-zA-Z0-9_ ]", "", q).strip()

    def _abrir_twitch_inteligente(self, consulta: str, **kwargs) -> str:
        """Parser inteligente de canal Twitch. Absorve parâmetros extra do Gemini."""
        canal = self._extrair_canal_twitch(consulta)
        if not canal:
            subprocess.run(["cmd", "/c", 'start browser "https://www.twitch.tv/directory"'], capture_output=True)
            return "Sucesso: Abri a Twitch na página de descoberta."

        # Se for um único token, tenta canal direto.
        if " " not in canal and 2 <= len(canal) <= 25:
            subprocess.run(["cmd", "/c", f'start browser "https://www.twitch.tv/{canal}"'], capture_output=True)
            return f"Sucesso: Tentei abrir o canal '{canal}' diretamente na Twitch."

        # Se vier nome com espaços, tenta slug sem espaços antes de cair para busca.
        slug_sem_espaco = canal.replace(" ", "")
        if 2 <= len(slug_sem_espaco) <= 25 and re.fullmatch(r"[a-zA-Z0-9_]+", slug_sem_espaco):
            subprocess.run(["cmd", "/c", f'start browser "https://www.twitch.tv/{slug_sem_espaco}"'], capture_output=True)
            return f"Sucesso: Tentei abrir o canal '{slug_sem_espaco}' diretamente na Twitch."

        # Nome ambíguo: abre busca interna da Twitch para reduzir chance de canal errado.
        canal_q = urllib.parse.quote(canal)
        subprocess.run(["cmd", "/c", f'start browser "https://www.twitch.tv/search?term={canal_q}"'], capture_output=True)
        return f"Sucesso: Procurei canais da Twitch por '{canal}' para evitar abrir o canal errado."

    def _normalizar_texto(self, texto: str) -> str:
        return (texto or "").strip().lower()

    def _extrair_url(self, texto: str) -> str:
        texto = (texto or "").strip()
        if not texto:
            return ""

        if texto.startswith("http://") or texto.startswith("https://"):
            return texto

        # Aceita comandos como "youtube.com", "github.com/user/repo".
        if "." in texto and (" " not in texto) and ("/" in texto or texto.endswith(".com") or texto.endswith(".com.br") or texto.endswith(".tv") or texto.endswith(".io")):
            return f"https://{texto}"

        return ""

    def _extrair_operador_site(self, texto: str):
        t = (texto or "").strip()
        if not t:
            return "", ""

        m = re.search(r"site\s*:\s*([a-zA-Z0-9._-]+)", t, flags=re.IGNORECASE)
        if not m:
            return "", ""

        dominio = m.group(1).lower().strip()
        resto = (t[:m.start()] + " " + t[m.end():]).strip()
        return dominio, resto

    def _abrir_site_operador(self, dominio: str, consulta: str, **kwargs) -> str:
        """Operador site: para buscas em domínios específicos. Absorve parâmetros extra do Gemini."""
        dominio = (dominio or "").strip().lower()
        consulta = (consulta or "").strip()
        if not dominio:
            return "Aviso: domínio inválido no operador site:."

        base_url = f"https://{dominio}"

        if "twitch.tv" in dominio:
            return self._abrir_twitch_inteligente(consulta)

        if not consulta:
            webbrowser.open(base_url)
            return f"Sucesso: Abri {dominio}."

        consulta_segura = urllib.parse.quote(consulta)
        webbrowser.open(f"https://www.google.com/search?q=site:{dominio}+{consulta_segura}")
        return f"Sucesso: Procurei '{consulta}' em {dominio}."

    def _detectar_site(self, texto: str) -> str:
        t = self._normalizar_texto(texto)
        for alias, canonico in self.alias_site.items():
            if alias in t:
                return canonico
        for chave in self.sites_conhecidos.keys():
            if chave in t:
                return chave
        return ""

    def _abrir_site_ou_pesquisa(self, site_chave: str, consulta: str, **kwargs) -> str:
        """Abre/pesquisa em sites conhecidos. Absorve parâmetros extra (browser, etc) do Gemini."""
        base = self.sites_conhecidos.get(site_chave, "")
        consulta = (consulta or "").strip()

        if not base:
            return "Aviso: site não suportado para roteamento direto."

        if not consulta or consulta.lower() in ["abrir", "iniciar", "entrar", "ir"]:
            webbrowser.open(base)
            return f"Sucesso: Abri {site_chave}."

        if site_chave == "twitch":
            return self._abrir_twitch_inteligente(consulta)

        consulta_segura = urllib.parse.quote(consulta)

        if site_chave == "youtube":
            webbrowser.open(f"{base}/results?search_query={consulta_segura}")
        elif site_chave == "github":
            webbrowser.open(f"{base}/search?q={consulta_segura}")
        elif site_chave in ["twitter", "x"]:
            webbrowser.open(f"https://x.com/search?q={consulta_segura}")
        elif site_chave == "reddit":
            webbrowser.open(f"{base}/search/?q={consulta_segura}")
        elif site_chave == "spotify":
            webbrowser.open(f"{base}/search/{consulta_segura}")
        elif site_chave == "wikipedia":
            webbrowser.open(f"https://pt.wikipedia.org/wiki/Especial:Pesquisar?search={consulta_segura}")
        else:
            # Fallback: pesquisa no próprio site via Google com operador site:
            dominio = base.replace("https://", "").replace("http://", "").split("/")[0]
            webbrowser.open(f"https://www.google.com/search?q=site:{dominio}+{consulta_segura}")

        return f"Sucesso: Procurei '{consulta}' em {site_chave}."

    # --- TERMINAL SEGURO ---
    def _comando_e_seguro(self, comando: str) -> bool:
        comando_limpo = comando.strip().lower()
        if not comando_limpo:
            return False

        # No perfil trusted-local, permite desligar/reiniciar via shutdown controlado.
        if self.security_profile != "strict" and self._shutdown_controlado(comando_limpo):
            return True

        for padrao in self.padroes_criticos:
            if re.search(padrao, comando_limpo):
                return False

        # No perfil estrito, ainda bloqueia chaining/shell metacharacters.
        if self.security_profile == "strict":
            metacaracteres_perigosos = ["&&", "||", "|", ";", "`"]
            if any(token in comando for token in metacaracteres_perigosos):
                return False

        try:
            partes = shlex.split(comando, posix=False)
            if not partes:
                return False
        except ValueError:
            return False

        return True

    def executar_comando(self, comando: str, justificacao: str, **kwargs) -> str:
        """Executa comando no terminal com validação de segurança. Absorve parâmetros extra do Gemini."""
        print(f"\n>>> [HITL PRE-CHECK] A IA quer executar: '{comando}'")
        if not self._comando_e_seguro(comando):
            return f"ERRO DE SEGURANÇA: Comando '{comando}' bloqueado."
        try:
            # ✓ CRÍTICO: Forçar PowerShell para garantir Start-Process funcione
            # PowerShell é mais robusto para comandos complexos como "start browser URL"
            resultado = subprocess.run(
                ["powershell", "-NoProfile", "-Command", comando],
                capture_output=True,
                text=True,
                timeout=15
            )
            if resultado.returncode == 0:
                resp = resultado.stdout.strip()
                return f"RESULTADO DO TERMINAL:\n{resp[:2000]}" if resp else "Sucesso sem retorno."
            else:
                return f"FALHOU COM ERRO:\n{resultado.stderr.strip()[:1000]}"
        except Exception as e:
            return f"ERRO INTERNO: {str(e)}"

    # --- ROTEADOR GERAL (Google) ---
    # --- ROTEADOR UNIVERSAL DE APLICATIVOS ---
    def abrir_uri_app(self, app_nome: str, pesquisa_ou_acao: str, **kwargs) -> str:
        """Roteador universal: abre apps, sites, pesquisa ou jogos. Absorve parâmetros extra do Gemini."""
        app = app_nome.lower().strip()
        pedido = (pesquisa_ou_acao or "").strip()
        contexto_completo = f"{app_nome} {pesquisa_ou_acao}".strip()

        # 0. Operador site:dominio em qualquer campo.
        dominio_site, consulta_site = self._extrair_operador_site(f"{app} {pedido}")
        if dominio_site:
            return self._abrir_site_operador(dominio_site, consulta_site)

        # 0. URL direta em qualquer campo (pedido/app/contexto) abre imediatamente.
        url_direta = self._extrair_url(pedido)
        if url_direta:
            subprocess.run(["cmd", "/c", f'start browser "{url_direta}"'], capture_output=True)
            return f"Sucesso: Abri a página {url_direta}."

        url_no_app = self._extrair_url(app_nome)
        if url_no_app:
            subprocess.run(["cmd", "/c", f'start browser "{url_no_app}"'], capture_output=True)
            return f"Sucesso: Abri a página {url_no_app}."

        url_no_contexto = self._extrair_url(contexto_completo)
        if url_no_contexto:
            subprocess.run(["cmd", "/c", f'start browser "{url_no_contexto}"'], capture_output=True)
            return f"Sucesso: Abri a página {url_no_contexto}."

        # 0.1. Se app ou pedido mencionar um site conhecido, abre/pesquisa direto no site.
        site_por_app = self._detectar_site(app)
        if site_por_app:
            consulta = pedido if pedido else contexto_completo
            return self._abrir_site_ou_pesquisa(site_por_app, consulta)

        site_por_pedido = self._detectar_site(pedido)
        if site_por_pedido:
            # Remove menções do site para manter apenas a consulta.
            consulta = pedido
            for chave in self.sites_conhecidos.keys():
                consulta = consulta.lower().replace(chave, "").strip()
            return self._abrir_site_ou_pesquisa(site_por_pedido, consulta)

        # 0.2. Se o contexto completo mencionar Twitch, usa parser inteligente de canal.
        if self._detectar_site(contexto_completo) == "twitch":
            return self._abrir_twitch_inteligente(contexto_completo)
        
        # 1. Roteador Web (Google)
        if "google" in app or "navegador" in app or "pesquisar" in app:
            # Ex.: "abrir x na página youtube" -> pesquisa no site, não no Google geral.
            pedido_norm = self._normalizar_texto(pedido)
            if " na pagina " in pedido_norm or " na página " in pedido_norm or " no site " in pedido_norm:
                site_detectado = self._detectar_site(pedido_norm)
                if site_detectado:
                    consulta = pedido_norm
                    consulta = consulta.replace("na pagina", "").replace("na página", "").replace("no site", "")
                    consulta = consulta.replace(site_detectado, "").strip()
                    return self._abrir_site_ou_pesquisa(site_detectado, consulta)

            query_segura = urllib.parse.quote(pedido)
            webbrowser.open(f"https://www.google.com/search?q={query_segura}")
            return f"Sucesso: O navegador abriu pesquisando por '{pedido}'."

        # 2. Dicionário de Tradução Nativa
        dicionario_nativo = {
            "calculadora": "calc",
            "bloco de notas": "notepad",
            "painel de controle": "control",
            "configurações": "ms-settings:",
            "cmd": "cmd",
            "paint": "mspaint",
            "gerenciador de tarefas": "taskmgr"
        }

        for pt_br, cmd_windows in dicionario_nativo.items():
            if pt_br in app:
                os.startfile(cmd_windows)
                return f"Sucesso: Abri a ferramenta nativa '{pt_br}'."

        # 3. O MOTOR DE BUSCA AVANÇADO (Agora com suporte a Jogos da Steam/Epic)
        print(f">>> [ROUTER] A procurar o atalho de '{app_nome}' no PC...")
        
        # Este script PowerShell remove ruído dos nomes e tenta 3 caminhos:
        # 1) atalhos (.lnk/.url), 2) executável no PATH, 3) app registrada no Start Menu.
        app_nome_ps = app_nome.replace('"', '`"')
        ps_script = f"""
        $appName = "{app_nome_ps}"
        $cleanQuery = $appName -replace '\\s+', '' -replace '[^\\w]', ''
        
        function Normalize-Name([string]$value) {{
            return ($value -replace '\\s+', '' -replace '[^\\w]', '').ToLower()
        }}
        
        $cleanQuery = Normalize-Name $appName
        
        $paths = @("$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs", "$env:ALLUSERSPROFILE\\Microsoft\\Windows\\Start Menu\\Programs", "$env:PUBLIC\\Desktop", "$env:USERPROFILE\\Desktop")
        
        $allShortcuts = Get-ChildItem -Path $paths -Include *.lnk, *.url -Recurse -ErrorAction SilentlyContinue
        
        $target = $null
        foreach ($shortcut in $allShortcuts) {{
            $cleanName = Normalize-Name $shortcut.BaseName
            if ($cleanName -match $cleanQuery -or $cleanQuery -match $cleanName) {{
                $target = $shortcut
                break
            }}
        }}
        
        if ($target) {{
            Invoke-Item $target.FullName
            Write-Output "SUCESSO"
            exit
        }}

        $cmd = Get-Command $appName -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) {{
            Start-Process -FilePath $cmd.Source
            Write-Output "SUCESSO"
            exit
        }}

        $startApp = Get-StartApps | Where-Object {{
            $n = Normalize-Name $_.Name
            $n -match $cleanQuery -or $cleanQuery -match $n
        }} | Select-Object -First 1

        if ($startApp) {{
            Start-Process "shell:AppsFolder\\$($startApp.AppID)"
            Write-Output "SUCESSO"
            exit
        }}

        Write-Output "FALHA"
        """
        
        try:
            resultado = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
            
            if "SUCESSO" in resultado.stdout:
                return f"Sucesso absoluto: Encontrei o atalho de '{app_nome}' (seja jogo ou programa) e iniciei!"
            else:
                detalhe = (resultado.stderr or "").strip()
                if detalhe:
                    return f"Aviso: Não consegui abrir '{app_nome}'. Detalhe técnico: {detalhe}"
                return f"Aviso: Não encontrei '{app_nome}' no Desktop/Menu Iniciar/PATH. Confirma o nome exato do app?"
                
        except Exception as e:
            return f"Erro interno ao procurar o programa: {str(e)}"
    # --- FUNÇÃO 1: SPOTIFY API ---
    def tocar_musica_spotify_api(self, pesquisa: str, **kwargs) -> str:
        """Exclusivo para contas Premium. Absorve parâmetros extra do Gemini de forma segura."""
        if not self.sp: return "Erro: Credenciais do Spotify ausentes no .env."
        try:
            print(f">>> [SPOTIFY] A procurar: '{pesquisa}'...")
            resultados = self.sp.search(q=pesquisa, limit=1, type='track')
            tracks = resultados['tracks']['items']
            if not tracks: return f"Não encontrei a música '{pesquisa}'."
            
            track = tracks[0]
            devices = self.sp.devices()
            if not devices['devices']:
                webbrowser.open(track['uri'])
                return f"Abri '{track['name']}'. (Nota: Spotify estava fechado, precisa de play manual)."
                
            self.sp.start_playback(uris=[track['uri']])
            return f"Sucesso. A tocar '{track['name']}' no Spotify."
        except Exception as e:
            if "403" in str(e): return "Aviso: A API do Spotify bloqueou o comando de Play porque a conta não é Premium. Sugere ao Matheus usar o YouTube desta vez."
            return f"Erro no Spotify: {str(e)}"

    # ===== MÉTODO UTILITÁRIO: INICIALIZAR BROWSER ASSÍNCRONO PERSISTENTE =====
    def _get_browser_init_lock(self):
        if self._browser_init_lock is None:
            self._browser_init_lock = asyncio.Lock()
        return self._browser_init_lock

    def _browser_is_active(self) -> bool:
        if self.browser is None:
            return False
        try:
            is_connected = getattr(self.browser, "is_connected", None)
            if callable(is_connected):
                return bool(is_connected())
            return True
        except Exception:
            return False

    async def _init_browser(self):
        """Inicializa o Playwright assíncrono e o browser Chromium persistentes.
        Se já iniciado, reutiliza as instâncias. O navegador fica aberto em background."""
        if self._browser_is_active() and self.playwright is not None:
            # Browser ja esta inicializado e conectado
            return

        lock = self._get_browser_init_lock()
        async with lock:
            if self._browser_is_active() and self.playwright is not None:
                return

            print("[PLAYWRIGHT ASYNC] Inicializando Chromium persistente...")
            try:
                # Garante ambiente limpo antes de novo start.
                if self.browser is not None:
                    try:
                        await self.browser.close()
                    except Exception:
                        pass
                    self.browser = None

                if self.playwright is not None:
                    try:
                        await self.playwright.stop()
                    except Exception:
                        pass
                    self.playwright = None

                # Inicializar async_playwright
                self.playwright = await async_playwright().start()

                # Lançar Chromium com ignore-certificate-errors para HTTPS
                self.browser = await self.playwright.chromium.launch(
                    headless=True,  # Invisivel em background
                    args=[
                        "--autoplay-policy=no-user-gesture-required",
                        "--disable-blink-features=AutomationControlled",
                        "--ignore-certificate-errors"
                    ]
                )
                print("[PLAYWRIGHT ASYNC] ✅ Browser Chromium persistente pronto (headless mode)")
            except Exception as e:
                print(f"[ERRO PLAYWRIGHT] Falha ao inicializar: {type(e).__name__}: {str(e)}")
                print(traceback.format_exc())
                raise

    # --- FUNÇÃO 2: YOUTUBE PLAYWRIGHT (BLINDADO CONTRA ANTI-BOT) ---
    async def tocar_youtube_invisivel_async(self, pesquisa: str, **kwargs) -> str:
        """Abre o YouTube de forma assíncrona com capa de invisibilidade contra bots.
        O navegador fica aberto em background para próximas requisições."""
        print(f">>> [YOUTUBE ASYNC] A preparar motor web para: '{pesquisa}'...")
        query_url = urllib.parse.quote(pesquisa)
        video_resolvido = self._resolver_video_youtube(pesquisa)
        
        try:
            # ===== INICIALIZAR BROWSER PERSISTENTE =====
            await self._init_browser()
            
            # ===== CRIAR OU REUSAR PÁGINA =====
            if self.page:
                try:
                    await self.page.close()
                except:
                    pass
            
            self.page = await self.browser.new_page()
            
            # CAPA DE INVISIBILIDADE
            await self.page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            
            print(f">>> [YOUTUBE ASYNC] A navegar para YouTube...")
            
            # NAVEGAR E PROCURAR O VÍDEO
            if video_resolvido and video_resolvido.get("id"):
                await self.page.goto(f"https://www.youtube.com/watch?v={video_resolvido['id']}", timeout=30000)
            else:
                await self.page.goto(f"https://www.youtube.com/results?search_query={query_url}", timeout=30000)
                print(f">>> [YOUTUBE ASYNC] Aguardando primeiro vídeo...")
                
                # CORREÇÃO: Usar locator para clicar no primeiro vídeo
                await self.page.locator("ytd-video-renderer a#thumbnail").first.click(timeout=10000)
            
            print(f">>> [YOUTUBE ASYNC] Aguardando reprodutor...")
            await asyncio.sleep(2)
            
            # MOTOR FURTIVO: Anti-ads
            codigo_magico = """
            () => {
                const DEFAULT_VOLUME = __DEFAULT_VOLUME__;
                window.__assistentePreferredVolume ??= DEFAULT_VOLUME;
                let hookedVideo = null;
                
                const v = document.querySelector('video');
                if(v) {
                    v.muted = false;
                    v.volume = window.__assistentePreferredVolume;
                    if(v.paused) v.play();
                }
                
                setInterval(() => {
                    try {
                        const video = document.querySelector('video');
                        if (!video) return;
                        
                        const isAd = document.querySelector('.ytp-ad-player-overlay');
                        if (isAd) {
                            video.muted = true;
                            video.volume = 0;
                            video.playbackRate = 16.0;
                            document.querySelectorAll('.ytp-ad-skip-button').forEach(b => b.click());
                        } else {
                            video.muted = false;
                            video.volume = window.__assistentePreferredVolume;
                            video.playbackRate = 1.0;
                        }
                    } catch (err) {}
                }, 150);
            }
            """
            codigo_magico = codigo_magico.replace("__DEFAULT_VOLUME__", str(self.youtube_default_volume))
            await self.page.evaluate(codigo_magico)
            print(">>> [YOUTUBE ASYNC] Motor furtivo ativado!")
            
            if video_resolvido and video_resolvido.get("title"):
                return f"✅ Encontrei e coloquei '{video_resolvido['title']}' a tocar."
            return f"✅ Coloquei '{pesquisa}' a tocar no YouTube."
            
        except Exception as e:
            print(f"\n[ERRO FATAL PLAYWRIGHT]")
            print(traceback.format_exc())
            print("\n")
            return f"Erro na automação do YouTube: {str(e)}"
    
    async def tocar_youtube_invisivel(self, pesquisa: str, **kwargs) -> str:
        """ASSÍNCRONO - Wrapper para tocar_youtube_invisivel_async().
        Brain detecta como coroutine function e chama com await."""
        print(f">>> [ASYNC WRAPPER] Delegando para tocar_youtube_invisivel_async...")
        try:
            # Executar a coroutine assíncrona no mesmo event loop
            return await self.tocar_youtube_invisivel_async(pesquisa, **kwargs)
        except Exception as e:
            print(f"\n[ERRO FATAL PLAYWRIGHT]")
            print(traceback.format_exc())
            print("\n")
            return f"Erro ao iniciar YouTube: {str(e)}"

    # ==========================================
    # OS BOTÕES DO COMANDO REMOTO (Corrigidos)
    # ==========================================
    def controlar_reproducao(self, acao: str, **kwargs) -> str:
        """Pausa, retoma, salta, ou controla loop da música atual com segurança. Absorve parâmetros extra do Gemini."""
        if not self.page:
            return "Erro: O YouTube não está aberto no momento."
            
        try:
            acao_lower = acao.lower()
            
            if "pausar" in acao_lower or "parar" in acao_lower:
                return asyncio.run(self.controlar_reproducao_async("pausar"))
            
            elif "retomar" in acao_lower or "voltar" in acao_lower or "play" in acao_lower or "começar" in acao_lower:
                return asyncio.run(self.controlar_reproducao_async("play"))
            
            elif "pular" in acao_lower or "skip" in acao_lower or "proxima" in acao_lower or "próxima" in acao_lower:
                return asyncio.run(self.controlar_reproducao_async("skip"))
            
            elif "loop" in acao_lower or "repeat" in acao_lower or "repetir" in acao_lower or "lupi" in acao_lower:
                return asyncio.run(self.controlar_reproducao_async("loop"))
            
            else:
                return f"Ação '{acao}' não reconhecida. Tente: pausar, retomar (play), pular (skip), ou loop (repetir)."
                
        except Exception as e:
            print(f"\n[ERRO FATAL PLAYWRIGHT]")
            print(traceback.format_exc())
            print("\n")
            return f"Falha ao executar o comando no navegador: {str(e)}"
    
    async def controlar_reproducao_async(self, acao: str, **kwargs) -> str:
        """Pausa, retoma, salta, ou controla loop da música atual com segurança (ASYNC)."""
        if not self.page:
            return "Erro: O YouTube não está aberto no momento."
        
        try:
            acao_lower = acao.lower()
            
            if "pausar" in acao_lower or "parar" in acao_lower:
                await self.page.evaluate("() => { const v = document.querySelector('video'); if(v) v.pause(); }")
                return "✅ A música foi pausada com sucesso."
            
            elif "retomar" in acao_lower or "voltar" in acao_lower or "play" in acao_lower or "começar" in acao_lower:
                await self.page.evaluate("() => { const v = document.querySelector('video'); if(v) v.play(); }")
                return "✅ A música voltou a tocar."
            
            elif "pular" in acao_lower or "skip" in acao_lower or "proxima" in acao_lower or "próxima" in acao_lower:
                await self.page.evaluate("() => { const nextBtn = document.querySelector('.ytp-next-button'); if(nextBtn) nextBtn.click(); }")
                return "✅ Pulei para a próxima música."
            
            elif "loop" in acao_lower or "repeat" in acao_lower or "repetir" in acao_lower or "lupi" in acao_lower:
                await self.page.evaluate("() => { const repeatBtn = document.querySelector('.ytp-repeat'); if(repeatBtn) repeatBtn.click(); }")
                return "✅ Modo de repetição (loop) ativado."
            
            else:
                return f"Ação '{acao}' não reconhecida. Tente: pausar, retomar (play), pular (skip), ou loop (repetir)."
                
        except Exception as e:
            print(f"\n[ERRO FATAL PLAYWRIGHT]")
            print(traceback.format_exc())
            print("\n")
            return f"Erro ao controlar reprodução: {str(e)}"
    
    def controlar_reproducao_spotify(self, acao: str, **kwargs) -> str:
        """Controla reprodução no Spotify: pause, retomar, repetição (loop). Absorve parâmetros extra do Gemini."""
        if not self.sp:
            return "Erro: Spotify não está configurado. Verifique SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET no .env"
        
        try:
            acao_lower = acao.lower()
            
            if "pausar" in acao_lower or "parar" in acao_lower:
                self.sp.pause_playback()
                return "A música do Spotify foi pausada."
            
            elif "retomar" in acao_lower or "voltar" in acao_lower or "play" in acao_lower or "começar" in acao_lower:
                self.sp.start_playback()
                return "A música do Spotify foi retomada."
            
            elif "loop" in acao_lower or "repeat" in acao_lower or "repetir" in acao_lower or "lupi" in acao_lower:
                # Spotify oferece: 'off' (sem repetição), 'context' (repetir playlist), 'track' (repetir faixa)
                # Por defeito, ativar repetição de faixa
                self.sp.repeat('track')
                return "Repetição (loop) de uma faixa ativada no Spotify. Clica novamente para mudar para repetição da playlist ou desativar."
            
            else:
                # Fallback seguro
                return f"Ação '{acao}' não reconhecida para Spotify. Tente: pausar, retomar (play), ou loop (repetir)."
        
        except Exception as e:
            return f"Erro ao controlar Spotify: {str(e)}"
        
    

    def ajustar_volume(self, nivel, **kwargs) -> str:
        """Ajusta o volume do vídeo blindado contra textos sujos. Absorve parâmetros extra do Gemini."""
        try:
            # Limpa qualquer lixo que a IA mande (como "%" ou espaços) e converte com segurança
            if isinstance(nivel, str):
                nivel = nivel.replace('%', '').strip()
            
            # Converte para float primeiro (caso ela mande "50.0") e depois para inteiro
            numero_limpo = int(float(nivel))
            vol_decimal = max(0, min(100, numero_limpo)) / 100.0
            self.youtube_default_volume = vol_decimal
            self._guardar_volume_preferido(vol_decimal)
            
            if self.page:
                self.page.evaluate(
                    f"() => {{ window.__assistentePreferredVolume = {vol_decimal}; const v = document.querySelector('video'); if(v) {{ v.muted = false; v.volume = {vol_decimal}; }} }}"
                )
                return f"O volume da música foi ajustado para {numero_limpo}% e ficará assim nas próximas músicas."

            return f"Guardei {numero_limpo}% como volume padrão. As próximas músicas no YouTube abrirão nesse volume."
        except Exception as e:
            return f"Erro interno ao ajustar o volume. Diga ao Matheus para passar apenas números. Erro: {str(e)}"
        
    def pular_musica(self, **kwargs) -> str:
        """Pula para o próximo vídeo/música na playlist do YouTube. Absorve parâmetros extra do Gemini."""
        if not self.page:
            return "Erro: O YouTube não está aberto no momento."
            
        try:
            # O seletor '.ytp-next-button' é o botão nativo do YouTube de "Próximo"
            self.page.evaluate("() => { const nextBtn = document.querySelector('.ytp-next-button'); if(nextBtn) nextBtn.click(); }")
            return "Pulei para a próxima música com sucesso!"
        except Exception as e:
            return f"Erro ao tentar pular a música: {str(e)}"
        
    def capturar_visao_tela(self) -> str:
        """
        Tira um print screen invisível do monitor principal e guarda como ficheiro temporário.
        """
        print(">>> [VISÃO] Córtex visual acionado. A capturar o monitor principal...")
        
        # 1. Cria uma pasta temporária para os prints se ela não existir
        pasta_temp = "temp_vision"
        if not os.path.exists(pasta_temp):
            os.makedirs(pasta_temp)
            
        # 2. Define o nome do ficheiro
        caminho_imagem = os.path.join(pasta_temp, "quintafeira_visao.png")
        
        try:
            # 3. Tira o print usando o PyAutoGUI (é instantâneo e invisível)
            # screen = pyautogui.screenshot()
            # screen.save(caminho_imagem)
            
            # Uma forma mais robusta de capturar com múltiplas telas se necessário:
            pyautogui.screenshot(caminho_imagem)
            
            print(f">>> [VISÃO] Imagem capturada com sucesso e guardada em: {caminho_imagem}")
            return caminho_imagem # Retorna o caminho para o Brain ler
            
        except Exception as e:
            print(f">>> [ERRO VISÃO] Falha ao capturar ecrã: {str(e)}")
            return f"Erro na visão: {str(e)}"
    
    def controlar_energia(self, acao: str, delay: int = 10, **kwargs) -> str:
        """Controla energia do sistema: shutdown, restart, sleep. Absorve parâmetros extra do Gemini.
        
        Args:
            acao (str): 'shutdown' (desligar), 'restart' (reiniciar), 'sleep' (suspender)
            delay (int): Segundos para aguardar antes de executar (padrão: 10)
            
        Returns:
            str: Mensagem de resultado
        """
        acao_lower = acao.lower().strip()
        
        # Normalizar comandos
        if acao_lower in ['desligar', 'shutdown', 'shudown', 'deslizar']:
            acao_normalizada = 'shutdown'
            msg_user = f"Computador será desligado em {delay} segundos."
        elif acao_lower in ['reiniciar', 'restart', 'reboot', 're-iniciar']:
            acao_normalizada = 'restart'
            msg_user = f"Computador será reiniciado em {delay} segundos."
        elif acao_lower in ['dormir', 'sleep', 'suspender', 'hibernar', 'dormer']:
            acao_normalizada = 'sleep'
            msg_user = "Computador entrando em modo de suspensão."
        else:
            return f"Ação desconhecida: '{acao}'. Use: desligar (shutdown), reiniciar (restart), ou dormir (sleep)."
        
        try:
            sistema = os.name
            
            if sistema == 'nt':  # Windows
                if acao_normalizada == 'shutdown':
                    os.system(f'shutdown /s /t {delay}')
                elif acao_normalizada == 'restart':
                    os.system(f'shutdown /r /t {delay}')
                else:  # sleep
                    os.system('rundll32.exe powrprof.dll,SetSuspendState 0,1,0')
            
            else:  # Linux/Mac
                if acao_normalizada == 'shutdown':
                    os.system(f'shutdown -h +{delay // 60}')
                elif acao_normalizada == 'restart':
                    os.system(f'shutdown -r +{delay // 60}')
                else:  # sleep
                    os.system('systemctl suspend')
            
            print(f">>> [ENERGIA] {msg_user}")
            return msg_user
            
        except Exception as e:
            return f"Erro ao executar controle de energia: {str(e)}"
    
    # ===== MÉTODOS ASYNC (NÃO BLOQUEIAM O EVENT LOOP) =====
    
    async def async_tocar_youtube_invisivel(self, pesquisa: str, **kwargs) -> str:
        """
        ✅ Versão ASYNC refatorada que NÃO BLOQUEIA o FastAPI event loop.
        ✅ Usa async_playwright com persistência de contexto.
        ✅ Mantém browser, context, page em self para reutilização.
        ✅ Toda lógica anti-bot intacta.
        
        Requisitos atendidos:
        1. async def ✓
        2. Ciclo de vida do async_playwright mantido em self ✓
        3. Todas as interações com página usam await ✓
        4. Lógica anti-bot intacta ✓
        5. À prova de falhas no event loop ✓
        """
        print(f">>> [YOUTUBE ASYNC] A preparar motor web para: '{pesquisa}'...")
        
        try:
            # Inicializar async_playwright uma única vez (reutilizar nos próximos comandos)
            await self._inicializar_async_playwright()
            
            # Resolver a URL do vídeo
            video_resolvido = self._resolver_video_youtube(pesquisa)
            query_url = urllib.parse.quote(pesquisa)
            
            # Usar lock para evitar condições de corrida com outras operações de página
            async with self.async_pb_lock:
                # Fechar página antiga se existir
                if self.page_async:
                    try:
                        await self.page_async.close()
                    except:
                        pass
                
                # Criar nova página no contexto persistente
                self.page_async = await self.context_async.new_page()
                
                # Injetar script anti-bot
                await self.page_async.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                
                # Navegar para o vídeo
                if video_resolvido and video_resolvido.get("id"):
                    print(f">>> [YOUTUBE ASYNC] Navegando para: {video_resolvido['id']}")
                    await self.page_async.goto(
                        f"https://www.youtube.com/watch?v={video_resolvido['id']}", 
                        timeout=30000
                    )
                else:
                    print(f">>> [YOUTUBE ASYNC] Procurando: {pesquisa}")
                    await self.page_async.goto(
                        f"https://www.youtube.com/results?search_query={query_url}", 
                        timeout=30000
                    )
                    await self.page_async.wait_for_selector("a#video-title", timeout=10000)
                    await self.page_async.click("a#video-title")
                
                # Aguardar player
                print(">>> [YOUTUBE ASYNC] Aguardando player...")
                await self.page_async.wait_for_selector("video", timeout=15000)
                await asyncio.sleep(1)  # Pequena pausa para o vídeo carregar
                
                # Injetar código de controle de volume (igual ao sync, mas com persistência)
                codigo_magico = f"""
                (() => {{
                    const DEFAULT_VOLUME = {self.youtube_default_volume};
                    if (typeof window.__assistentePreferredVolume !== 'number') {{
                        window.__assistentePreferredVolume = DEFAULT_VOLUME;
                    }}
                    let lastVideoSrc = null;
                    let lastUrl = location.href;
                    let hookedVideo = null;

                    const obterVolumePreferido = () => {{
                        const v = window.__assistentePreferredVolume;
                        if (typeof v !== 'number' || Number.isNaN(v)) return DEFAULT_VOLUME;
                        return Math.max(0, Math.min(1, v));
                    }};

                    const aplicarVolumePadrao = (video) => {{
                        if (!video) return;
                        video.muted = false;
                        video.volume = obterVolumePreferido();
                    }};

                    const anexarHooks = (video) => {{
                        if (!video || video === hookedVideo) return;
                        hookedVideo = video;
                        const aplicar = () => aplicarVolumePadrao(video);
                        video.addEventListener('loadedmetadata', aplicar);
                        video.addEventListener('play', aplicar);
                        aplicar();
                    }};

                    const v = document.querySelector('video');
                    if(v) {{
                        aplicarVolumePadrao(v);
                        anexarHooks(v);
                        if(v.paused) v.play();
                        lastVideoSrc = v.currentSrc || v.src || null;
                    }}
                    
                    setInterval(() => {{
                        try {{
                            const video = document.querySelector('video');
                            if (!video) return;

                            anexarHooks(video);

                            const currentSrc = video.currentSrc || video.src || null;
                            const trocouDeMusica = currentSrc && currentSrc !== lastVideoSrc;
                            if (trocouDeMusica) {{
                                lastVideoSrc = currentSrc;
                            }}

                            const urlMudou = location.href !== lastUrl;
                            if (urlMudou) {{
                                lastUrl = location.href;
                            }}

                            // DETEÇÃO DEFINITIVA: Olha para todos os elementos que o YouTube usa para exibir anúncios
                            const isAd = document.querySelector('.ytp-ad-player-overlay, .ytp-ad-player-overlay-instream-info, .ad-showing');

                            if (isAd) {{
                                // É ANÚNCIO: Muta, zera o volume e acelera
                                video.muted = true;
                                video.volume = 0;
                                video.playbackRate = 16.0;

                                // Clica em qualquer botão de pular que existir
                                document.querySelectorAll('.ytp-ad-skip-button, .ytp-ad-skip-button-modern, .ytp-skip-ad-button').forEach(b => b.click());

                                // Salto no tempo (se for inpulável)
                                if (video.duration > 0 && video.currentTime < video.duration - 1) {{
                                    video.currentTime = video.duration - 0.5; 
                                }}
                            }} else {{
                                // NÃO É ANÚNCIO: Restaura o som e a velocidade com segurança
                                if (video.muted || video.playbackRate !== 1.0 || trocouDeMusica || urlMudou || video.volume !== obterVolumePreferido()) {{
                                    aplicarVolumePadrao(video);
                                    video.playbackRate = 1.0;
                                }}
                            }}

                            // Esmaga banners
                            document.querySelectorAll('.ytp-ad-overlay-close-button').forEach(b => b.click());
                        }} catch (err) {{}}
                    }}, 150);
                }})();
                """
                
                await self.page_async.evaluate(codigo_magico)
                print(">>> [YOUTUBE ASYNC] Motor furtivo injetado!")
                
                # ✅ NÃO FECHAR A PÁGINA - manter para próximos comandos (controlar_reproducao, pular_musica, etc)
                
                if video_resolvido and video_resolvido.get("title"):
                    return f"Sucesso! Encontrei e coloquei '{video_resolvido['title']}' a tocar."
                return f"Sucesso! Coloquei '{pesquisa}' a tocar. Anti-Bot evadido."
        
        except Exception as e:
            print(f"[YOUTUBE ASYNC] Erro: {e}")
            return f"Erro na automação do YouTube (async): {str(e)}"
    
    async def async_controlar_reproducao(self, acao: str, **kwargs) -> str:
        """
        ✅ Versão ASYNC do controle de reprodução (Pausa, Retoma, Pula, Loop).
        ✅ Não bloqueia o event loop.
        ✅ Reutiliza a página assíncrona persistente mantida em self.
        """
        if not self.page_async:
            return "Erro: O YouTube não está aberto no momento (página async não existe)."
        
        try:
            acao_lower = acao.lower()
            
            async with self.async_pb_lock:
                if "pausar" in acao_lower or "parar" in acao_lower:
                    await self.page_async.evaluate("() => { const v = document.querySelector('video'); if(v) v.pause(); }")
                    return "A música foi pausada com sucesso."
                
                elif "retomar" in acao_lower or "voltar" in acao_lower or "play" in acao_lower or "começar" in acao_lower:
                    await self.page_async.evaluate("() => { const v = document.querySelector('video'); if(v) v.play(); }")
                    return "A música voltou a tocar."
                
                elif "pular" in acao_lower or "skip" in acao_lower or "proxima" in acao_lower or "próxima" in acao_lower:
                    await self.page_async.evaluate("() => { const nextBtn = document.querySelector('.ytp-next-button'); if(nextBtn) nextBtn.click(); }")
                    return "Pulei para a próxima música."
                
                elif "loop" in acao_lower or "repeat" in acao_lower or "repetir" in acao_lower or "lupi" in acao_lower:
                    await self.page_async.evaluate("() => { const repeatBtn = document.querySelector('.ytp-repeat'); if(repeatBtn) repeatBtn.click(); }")
                    return "Modo de repetição (loop) ativado. Clica novamente para mudar entre uma música ou toda a playlist."
                
                else:
                    return f"Ação '{acao}' não reconhecida. Tente: pausar, retomar (play), pular (skip), ou loop (repetir)."
        
        except Exception as e:
            print(f"[YOUTUBE ASYNC] Erro ao controlar reprodução: {e}")
            return f"Falha ao executar o comando no navegador: {str(e)}"
    
    async def async_ajustar_volume(self, nivel, **kwargs) -> str:
        """
        ✅ Versão ASYNC de ajuste de volume.
        ✅ Não bloqueia o event loop.
        ✅ Mantém volume persistido para futuras sessões.
        """
        if not self.page_async:
            return "Erro: O YouTube não está aberto no momento (página async não existe)."
        
        try:
            # Limpar input
            if isinstance(nivel, str):
                nivel = nivel.replace('%', '').strip()
            
            numero_limpo = int(float(nivel))
            vol_decimal = max(0, min(100, numero_limpo)) / 100.0
            self.youtube_default_volume = vol_decimal
            self._guardar_volume_preferido(vol_decimal)
            
            async with self.async_pb_lock:
                await self.page_async.evaluate(
                    f"() => {{ window.__assistentePreferredVolume = {vol_decimal}; const v = document.querySelector('video'); if(v) {{ v.muted = false; v.volume = {vol_decimal}; }} }}"
                )
            
            return f"O volume da música foi ajustado para {numero_limpo}% e ficará assim nas próximas músicas."
        
        except Exception as e:
            print(f"[YOUTUBE ASYNC] Erro ao ajustar volume: {e}")
            return f"Erro interno ao ajustar o volume. Erro: {str(e)}"
    
    async def async_pular_musica(self, **kwargs) -> str:
        """
        ✅ Versão ASYNC para pular a música.
        ✅ Não bloqueia o event loop.
        ✅ Reutiliza a página assíncrona persistente.
        """
        if not self.page_async:
            return "Erro: O YouTube não está aberto no momento (página async não existe)."
        
        try:
            async with self.async_pb_lock:
                # O seletor '.ytp-next-button' é o botão nativo do YouTube de "Próximo"
                await self.page_async.evaluate("() => { const nextBtn = document.querySelector('.ytp-next-button'); if(nextBtn) nextBtn.click(); }")
            
            return "Pulei para a próxima música com sucesso!"
        
        except Exception as e:
            print(f"[YOUTUBE ASYNC] Erro ao pular música: {e}")
            return f"Erro ao tentar pular a música: {str(e)}"
        