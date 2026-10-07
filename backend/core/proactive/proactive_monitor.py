"""
ProactiveMonitor — a presença viva da Quinta-Feira.

Duas camadas, como num organismo:

  INSTINTOS (baratos, sem LLM): regras lendo sinais reais — bateria, CPU, RAM,
  disco, rede, clima, pausa, madrugada, jogo longo. Quando um instinto dispara,
  ele NÃO vira template: vira uma "situação percebida" entregue ao cérebro.

  CONSCIÊNCIA (LLM, com parcimônia): todo aviso é gerado com a fotografia
  completa do momento (ContextSensor) + os últimos avisos ditos (pra nunca se
  repetir). Além de reagir, ela tem comportamentos espontâneos: dá bom dia
  quando o PC liga de manhã, comenta quando um jogo abre, e de tempos em
  tempos decide POR CONTA PRÓPRIA se vale falar algo (pulso de presença —
  na maioria das vezes ela escolhe ficar quieta, como gente de verdade).

Entrega: fila consumida pelo frontend via /proactive (narra em voz alta).
Se o Matheus está longe do PC e a ponte do Telegram existe, o aviso também
vai pro celular. Amostras de hábito são gravadas na memória episódica e
alimentam a reflexão (aprendizado).
"""

from __future__ import annotations

import asyncio
import random
import socket
import time
from collections import deque
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import psutil
except Exception:
    psutil = None

try:
    from .. import get_logger
except ImportError:
    from .. import get_logger

from .context_snapshot import ContextSensor
from .atencao import Atencao, get_atencao
from .pregate import assinatura, aviso_vale, deve_acordar

logger = get_logger(__name__)

# Tipos que furam o horário de silêncio (coisa séria não espera amanhecer;
# madrugada é literalmente sobre falar de madrugada; lembrete com hora marcada
# foi o usuário que escolheu o horário)
# 'disco' SAIU dos críticos: disco cheio é condição crônica, não emergência —
# não deve furar silêncio/foco nem repetir. (bateria/temperatura são urgências reais.)
MAX_PESQUISAS_BASTIDOR = 2
_TIPOS_CRITICOS = {"bateria_critica", "temperatura", "madrugada", "lembrete"}
# Passam sem o avaliador (A5): críticos, saudação do dia e ações agendadas pelo Matheus
_TIPOS_SEM_AVALIACAO = _TIPOS_CRITICOS | {"saudacao", "agendado"}


class ProactiveMonitor:
    def __init__(
        self,
        *,
        brain: Any,
        config: Any,
        get_last_activity: Callable[[], Optional[float]],
        check_interval_seconds: int = 60,
        memory_manager: Optional[Any] = None,
        notifier: Optional[Any] = None,
        atencao: Optional[Atencao] = None,
    ) -> None:
        self._brain = brain
        self._config = config
        self._get_last_activity = get_last_activity
        self._interval = max(20, check_interval_seconds)
        self._memory = memory_manager
        self._notifier = notifier  # ex.: TelegramBridge (precisa de .is_available e .send)

        self._sensor = ContextSensor(config)
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._pending: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._state: Dict[str, Any] = {}
        self._session_start = time.time()

        # Memória do que ela já disse — base do anti-repetição
        # Gerente de atenção: quando NÃO falar (backoff por assunto, teto global, persistido em disco)
        self._atencao: Atencao = atencao if atencao is not None else get_atencao()
        self._ultimos_avisos: deque[str] = deque(self._atencao.recentes, maxlen=12)
        self._presenca_ini: Optional[float] = None   # início da presença CONTÍNUA (zera numa pausa real)

        # Pulso de presença (observações espontâneas)
        self._presence_enabled = bool(getattr(config, "PRESENCE_ENABLED", True))
        self._presence_interval = max(10, int(getattr(config, "PRESENCE_INTERVAL_MINUTES", 50))) * 60
        self._next_presence = time.time() + self._presence_interval * random.uniform(0.5, 1.0)
        # Pré-gate (A4): assinatura do contexto na última consulta ao LLM
        self._pregate_sig: Optional[tuple] = None
        self._pregate_ultima = 0.0

        self._quiet_start = int(getattr(config, "QUIET_HOURS_START", 1))
        self._quiet_end = int(getattr(config, "QUIET_HOURS_END", 7))

    # ── ciclo de vida ────────────────────────────────────────────────────────
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="proactive_monitor")
        logger.info("[PROATIVO] Presença viva iniciada")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[PROATIVO] Presença encerrada")

    # ── fila de avisos ───────────────────────────────────────────────────────
    async def get_pending(self) -> List[Dict[str, Any]]:
        async with self._lock:
            out = list(self._pending)
            self._pending.clear()
            return out

    async def _push(self, texto: str, tipo: str, snap: Optional[Dict[str, Any]] = None) -> bool:
        """Entrega o aviso. Devolve True se falou, False se descartou (repetido, bloqueado...)."""
        if not texto:
            return False
        # B13: tipos de aviso que o Matheus mandou calar (regra aceita a partir de lições repetidas)
        try:
            from ..learning.lesson_guards import get_guard_store
            if tipo not in _TIPOS_CRITICOS and tipo in get_guard_store().tipos_bloqueados():
                logger.debug(f"[PROATIVO] '{tipo}' bloqueado por regra aceita")
                return False
        except Exception:
            pass
        if tipo not in _TIPOS_SEM_AVALIACAO and getattr(self._config, "PREGATE_ENABLED", True):
            vale, motivo = aviso_vale(texto, list(self._ultimos_avisos))
            if not vale:
                logger.debug(f"[PROATIVO] '{tipo}' descartado pelo avaliador ({motivo})")
                return False
        async with self._lock:
            self._pending.append({"texto": texto, "tipo": tipo, "ts": time.time()})
        self._ultimos_avisos.append(texto)
        self._atencao.registrar(tipo, texto, time.time())
        # Aprende com o desfecho (respondeu ou ignorou): só avisos comuns, não críticos/agendados
        if tipo not in _TIPOS_SEM_AVALIACAO:
            try:
                from .reacao import get_reacao
                get_reacao().registrar_fala(tipo, time.time())
            except Exception:
                pass
        logger.info(f"[PROATIVO] {tipo}: {texto}")

        # Toast nativo do Windows: alcança o Matheus mesmo com o navegador fechado
        try:
            if bool(getattr(self._config, "NATIVE_NOTIFICATIONS_ENABLED", True)):
                from ..notify import notificar
                await notificar("Quinta-Feira", texto)
        except Exception as exc:
            logger.debug(f"[PROATIVO] toast nativo falhou: {exc}")

        # Matheus longe do PC + ponte disponível → o aviso vai pro celular também
        try:
            ocioso = (snap or {}).get("ocioso_seg")
            longe = ocioso is not None and ocioso > 900
            if longe and self._notifier and getattr(self._notifier, "is_available", False):
                await self._notifier.send(texto)
        except Exception as exc:
            logger.debug(f"[PROATIVO] espelho notifier falhou: {exc}")
        return True

    # ── utilidades ───────────────────────────────────────────────────────────
    def _cooldown_ok(self, key: str, segundos: float) -> bool:
        agora = time.time()
        if agora - self._state.get(f"cd_{key}", 0.0) >= segundos:
            self._state[f"cd_{key}"] = agora
            return True
        return False

    def _em_silencio(self, hora: int) -> bool:
        """Horário de silêncio (default 1h-7h): ela só fala se for crítico."""
        if self._quiet_start <= self._quiet_end:
            return self._quiet_start <= hora < self._quiet_end
        return hora >= self._quiet_start or hora < self._quiet_end

    def _usuario_presente(self, snap: Dict[str, Any], limite_seg: float = 300.0) -> bool:
        ocioso = snap.get("ocioso_seg")
        if ocioso is not None:
            return ocioso < limite_seg
        ultima = self._get_last_activity()
        return bool(ultima and (time.time() - ultima) < limite_seg)

    def _em_foco(self, snap: Optional[Dict[str, Any]]) -> bool:
        """Modo foco: sessão pomodoro ativa, jogo em tela cheia ou chamada — não interromper."""
        # Sessão de foco (pomodoro) na fase de trabalho sempre conta
        try:
            from ..focus import focus_store
            if focus_store.em_foco_ativo():
                return True
        except Exception:
            pass
        if not snap or not bool(getattr(self._config, "FOCUS_MODE_ENABLED", True)):
            return False
        if snap.get("em_chamada"):
            return True
        # Jogo + tela cheia = imersão; segura o que não é urgente
        if snap.get("jogo_rodando") and snap.get("fullscreen"):
            return True
        return False

    async def _avisar(
        self,
        situacao: str,
        tipo: str,
        snap: Optional[Dict[str, Any]] = None,
        hora: Optional[int] = None,
        piorou: bool = False,
    ) -> None:
        """Instinto disparou → cérebro transforma em fala natural, com contexto."""
        if hora is None:
            hora = time.localtime().tm_hour
        if self._em_silencio(hora) and tipo not in _TIPOS_CRITICOS:
            logger.debug(f"[PROATIVO] '{tipo}' segurado (horário de silêncio)")
            return
        # Modo foco: jogo fullscreen / chamada. Críticos (bateria, temperatura,
        # lembrete com hora marcada) furam; o resto espera ele sair da imersão.
        if self._em_foco(snap) and tipo not in _TIPOS_CRITICOS:
            logger.debug(f"[PROATIVO] '{tipo}' segurado (modo foco)")
            return

        # Atenção: já falei disso há pouco? falei demais hoje? Decide ANTES de gastar a chamada do LLM.
        vale, motivo_atencao = self._atencao.avaliar(tipo, time.time(), piorou=piorou)
        if not vale:
            logger.debug(f"[PROATIVO] '{tipo}' calado: {motivo_atencao}")
            return

        if snap is None:
            snap = await self._sensor.snapshot()
        contexto = ContextSensor.to_prompt(snap)

        texto = ""
        try:
            if hasattr(self._brain, "gerar_aviso_contextual"):
                texto = await self._brain.gerar_aviso_contextual(
                    situacao, contexto, list(self._ultimos_avisos)
                )
            else:
                texto = await self._brain.gerar_aviso(situacao)
        except Exception as exc:
            logger.warning(f"[PROATIVO] Falha ao gerar texto: {exc}")
        if not texto:
            # Falas espontâneas (saudação/observação) só existem com a voz dela:
            # sem LLM, melhor silêncio. Avisos factuais caem no texto da situação.
            # Só o que é urgente cai no texto cru; o resto, sem a voz dela, fica calado (a frase de
            # reserva idêntica a cada vez era o que soava como alarme).
            if tipo not in _TIPOS_CRITICOS:
                logger.debug(f"[PROATIVO] '{tipo}' descartado (LLM indisponível)")
                return
            texto = situacao.capitalize() + "."
        falou = await self._push(texto, tipo, snap)
        if not falou:
            # Descartado (repetido/bloqueado): mesmo assim gasta a paciência deste assunto, senão o
            # LLM seria chamado de novo a cada ciclo só para ser descartado outra vez.
            self._atencao.registrar(tipo, "", time.time())

    def _has_internet(self) -> bool:
        try:
            socket.setdefaulttimeout(3)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
            return True
        except Exception:
            return False

    def _downloads_size_gb(self) -> float:
        try:
            dl = Path.home() / "Downloads"
            if not dl.exists():
                return 0.0
            total = sum(f.stat().st_size for f in dl.rglob("*") if f.is_file())
            return total / (1024 ** 3)
        except Exception:
            return 0.0

    # ── loop principal ───────────────────────────────────────────────────────
    async def _loop(self) -> None:
        if psutil:
            try:
                psutil.cpu_percent()  # prime
            except Exception:
                pass
        await asyncio.sleep(20)  # aguarda estabilizar o boot
        while self._running:
            try:
                await self._checar()
            except Exception as exc:
                logger.warning(f"[PROATIVO] Erro no ciclo: {exc}")
            await asyncio.sleep(self._interval)

    async def _checar(self) -> None:
        agora = time.time()
        hora_local = time.localtime(agora).tm_hour
        snap = await self._sensor.snapshot()

        # ── COMPORTAMENTOS VIVOS ─────────────────────────────────────────────
        await self._checar_saudacao(snap, hora_local)
        await self._checar_despedida(snap, hora_local)
        await self._checar_jogo_abriu(snap, agora)
        await self._checar_pulso_presenca(snap, agora, hora_local)
        await self._checar_puxar_assunto(snap, agora, hora_local)
        await self._checar_autorevisao(snap, agora, hora_local)
        await self._checar_backup()
        await self._checar_memoria()
        await self._checar_pendencias(snap, agora, hora_local)
        await self._checar_bastidor(snap, agora)
        await self._amostrar_habito(snap, agora)
        await self._amostrar_musica(agora)

        # ── AGENDA DELA ──────────────────────────────────────────────────────
        await self._checar_lembretes(snap, hora_local)
        await self._checar_aniversarios(snap, hora_local)
        await self._checar_agenda_do_dia(snap, hora_local)
        await self._checar_agendados(snap, hora_local)
        await self._checar_padroes(snap, hora_local)

        # ── WHATSAPP PROATIVO ────────────────────────────────────────────────
        await self._checar_whatsapp(snap, hora_local)

        # ── FINANÇAS (watchlist) ─────────────────────────────────────────────
        await self._checar_financas(snap, hora_local)

        # ── COACH DE FOCO (pomodoro) ─────────────────────────────────────────
        await self._checar_foco(snap, hora_local)

        # ── SAÚDE DAS INTEGRAÇÕES (falha nunca silenciosa) ───────────────────
        await self._checar_saude(snap, hora_local)

        # ── INSTINTOS DE SISTEMA ─────────────────────────────────────────────
        if psutil:
            cpu = snap.get("cpu_pct", 0)
            ram = snap.get("ram_pct", 0)

            # CPU alta sustentada
            if cpu >= 88:
                self._state["cpu_count"] = self._state.get("cpu_count", 0) + 1
                if self._state["cpu_count"] >= 2 and self._cooldown_ok("cpu", 1800):
                    await self._avisar(
                        f"a CPU está em {int(cpu)}%, algo pesado está rodando", "cpu", snap, hora_local
                    )
            else:
                self._state["cpu_count"] = 0
                self._atencao.resolvido("cpu")

            # RAM quase cheia
            if ram >= 90 and self._cooldown_ok("ram", 1800):
                await self._avisar(
                    f"a memória RAM está em {int(ram)}% de uso — quase no limite", "ram", snap, hora_local,
                    piorou=ram >= 97,
                )
            elif ram < 85:
                self._atencao.resolvido("ram")

            # Temperatura da CPU (se disponível)
            try:
                temps = psutil.sensors_temperatures()
                cpu_temps = temps.get("coretemp") or temps.get("cpu_thermal") or []
                if cpu_temps:
                    max_temp = max(t.current for t in cpu_temps)
                    if max_temp >= 90 and self._cooldown_ok("temp", 1800):
                        await self._avisar(
                            f"a CPU está a {int(max_temp)}°C — perto do limite térmico",
                            "temperatura", snap, hora_local,
                        )
            except Exception:
                pass

            # Disco quase cheio — condição CRÔNICA, então no MÁXIMO 1x/dia e SÓ se
            # piorou de verdade desde o último aviso (ele não aguenta mais ouvir isso).
            try:
                if bool(getattr(self._config, "DISK_ALERTS_ENABLED", True)):
                    disco = psutil.disk_usage("C:\\")
                    livre_pct = (disco.free / disco.total) * 100
                    livre_gb = disco.free / (1024 ** 3)
                    # Limiar mais apertado (só quando fica REALMENTE crítico)
                    if livre_pct < 5 or livre_gb < 3:
                        ultimo = self._state.get("disco_ultimo_gb")
                        piorou = ultimo is None or livre_gb < (ultimo - 3)  # caiu +3GB
                        if piorou and self._cooldown_ok("disco", 86400):  # no máx 1x/dia
                            self._state["disco_ultimo_gb"] = livre_gb
                            await self._avisar(
                                f"o disco C: está bem no limite, só {livre_gb:.1f} GB livres",
                                "disco", snap, hora_local,
                            )
            except Exception:
                pass

            # Bateria
            if "bateria_pct" in snap and not snap.get("na_tomada", True):
                pct = snap["bateria_pct"]
                if pct <= 8 and self._cooldown_ok("bat_critica", 600):
                    await self._avisar(
                        f"a bateria está em {pct}% e descarregando rápido — crítico",
                        "bateria_critica", snap, hora_local,
                    )
                elif pct <= 20 and self._cooldown_ok("bat_baixa", 1800):
                    await self._avisar(
                        f"a bateria está em {pct}% e não tem carregador", "bateria", snap, hora_local,
                        piorou=pct <= 10,
                    )
            else:  # na tomada (ou sem bateria): o assunto acabou
                self._atencao.resolvido("bateria")
                self._atencao.resolvido("bateria_critica")

        # ── REDE ─────────────────────────────────────────────────────────────
        internet = await asyncio.to_thread(self._has_internet)
        if not internet and self._cooldown_ok("sem_internet", 600):
            await self._avisar("o computador perdeu acesso à internet", "rede", snap, hora_local)
        elif internet:
            self._state["cd_sem_internet"] = 0.0  # reseta cooldown se voltou
            self._atencao.resolvido("rede")

        # ── TEMPO / PAUSA ────────────────────────────────────────────────────
        presente = self._usuario_presente(snap, 600)

        continuo = self._atualizar_presenca(snap, agora, presente)

        # Trabalhando há muito tempo sem pausa
        if presente and continuo > 5400 and self._cooldown_ok("pausa", 5400):
            horas = max(1, int(continuo // 3600))
            await self._avisar(
                f"o Matheus está há mais de {horas} hora{'s' if horas > 1 else ''} seguidas sem dar uma pausa",
                "pausa", snap, hora_local,
            )

        # Madrugada ainda acordado (fura o silêncio de propósito: é cuidado)
        if hora_local in (1, 2, 3, 4) and presente and self._cooldown_ok("madrugada", 3600):
            await self._avisar(
                f"são {hora_local}h da manhã e o Matheus ainda está acordado na tela",
                "madrugada", snap, hora_local,
            )

        # Jogo há muitas horas seguidas
        jogo = snap.get("jogo_rodando", "")
        if jogo:
            key = f"jogo_{jogo}"
            if key not in self._state:
                self._state[key] = agora
            tempo_jogo = agora - self._state[key]
            if tempo_jogo > 10800 and self._cooldown_ok(f"jogo_aviso_{jogo}", 3600):
                horas_jogo = tempo_jogo / 3600
                await self._avisar(
                    f"o Matheus está jogando {jogo} há {horas_jogo:.0f} horas seguidas",
                    "jogo", snap, hora_local,
                )
        else:
            self._atencao.resolvido("jogo")
            for k in list(self._state.keys()):
                if k.startswith("jogo_") and not k.startswith("jogo_aviso_"):
                    del self._state[k]

        # Downloads acumulados — só com alertas de disco ligados, e bem alto (30GB),
        # no máximo 1x por semana (faz parte do "para de falar do meu armazenamento")
        if bool(getattr(self._config, "DISK_ALERTS_ENABLED", True)) and self._cooldown_ok("downloads_check", 604800):
            dl_gb = await asyncio.to_thread(self._downloads_size_gb)
            if dl_gb >= 30:
                await self._avisar(
                    f"a pasta Downloads está com {dl_gb:.0f} GB acumulados",
                    "downloads", snap, hora_local,
                )

        # ── CLIMA ────────────────────────────────────────────────────────────
        clima = snap.get("clima")
        if clima:
            desc = (clima.get("descricao") or "").lower()
            temp = clima.get("temp", 20)
            cidade = clima.get("cidade", "")
            if any(t in desc for t in ("chuva", "tempestade", "rain", "storm")):
                if self._cooldown_ok("clima_chuva", 21600):
                    await self._avisar(
                        f"está com {clima['descricao']} em {cidade} agora ({temp}°C)",
                        "clima", snap, hora_local,
                    )
            elif isinstance(temp, (int, float)) and temp >= 38 and self._cooldown_ok("clima_calor", 14400):
                await self._avisar(f"tá {temp}°C em {cidade} — calor extremo", "clima", snap, hora_local)
            elif isinstance(temp, (int, float)) and temp <= 5 and self._cooldown_ok("clima_frio", 14400):
                await self._avisar(f"tá {temp}°C em {cidade} — frio de verdade hoje", "clima", snap, hora_local)

    def _atualizar_presenca(self, snap: Dict[str, Any], agora: float, presente: bool) -> float:
        """Segundos de presença CONTÍNUA (e não o tempo desde que o backend subiu): uma pausa real
        (ocioso > 5 min) zera a contagem e o assunto. Antes o aviso repetia "há N horas sem pausa"
        mesmo depois de ele ter parado, porque contava o uptime do programa."""
        ocioso = snap.get("ocioso_seg")
        if ocioso is not None and ocioso > 300:
            self._presenca_ini = None
            self._atencao.resolvido("pausa")
        elif presente and self._presenca_ini is None:
            self._presenca_ini = agora
        return (agora - self._presenca_ini) if self._presenca_ini else 0.0

    # ── comportamentos vivos ──────────────────────────────────────────────────
    async def _checar_saudacao(self, snap: Dict[str, Any], hora: int) -> None:
        """Bom dia espontâneo: primeira presença do dia entre 6h e 12h.
        Com BRIEFING_RITUAL_ENABLED, vira um panorama completo do dia."""
        hoje = date.today().isoformat()
        if self._state.get("saudacao_dia") == hoje:
            return
        if not (6 <= hora < 13):
            return
        if not self._usuario_presente(snap, 240):
            return
        self._state["saudacao_dia"] = hoje

        # Briefing ritual: panorama completo do dia (clima+notícias+agenda+mercado+lembretes)
        if bool(getattr(self._config, "BRIEFING_RITUAL_ENABLED", True)) and hasattr(self._brain, "montar_briefing"):
            try:
                texto = await self._brain.montar_briefing("manha")
                if texto and not (hasattr(self._brain, "_parece_erro")):
                    await self._push(texto, "saudacao", snap)
                    return
                if texto:
                    await self._push(texto, "saudacao", snap)
                    return
            except Exception as exc:
                logger.debug(f"[PROATIVO] briefing matinal falhou: {exc}")

        await self._avisar(
            "o Matheus acabou de começar o dia no computador — dê um bom dia do SEU jeito, "
            "breve (1-2 frases), aproveitando o que você vê do momento (dia da semana, clima, "
            "o que ele já abriu)",
            "saudacao", snap, hora,
        )

    async def _checar_despedida(self, snap: Dict[str, Any], hora: int) -> None:
        """Fechamento de dia: 1x/dia, tarde da noite (22h-1h), se ele ainda está."""
        if not bool(getattr(self._config, "BRIEFING_RITUAL_ENABLED", True)):
            return
        if not hasattr(self._brain, "montar_briefing"):
            return
        hoje = date.today().isoformat()
        if self._state.get("despedida_dia") == hoje:
            return
        if not (hora >= 22 or hora == 0):
            return
        if not self._usuario_presente(snap, 300):
            return
        self._state["despedida_dia"] = hoje
        try:
            texto = await self._brain.montar_briefing("noite")
            if texto:
                await self._push(texto, "observacao", snap)
        except Exception as exc:
            logger.debug(f"[PROATIVO] despedida falhou: {exc}")

    async def _checar_jogo_abriu(self, snap: Dict[str, Any], agora: float) -> None:
        """Reação espontânea quando um jogo ACABOU de abrir (nem sempre — como gente)."""
        jogo = snap.get("jogo_rodando", "")
        anterior = self._state.get("ultimo_jogo_visto", "")
        self._state["ultimo_jogo_visto"] = jogo
        if not jogo or jogo == anterior:
            return
        # Marco do dia: alimenta o ESTADO INTERNO (continuidade nas conversas)
        try:
            from .internal_state import get_internal_state
            get_internal_state().registrar_marco(f"ele abriu o {jogo}")
        except Exception:
            pass
        if not self._cooldown_ok("jogo_abriu", 7200):
            return
        if random.random() < 0.45:  # na maioria das vezes ela deixa quieto
            await self._avisar(
                f"o Matheus acabou de abrir o {jogo} — solte um comentário curto e espontâneo "
                "sobre isso, do seu jeito (pode provocar de leve, reconhecendo os hábitos dele)",
                "observacao", snap,
            )

    async def _checar_pulso_presenca(self, snap: Dict[str, Any], agora: float, hora: int) -> None:
        """De tempos em tempos ela DECIDE se tem algo que vale dizer. Quase sempre: não."""
        if not self._presence_enabled or agora < self._next_presence:
            return
        # reagenda já (com variação — cadência humana, não de cron)
        self._next_presence = agora + self._presence_interval * random.uniform(0.7, 1.4)

        if self._em_silencio(hora) or not self._usuario_presente(snap, 300):
            return
        if not hasattr(self._brain, "decidir_observacao"):
            return
        vale, motivo_atencao = self._atencao.avaliar("observacao", agora)
        if not vale:
            logger.debug(f"[PROATIVO] pulso: sem LLM ({motivo_atencao})")
            return
        descoberta = await self._descoberta_recente()
        if getattr(self._config, "PREGATE_ENABLED", True):
            acordar, motivo = deve_acordar(
                snap, self._pregate_sig, descoberta=descoberta, agora=agora,
                ultima_consulta=self._pregate_ultima,
            )
            if not acordar:
                logger.debug(f"[PROATIVO] pré-gate: sem LLM ({motivo})")
                return
            logger.debug(f"[PROATIVO] pré-gate: consultando o LLM ({motivo})")
            self._pregate_sig = assinatura(snap)
            self._pregate_ultima = agora
        try:
            texto = await self._brain.decidir_observacao(
                ContextSensor.to_prompt(snap),
                list(self._ultimos_avisos),
                descoberta=descoberta,
            )
        except TypeError:
            # brain antigo sem o parâmetro descoberta
            texto = await self._brain.decidir_observacao(
                ContextSensor.to_prompt(snap), list(self._ultimos_avisos)
            )
        except Exception as exc:
            logger.debug(f"[PROATIVO] pulso falhou: {exc}")
            return
        if texto:
            await self._push(texto, "observacao", snap)
        else:
            logger.debug("[PROATIVO] pulso: ela preferiu ficar quieta")

    async def _checar_pendencias(self, snap: Dict[str, Any], agora: float, hora: int) -> None:
        """Retoma UMA pendência em aberto por dia (frase fixa, sem LLM). Só com ele presente, fora de silêncio
        e de foco; no 3º toque sem resposta, arquiva sozinha (não insiste)."""
        if not self._cooldown_ok("pendencias_check", 1800) or self._em_silencio(hora) or self._em_foco(snap):
            return
        if not self._usuario_presente(snap, 300):
            return
        try:
            from ..learning.pendencias import frase_de_retomada, get_pendencias
            loja = get_pendencias()
            p = loja.proxima_para_retomar(agora)
            if not p or not self._atencao.avaliar("pendencia", agora)[0]:
                return
            falou = await self._push(frase_de_retomada(p), "pendencia", snap)
            if falou:
                if loja.registrar_toque(p["id"], agora) == "arquivada":
                    logger.info(f"[PENDENCIAS] '{p['texto'][:40]}' arquivada por falta de resposta")
        except Exception as exc:
            logger.debug(f"[PROATIVO] pendências falhou: {exc}")

    async def _checar_bastidor(self, snap: Dict[str, Any], agora: float) -> None:
        """De madrugada, com ele longe, prepara resumo para até 2 pendências (silencioso; ver bastidor.py)."""
        if not self._cooldown_ok("bastidor_check", 3600) or self._usuario_presente(snap, 900):
            return
        try:
            from ..learning.bastidor import rodar_noite
            from ..learning.pendencias import get_pendencias
            from ..learning.search_guard import SearchGuard
            from pathlib import Path as _P
            guarda = SearchGuard(runtime_dir=_P(__file__).resolve().parents[2] / ".runtime",
                                 max_por_rodada=MAX_PESQUISAS_BASTIDOR, max_por_dia=int(getattr(self._config, "CURIOSITY_MAX_PER_DAY", 12)))

            async def pesquisar(q: str):
                from ..tools.web_search_tool import _buscar_ddg, _buscar_tavily
                chave = getattr(self._config, "TAVILY_API_KEY", "")
                if chave:
                    try:
                        r = await asyncio.to_thread(_buscar_tavily, q, 5, chave)
                        if r:
                            return r
                    except Exception:
                        pass
                return await asyncio.to_thread(_buscar_ddg, q, 5)

            r = await rodar_noite(self._brain, get_pendencias(), guarda, pesquisar, agora=agora)
            if r.get("feitas"):
                logger.info(f"[BASTIDOR] {r['feitas']} preparo(s) pronto(s)")
        except Exception as exc:
            logger.debug(f"[PROATIVO] bastidor falhou: {exc}")

    async def _checar_backup(self) -> None:
        """Uma cópia por dia do que ela aprendeu (silenciosa; se já existe a de hoje, não faz nada)."""
        if not self._cooldown_ok("backup_check", 1800):
            return
        try:
            from ..host.backup import fazer_backup
            pasta = await asyncio.to_thread(fazer_backup)
            if pasta is not None:
                logger.info(f"[BACKUP] cópia do dia criada: {pasta.name}")
        except Exception as exc:
            logger.warning(f"[BACKUP] falhou: {exc}")

    async def _checar_memoria(self) -> None:
        """Faxina diária SILENCIOSA da memória: junta categorias fragmentadas (com pré-imagem) e poda
        telemetria velha (amostras de hábito/música). Sem LLM, sem fala; nunca apaga fato aprendido."""
        if not self._cooldown_ok("memoria_manutencao", 24 * 3600):
            return
        mm = getattr(self._brain, "memory_manager", None)
        if mm is None:
            return
        try:
            n = await mm.normalizar_categorias()
            t = await mm.podar_telemetria()
            if n.get("alteradas") or any(t.values()):
                logger.info(f"[MEMORIA] manutenção: categorias={n} telemetria podada={t}")
        except Exception as exc:
            logger.debug(f"[MEMORIA] manutenção falhou: {exc}")

    async def _checar_autorevisao(self, snap: Dict[str, Any], agora: float, hora: int) -> None:
        """Uma vez por semana ela revisa as próprias falhas e guarda sugestões (no máximo 1 chamada
        leve; sem lacunas suficientes, nenhuma). Só avisa que há sugestões, com frase fixa."""
        if not self._cooldown_ok("autorevisao", 3600) or self._em_silencio(hora):
            return
        try:
            from ..learning.self_review import revisar
            r = await revisar(self._brain, agora=agora)
        except Exception as exc:
            logger.debug(f"[PROATIVO] autorrevisão falhou: {exc}")
            return
        if r.get("novas"):
            await self._push(
                f"Fiz minha revisão da semana e tenho {r['novas']} sugestão(ões) de melhoria para você olhar no painel de memória.",
                "melhoria", snap)

    async def _checar_puxar_assunto(self, snap: Dict[str, Any], agora: float, hora: int) -> None:
        """
        De vez em quando ela puxa papo do nada (como um amigo). Raro de propósito:
        cooldown ~4h + chance aleatória, só presente, fora de silêncio/foco.
        """
        if not getattr(self._config, "CONVERSATION_STARTER_ENABLED", True):
            return
        if not self._cooldown_ok("puxar_assunto", 4 * 3600):
            return
        if self._em_silencio(hora) or self._em_foco(snap):
            return
        if not self._usuario_presente(snap, 300):
            return
        if random.random() > 0.5:  # nem toda janela vira conversa
            return
        if not hasattr(self._brain, "puxar_assunto"):
            return
        if not self._atencao.avaliar("observacao")[0]:
            return
        try:
            descoberta = await self._descoberta_recente()
            texto = await self._brain.puxar_assunto(
                ContextSensor.to_prompt(snap), descoberta, list(self._ultimos_avisos)
            )
        except Exception as exc:
            logger.debug(f"[PROATIVO] puxar assunto falhou: {exc}")
            return
        if texto:
            await self._push(texto, "observacao", snap)

    async def _amostrar_musica(self, agora: float) -> None:
        """
        Ouvido musical: a cada ~4 min anota O QUE está tocando (via sessões de
        mídia do Windows — qualquer player). Vira matéria-prima da reflexão:
        ela aprende o gosto musical dele sozinha.
        """
        if not self._memory or not self._cooldown_ok("music_sample", 240):
            return
        try:
            from ..tools.media_tool import _listar_sessoes
            sessoes = await _listar_sessoes()
        except Exception as exc:
            logger.debug(f"[PROATIVO] sessões de mídia indisponíveis: {exc}")
            return
        atual = next((s for s in sessoes if s["tocando"] and s["titulo"]), None)
        if not atual:
            return
        chave = f"{atual['titulo']}|{atual['artista']}"
        if chave == self._state.get("ultima_musica"):
            return  # mesma faixa, não duplica
        self._state["ultima_musica"] = chave
        try:
            await self._memory.save_memory(
                memory_type="episodic",
                content=f"ouvindo: {atual['titulo']}"
                + (f" — {atual['artista']}" if atual["artista"] else ""),
                event_type="music_sample",
                importance=0.1,
                tags=["musica"],
                payload={"titulo": atual["titulo"], "artista": atual["artista"], "app": atual["app"]},
            )
        except Exception as exc:
            logger.debug(f"[PROATIVO] amostra de música falhou: {exc}")

    async def _checar_lembretes(self, snap: Dict[str, Any], hora: int) -> None:
        """Lembretes pontuais vencidos viram aviso falado (furam o silêncio:
        o horário foi escolhido pelo próprio usuário)."""
        if not self._cooldown_ok("lembretes_check", 45):
            return
        try:
            from . import reminders_store
            pendentes = await asyncio.to_thread(reminders_store.vencidos)
        except Exception as exc:
            logger.debug(f"[PROATIVO] lembretes indisponíveis: {exc}")
            return
        for lem in pendentes[:3]:
            await self._avisar(
                f"chegou a hora de um lembrete que ele pediu: \"{lem['texto']}\" — "
                "entregue o lembrete de forma direta",
                "lembrete", snap, hora,
            )
            try:
                await asyncio.to_thread(reminders_store.marcar_entregue, lem["id"])
            except Exception:
                pass

    async def _checar_aniversarios(self, snap: Dict[str, Any], hora: int) -> None:
        """Datas anuais (aniversários): um aviso no dia, a partir das 8h."""
        if hora < 8 or not self._cooldown_ok("aniversarios_check", 3600):
            return
        try:
            from . import reminders_store
            datas = await asyncio.to_thread(reminders_store.aniversarios_de_hoje)
        except Exception as exc:
            logger.debug(f"[PROATIVO] aniversários indisponíveis: {exc}")
            return
        for d in datas[:3]:
            await self._avisar(
                f"hoje é uma data anual que ele anotou: \"{d['texto']}\" — "
                "lembre ele disso com carinho (e sugira algo se fizer sentido)",
                "aniversario", snap, hora,
            )

    async def _checar_agendados(self, snap: Dict[str, Any], hora: int) -> None:
        """Ações agendadas: roda o comando pelo brain no horário e narra o resultado."""
        try:
            from ..scheduler import scheduled_store
            devidas = await asyncio.to_thread(scheduled_store.devidas)
        except Exception as exc:
            logger.debug(f"[PROATIVO] agendados indisponíveis: {exc}")
            return
        for t in devidas[:3]:
            try:
                # Comando que ELE agendou: quando dispara, ações críticas pedem aprovação na tela
                # (sem tela aberta, são negadas) — ele não está necessariamente olhando.
                from ..policy.approvals import ORIGEM_AGENDADO, com_origem_async

                resp = await com_origem_async(ORIGEM_AGENDADO, self._brain.ask(t["comando"]))
                texto = (getattr(resp, "text", "") or "").strip()
                if texto:
                    await self._push(texto, "agendado", snap)
            except Exception as exc:
                logger.debug(f"[PROATIVO] tarefa agendada falhou: {exc}")
            finally:
                try:
                    await asyncio.to_thread(scheduled_store.marcar_executada, t["id"])
                except Exception:
                    pass

    async def _checar_padroes(self, snap: Dict[str, Any], hora: int) -> None:
        """
        Olha padrões e cutuca com CUIDADO (1x/dia): pessoas do CRM que ele não fala
        há tempo, e maratona de tela/jogo. Como alguém que se importa, não um alarme.
        """
        if not self._cooldown_ok("padroes_check", 86400):
            return
        if self._em_silencio(hora) or not self._usuario_presente(snap, 600):
            return

        # Relacionamento: alguém importante sem contato há um tempo
        try:
            from ..people import people_store
            esquecidos = await asyncio.to_thread(people_store.sem_contato_ha, 12)
            if esquecidos:
                import time as _t
                p = esquecidos[0]
                dias = int((_t.time() - p["ultimo_contato_ts"]) / 86400)
                rel = f", sua {p['relacao']}," if p.get("relacao") else ""
                await self._avisar(
                    f"faz {dias} dias que o Matheus não fala com a {p['nome']}{rel} — "
                    "lembre ele disso com leveza, como quem cuida (sem cobrar)",
                    "observacao", snap, hora,
                )
                return  # um cuidado por dia basta
        except Exception as exc:
            logger.debug(f"[PROATIVO] padrão de relacionamento falhou: {exc}")

    async def _checar_agenda_do_dia(self, snap: Dict[str, Any], hora: int) -> None:
        """De manhã (8-11h, 1x/dia), passa os compromissos do dia da Google Agenda."""
        url = getattr(self._config, "CALENDAR_ICS_URL", "")
        if not url or not (8 <= hora < 11):
            return
        hoje = date.today().isoformat()
        if self._state.get("agenda_dia") == hoje:
            return
        if not self._usuario_presente(snap, 600):
            return
        try:
            from ..calendar import eventos_de_hoje, formatar
            eventos = await eventos_de_hoje(url)
        except Exception as exc:
            logger.debug(f"[PROATIVO] agenda indisponível: {exc}")
            return
        self._state["agenda_dia"] = hoje
        if not eventos:
            return
        lista = "; ".join(formatar(e) for e in eventos[:5])
        await self._avisar(
            f"a agenda dele hoje tem: {lista}. Passe os compromissos do dia de forma "
            "leve e organizada, como uma secretária que se importa",
            "agenda", snap, hora,
        )

    @staticmethod
    def _cdp_disponivel() -> bool:
        """True se o Edge do WhatsApp já está aberto (não lançamos sozinhos)."""
        try:
            socket.setdefaulttimeout(1.5)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("127.0.0.1", 9222))
            return True
        except Exception:
            return False

    async def _checar_whatsapp(self, snap: Dict[str, Any], hora: int) -> None:
        """
        Triagem proativa: de tempos em tempos olha o WhatsApp e avisa quando chega
        mensagem nova. Não lê conteúdo em voz alta — só quem mandou. Roda apenas se
        o Edge do WhatsApp já está aberto (não lançamos sozinhos).

        Filtro de ruído confiável: a triagem já descarta chats MUTADOS (sinal do
        próprio WhatsApp, ao contrário da heurística de "é grupo?" do DOM, que erra
        os dois lados). Aqui só anunciamos contatos que ficaram não-lidos DESDE a
        última varredura (diff), com cooldown por contato e teto baixo — pra ser
        presença, não um alto-falante.
        """
        if not bool(getattr(self._config, "WA_TRIAGE_ENABLED", True)):
            return
        intervalo = max(10, int(getattr(self._config, "WA_TRIAGE_INTERVAL_MINUTES", 30))) * 60
        if not self._cooldown_ok("wa_triage", intervalo):
            return
        if self._em_silencio(hora):
            return
        if not await asyncio.to_thread(self._cdp_disponivel):
            logger.debug("[PROATIVO] WhatsApp: Edge fechado, triagem pulada")
            return

        try:
            from ..tools.whatsapp_tool import _triagem_in_thread
            bruto = await asyncio.to_thread(_triagem_in_thread)
        except Exception as exc:
            logger.debug(f"[PROATIVO] triagem falhou: {exc}")
            return

        import json as _json
        import re as _re
        try:
            texto = _json.loads(bruto) if bruto.strip().startswith('"') else bruto
            m = _re.search(r"\[.*\]", texto, _re.DOTALL)
            chats = _json.loads(m.group(0)) if m else []
        except Exception:
            chats = []

        # Primeira varredura da sessão: só fotografa o estado atual (não anuncia
        # tudo que já estava não-lido quando ligamos — isso seria spam de boot).
        primeira = "wa_vistos" not in self._state
        vistos: Dict[str, bool] = self._state.setdefault("wa_vistos", {})
        novos: List[str] = []
        fixados: List[str] = []
        agora = time.time()
        for chat in chats:
            nome = str(chat.get("nome", "")).strip()
            if not nome:
                continue
            tem_nova = bool(chat.get("tem_nova_mensagem"))
            # CRM: registra último contato de quem mandou mensagem nova
            if tem_nova and not chat.get("is_grupo"):
                try:
                    from ..people import people_store
                    await asyncio.to_thread(people_store.registrar_contato, nome)
                except Exception:
                    pass
            ja_tinha = vistos.get(nome, False)
            vistos[nome] = tem_nova
            # Só nos importa quem ficou não-lido DESDE a última varredura
            if primeira or not tem_nova or ja_tinha:
                continue
            cd_key = f"wa_contato_{nome}"
            if agora - self._state.get(cd_key, 0.0) < 2700:  # 45 min por contato
                continue
            self._state[cd_key] = agora
            (fixados if chat.get("is_pinned") else novos).append(nome)

        # Fixados (VIPs) primeiro; teto baixo pra não virar alto-falante
        anunciar = (fixados + novos)[:3]
        if anunciar:
            quem = ", ".join(anunciar)
            await self._avisar(
                f"chegou mensagem nova no WhatsApp de: {quem}. Avise quem mandou, "
                "SEM inventar o conteúdo (você não leu as mensagens)",
                "whatsapp", snap, hora,
            )

    async def _checar_saude(self, snap: Dict[str, Any], hora: int) -> None:
        """
        A cada ~2h, checa as integrações. Se algo que ANTES funcionava quebrou
        (ex: WhatsApp deslogou, embeddings caíram), avisa o Matheus — falha
        deixa de ser silenciosa. Só fala de ERRO (não de coisa desligada por opção)
        e só quando MUDA pra pior (não fica repetindo).
        """
        if not self._cooldown_ok("saude_check", 7200):
            return
        if self._em_silencio(hora):
            return
        try:
            from ..diagnostics import diagnostico_completo
            rep = await diagnostico_completo()
        except Exception as exc:
            logger.debug(f"[PROATIVO] diagnóstico falhou: {exc}")
            return

        quebrados = {
            nome for nome, c in rep.get("checks", {}).items()
            if c.get("estado") == "erro"
        }
        antes = self._state.get("saude_quebrados", set())
        novos = quebrados - antes
        self._state["saude_quebrados"] = quebrados
        if novos:
            detalhes = "; ".join(
                f"{n} ({rep['checks'][n].get('detalhe','')})" for n in novos
            )
            await self._avisar(
                f"uma função sua parou de funcionar e ele precisa saber: {detalhes}. "
                "Avise de forma direta e honesta, dizendo que pode precisar de ajuste",
                "saude", snap, hora,
            )

    async def _checar_foco(self, snap: Dict[str, Any], hora: int) -> None:
        """Anuncia as viradas do pomodoro (fim de foco→pausa, fim de pausa→foco, fim da sessão).
        FURA silêncio/foco de propósito: foi o Matheus que iniciou a sessão e quer ser avisado."""
        try:
            from ..focus import focus_store
            t = await asyncio.to_thread(focus_store.transicao_devida)
        except Exception as exc:
            logger.debug(f"[PROATIVO] foco indisponível: {exc}")
            return
        if not t:
            return
        ev = t.get("evento")
        if ev == "fim_foco":
            situacao = (f"o ciclo de foco terminou (foram {t.get('ciclos')} até agora) — hora de uma "
                        f"pausa de {t.get('pausa_min')} min, avise ele pra descansar um pouco")
        elif ev == "fim_pausa":
            situacao = f"a pausa acabou — chame o Matheus de volta pra mais um ciclo de {t.get('foco_min')} min de foco"
        else:  # fim_sessao
            situacao = (f"a sessão de foco terminou ({t.get('ciclos')} ciclos completos!) — "
                        "parabenize ele pelo foco e pergunte se quer continuar ou parar")
        await self._avisar(situacao, "lembrete", snap, hora)  # 'lembrete' fura silêncio/foco

    async def _checar_financas(self, snap: Dict[str, Any], hora: int) -> None:
        """
        Watchlist: cota os ativos acompanhados e avisa quando o preço se move além
        do limite que o Matheus definiu, comparado ao último preço já avisado.
        """
        if not bool(getattr(self._config, "FINANCE_ENABLED", True)):
            return
        intervalo = max(5, int(getattr(self._config, "FINANCE_INTERVAL_MINUTES", 20))) * 60
        if not self._cooldown_ok("financas_check", intervalo):
            return
        if self._em_silencio(hora):
            return
        try:
            from ..finance import cotar, watchlist_store
            itens = await asyncio.to_thread(watchlist_store.listar)
        except Exception as exc:
            logger.debug(f"[PROATIVO] watchlist indisponível: {exc}")
            return

        for it in itens:
            try:
                cot = await cotar(it["simbolo"])
                if not cot:
                    continue
                base = it.get("ultimo_preco_avisado")
                preco = cot["preco"]
                if not base:
                    await asyncio.to_thread(watchlist_store.marcar_preco_avisado, it["simbolo"], preco)
                    continue
                variacao = (preco - base) / base * 100.0
                if abs(variacao) >= float(it.get("limite_pct", 3.0)):
                    direcao = "subiu" if variacao > 0 else "caiu"
                    await self._avisar(
                        f"{it['nome']} {direcao} {abs(variacao):.1f}% desde o último aviso "
                        f"(agora {cot.get('moeda','')} {preco:.2f}) — ele pediu pra acompanhar",
                        "financas", snap, hora,
                    )
                    await asyncio.to_thread(watchlist_store.marcar_preco_avisado, it["simbolo"], preco)
            except Exception as exc:
                logger.debug(f"[PROATIVO] checagem de {it.get('nome')} falhou: {exc}")

    async def _descoberta_recente(self) -> Optional[str]:
        """
        Última descoberta da curiosidade (aprendizado via internet) que ela ainda
        NÃO contou — combustível pro pulso de presença chegar com novidade.
        """
        if not self._memory:
            return None
        try:
            res = await self._memory.search_memory(
                query="descoberta", memory_type="episodic", limit=6
            )
            ja_ditas = " ".join(self._ultimos_avisos)
            for ep in res.get("episodic", []):
                if ep.get("event_type") != "descoberta":
                    continue
                texto = str(ep.get("summary") or ep.get("content") or "").strip()
                # não repete uma descoberta que já virou fala
                if texto and texto[:60] not in ja_ditas:
                    return texto
        except Exception as exc:
            logger.debug(f"[PROATIVO] descoberta indisponível: {exc}")
        return None

    async def _amostrar_habito(self, snap: Dict[str, Any], agora: float) -> None:
        """A cada ~15 min grava uma amostra do momento — combustível da reflexão."""
        if not self._memory or not self._cooldown_ok("habit_sample", 900):
            return
        try:
            await self._memory.save_memory(
                memory_type="episodic",
                content="habit_sample",
                event_type="habit_sample",
                importance=0.1,
                tags=["habito"],
                payload={
                    "hora": snap.get("hora", ""),
                    "dia_semana": snap.get("dia_semana", ""),
                    "foco": snap.get("app_em_foco", ""),
                    "jogo": snap.get("jogo_rodando", ""),
                    "ativo": self._usuario_presente(snap, 300),
                },
            )
        except Exception as exc:
            logger.debug(f"[PROATIVO] amostra de hábito falhou: {exc}")
