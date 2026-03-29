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
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from youtubesearchpython import VideosSearch
from playwright.sync_api import sync_playwright

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

        # --- MOTOR YOUTUBE (Playwright) ---
        self.playwright_ativo = False
        self.pw_motor = None
        self.browser_instance = None
        self.context = None  # ✓ NOVO: Context singleton
        self.page = None
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
        """Destrutor: Cleanup de recursos ao destruir objeto"""
        try:
            self._cleanup_playwright()
        except:
            pass
    
    def _cleanup_playwright(self):
        """Cleanup rigoroso de recursos Playwright"""
        try:
            print("[CLEANUP] Fechando recursos Playwright...")
            
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
            print("[CLEANUP] ✓ Recurso Playwright encerrado com sucesso")
        except Exception as e:
            print(f"[CLEANUP] Erro ao encerrar: {e}")

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
                resultados = VideosSearch(tentativa, limit=3).result()
                videos = resultados.get("result", [])
                if videos:
                    return {
                        "id": videos[0].get("id", ""),
                        "title": videos[0].get("title", ""),
                        "query": tentativa,
                    }
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

    def _abrir_twitch_inteligente(self, consulta: str) -> str:
        canal = self._extrair_canal_twitch(consulta)
        if not canal:
            webbrowser.open("https://www.twitch.tv/directory")
            return "Sucesso: Abri a Twitch na página de descoberta."

        # Se for um único token, tenta canal direto.
        if " " not in canal and 2 <= len(canal) <= 25:
            webbrowser.open(f"https://www.twitch.tv/{canal}")
            return f"Sucesso: Tentei abrir o canal '{canal}' diretamente na Twitch."

        # Se vier nome com espaços, tenta slug sem espaços antes de cair para busca.
        slug_sem_espaco = canal.replace(" ", "")
        if 2 <= len(slug_sem_espaco) <= 25 and re.fullmatch(r"[a-zA-Z0-9_]+", slug_sem_espaco):
            webbrowser.open(f"https://www.twitch.tv/{slug_sem_espaco}")
            return f"Sucesso: Tentei abrir o canal '{slug_sem_espaco}' diretamente na Twitch."

        # Nome ambíguo: abre busca interna da Twitch para reduzir chance de canal errado.
        canal_q = urllib.parse.quote(canal)
        webbrowser.open(f"https://www.twitch.tv/search?term={canal_q}")
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

    def _abrir_site_operador(self, dominio: str, consulta: str) -> str:
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

    def _abrir_site_ou_pesquisa(self, site_chave: str, consulta: str) -> str:
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

    def executar_comando(self, comando: str, justificacao: str) -> str:
        print(f"\n>>> [HITL PRE-CHECK] A IA quer executar: '{comando}'")
        if not self._comando_e_seguro(comando):
            return f"ERRO DE SEGURANÇA: Comando '{comando}' bloqueado."
        try:
            execucao = shlex.split(comando, posix=False)
            resultado = subprocess.run(execucao, shell=False, capture_output=True, text=True, timeout=15)
            if resultado.returncode == 0:
                resp = resultado.stdout.strip()
                return f"RESULTADO DO TERMINAL:\n{resp[:2000]}" if resp else "Sucesso sem retorno."
            else:
                return f"FALHOU COM ERRO:\n{resultado.stderr.strip()[:1000]}"
        except Exception as e:
            return f"ERRO INTERNO: {str(e)}"

    # --- ROTEADOR GERAL (Google) ---
    # --- ROTEADOR UNIVERSAL DE APLICATIVOS ---
    def abrir_uri_app(self, app_nome: str, pesquisa_ou_acao: str) -> str:
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
            webbrowser.open(url_direta)
            return f"Sucesso: Abri a página {url_direta}."

        url_no_app = self._extrair_url(app_nome)
        if url_no_app:
            webbrowser.open(url_no_app)
            return f"Sucesso: Abri a página {url_no_app}."

        url_no_contexto = self._extrair_url(contexto_completo)
        if url_no_contexto:
            webbrowser.open(url_no_contexto)
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
    def tocar_musica_spotify_api(self, pesquisa: str) -> str:
        """Exclusivo para contas Premium."""
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

    # --- FUNÇÃO 2: YOUTUBE PLAYWRIGHT ---
   # --- FUNÇÃO 2: YOUTUBE PLAYWRIGHT (BLINDADO CONTRA ANTI-BOT) ---
    def tocar_youtube_invisivel(self, pesquisa: str) -> str:
        """Abre o YouTube com capa de invisibilidade contra bots e pula anúncios silenciosamente."""
        print(f">>> [YOUTUBE] A preparar motor web para: '{pesquisa}'...")
        query_url = urllib.parse.quote(pesquisa)
        video_resolvido = self._resolver_video_youtube(pesquisa)
        
        try:
            # ===== SINGLETON RIGOROSO - Context Reutilizável =====
            if not self.playwright_ativo:
                print("[PLAYWRIGHT] Inicializando Playwright (singleton)...")
                self.pw_motor = sync_playwright().start()
                self.browser_instance = self.pw_motor.chromium.launch(
                    headless=False,
                    channel="msedge", 
                    args=[
                        "--autoplay-policy=no-user-gesture-required",
                        "--window-position=-32000,-32000",
                        "--window-size=800,600",
                        "--disable-blink-features=AutomationControlled"
                    ]
                )
                # ✓ NOVO: Guardar context em self (aplicação única e reutilizável)
                self.context = self.browser_instance.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                self.playwright_ativo = True
                print("[PLAYWRIGHT] ✓ Context singleton criado (reutilizável)")
            
            # ===== REUTILIZAR CONTEXT - Fechar página antiga, criar nova =====
            if self.page:
                try:
                    self.page.close()
                except:
                    pass
            
            # ✓ NOVO: Criar página no MESMO context (não novo context!)
            self.page = self.context.new_page()
            
            # A CAPA DE INVISIBILIDADE: Esconde o facto de sermos um script
            self.page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            print(">>> [PLAYWRIGHT] A navegar e procurar o vídeo...")
            if video_resolvido and video_resolvido.get("id"):
                self.page.goto(f"https://www.youtube.com/watch?v={video_resolvido['id']}")
            else:
                self.page.goto(f"https://www.youtube.com/results?search_query={query_url}")
                self.page.wait_for_selector("a#video-title")
                self.page.click("a#video-title")
            
            print(">>> [PLAYWRIGHT] A aguardar o player...")
            self.page.wait_for_selector("video", timeout=15000)
            time.sleep(2) 
            
            codigo_magico = """
            () => {
                const DEFAULT_VOLUME = __DEFAULT_VOLUME__;
                if (typeof window.__assistentePreferredVolume !== 'number') {
                    window.__assistentePreferredVolume = DEFAULT_VOLUME;
                }
                let lastVideoSrc = null;
                let lastUrl = location.href;
                let hookedVideo = null;

                const obterVolumePreferido = () => {
                    const v = window.__assistentePreferredVolume;
                    if (typeof v !== 'number' || Number.isNaN(v)) return DEFAULT_VOLUME;
                    return Math.max(0, Math.min(1, v));
                };

                const aplicarVolumePadrao = (video) => {
                    if (!video) return;
                    video.muted = false;
                    video.volume = obterVolumePreferido();
                };

                const anexarHooks = (video) => {
                    if (!video || video === hookedVideo) return;
                    hookedVideo = video;
                    const aplicar = () => aplicarVolumePadrao(video);
                    video.addEventListener('loadedmetadata', aplicar);
                    video.addEventListener('play', aplicar);
                    aplicar();
                };

                const v = document.querySelector('video');
                if(v) {
                    aplicarVolumePadrao(v);
                    anexarHooks(v);
                    if(v.paused) v.play();
                    lastVideoSrc = v.currentSrc || v.src || null;
                }
                
                setInterval(() => {
                    try {
                        const video = document.querySelector('video');
                        if (!video) return;

                        anexarHooks(video);

                        const currentSrc = video.currentSrc || video.src || null;
                        const trocouDeMusica = currentSrc && currentSrc !== lastVideoSrc;
                        if (trocouDeMusica) {
                            lastVideoSrc = currentSrc;
                        }

                        const urlMudou = location.href !== lastUrl;
                        if (urlMudou) {
                            lastUrl = location.href;
                        }

                        // DETEÇÃO DEFINITIVA: Olha para todos os elementos que o YouTube usa para exibir anúncios
                        const isAd = document.querySelector('.ytp-ad-player-overlay, .ytp-ad-player-overlay-instream-info, .ad-showing');

                        if (isAd) {
                            // É ANÚNCIO: Muta, zera o volume e acelera
                            video.muted = true;
                            video.volume = 0;
                            video.playbackRate = 16.0;

                            // Clica em qualquer botão de pular que existir
                            document.querySelectorAll('.ytp-ad-skip-button, .ytp-ad-skip-button-modern, .ytp-skip-ad-button').forEach(b => b.click());

                            // Salto no tempo (se for inpulável)
                            if (video.duration > 0 && video.currentTime < video.duration - 1) {
                                video.currentTime = video.duration - 0.5; 
                            }
                        } else {
                            // NÃO É ANÚNCIO: Restaura o som e a velocidade com segurança
                            if (video.muted || video.playbackRate !== 1.0 || trocouDeMusica || urlMudou || video.volume !== obterVolumePreferido()) {
                                aplicarVolumePadrao(video);
                                video.playbackRate = 1.0;
                            }
                        }

                        // Esmaga banners
                        document.querySelectorAll('.ytp-ad-overlay-close-button').forEach(b => b.click());
                    } catch (err) {}
                }, 150);
            }
            """
            codigo_magico = codigo_magico.replace("__DEFAULT_VOLUME__", str(self.youtube_default_volume))
            self.page.evaluate(codigo_magico)
            print(">>> [PLAYWRIGHT] Motor furtivo injetado!")

            if video_resolvido and video_resolvido.get("title"):
                return f"Sucesso! Encontrei e coloquei '{video_resolvido['title']}' a tocar."
            return f"Sucesso! Coloquei '{pesquisa}' a tocar. Anti-Bot evadido."
            
        except Exception as e:
            return f"Erro na automação do YouTube: {str(e)}"

    # ==========================================
    # OS BOTÕES DO COMANDO REMOTO (Corrigidos)
    # ==========================================
    def controlar_reproducao(self, acao: str) -> str:
        """Pausa ou retoma a música atual com segurança."""
        if not self.page:
            return "Erro: O YouTube não está aberto no momento."
            
        try:
            if "pausar" in acao.lower() or "parar" in acao.lower():
                self.page.evaluate("() => { const v = document.querySelector('video'); if(v) v.pause(); }")
                return "A música foi pausada com sucesso."
            elif "retomar" in acao.lower() or "voltar" in acao.lower() or "play" in acao.lower():
                self.page.evaluate("() => { const v = document.querySelector('video'); if(v) v.play(); }")
                return "A música voltou a tocar."
            return "Ação não reconhecida."
        except Exception as e:
            return f"Falha ao executar o comando no navegador: {str(e)}"
        
        

    def ajustar_volume(self, nivel) -> str:
        """Ajusta o volume do vídeo blindado contra textos sujos."""
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
        
    def pular_musica(self) -> str:
        """Pula para o próximo vídeo/música na playlist do YouTube."""
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
    
    # ===== MÉTODOS ASYNC (NÃO BLOQUEIAM O EVENT LOOP) =====
    
    async def async_tocar_youtube_invisivel(self, pesquisa: str) -> str:
        """
        Versão ASYNC do YouTube que não bloqueia o FastAPI event loop.
        Usa async_playwright em vez de sync_playwright().
        
        CRÍTICO: Esta função deve ser chamada APENAS com await em contexto async.
        """
        print(f">>> [YOUTUBE ASYNC] A preparar motor web para: '{pesquisa}'...")
        
        try:
            # Importar async_playwright (não bloqueia!)
            from playwright.async_api import async_playwright
            
            # Resolver a URL do vídeo
            video_resolvido = self._resolver_video_youtube(pesquisa)
            query_url = urllib.parse.quote(pesquisa)
            
            # Inicializar async_playwright
            async with await async_playwright() as p:
                # Lançar browser
                browser = await p.chromium.launch(
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
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                
                # Criar página
                page = await context.new_page()
                
                # Injetar script anti-bot
                await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                
                # Navegar para o vídeo
                if video_resolvido and video_resolvido.get("id"):
                    print(f">>> [YOUTUBE ASYNC] Navegando para: {video_resolvido['id']}")
                    await page.goto(f"https://www.youtube.com/watch?v={video_resolvido['id']}", timeout=30000)
                else:
                    print(f">>> [YOUTUBE ASYNC] Procurando: {pesquisa}")
                    await page.goto(f"https://www.youtube.com/results?search_query={query_url}", timeout=30000)
                    await page.wait_for_selector("a#video-title", timeout=10000)
                    await page.click("a#video-title")
                
                # Aguardar player
                print(">>> [YOUTUBE ASYNC] Aguardando player...")
                await page.wait_for_selector("video", timeout=15000)
                await asyncio.sleep(2)
                
                # Injetar código de controle de volume (igual ao sync)
                codigo_magico = f"""
                (() => {{
                    const DEFAULT_VOLUME = {self.youtube_default_volume};
                    if (typeof window.__assistentePreferredVolume !== 'number') {{
                        window.__assistentePreferredVolume = DEFAULT_VOLUME;
                    }}
                    const v = document.querySelector('video');
                    if(v) {{
                        v.muted = false;
                        v.volume = DEFAULT_VOLUME;
                        if(v.paused) v.play();
                    }}
                }})();
                """
                
                await page.evaluate(codigo_magico)
                print(">>> [YOUTUBE ASYNC] Motor furtivo injetado!")
                
                # Cleanup
                await page.close()
                await context.close()
                await browser.close()
                
                if video_resolvido and video_resolvido.get("title"):
                    return f"Sucesso! Encontrei e coloquei '{video_resolvido['title']}' a tocar."
                return f"Sucesso! Coloquei '{pesquisa}' a tocar."
        
        except Exception as e:
            return f"Erro na automação do YouTube (async): {str(e)}"
    
    async def async_controlar_reproducao(self, acao: str) -> str:
        """
        Versão ASYNC do controle de reprodução.
        """
        # Para agora, retorna um placeholder
        # TODO: Implementar com async page control
        return f"Ação de reprodução: {acao} (async)"
    
    async def async_pular_musica(self) -> str:
        """
        Versão ASYNC para pular a música.
        """
        # TODO: Implementar com async page control
        return "Música pulada (async)"
        