"""
Broker de aprovacoes: a Quinta-Feira PERGUNTA antes de fazer algo critico (Fase 0.3).

Fluxo: o LLM pede uma tool -> ToolRegistry.execute classifica o risco -> se for critico,
chama `gate()` aqui -> o broker manda `approval_requested` para as telas conectadas e
ESPERA a resposta (`approval_response`) -> sem resposta no prazo, NEGA.

Modos de autonomia (o usuario escolhe; persistido em backend/.runtime/autonomy.json):
  perguntar_sempre   pede em escrita E critica
  so_perigoso        pede so em critica                      <- padrao
  autonoma           nao pede (tudo e auditado do mesmo jeito)

Origem da chamada (contextvar `origem_atual`, definida por quem chama brain.ask):
  telegram   o dono, autenticado por chat_id: liberado (nao ha tela para confirmar)
  autonomo   loop autonomo sem ninguem olhando: acao critica e NEGADA, nao perguntada
  demais     perguntam na tela; sem tela aberta, NEGA

Regra de ouro: guardrail no CODIGO, nao no prompt — um aviso escrito no prompt some quando
o contexto e compactado (um agente ja apagou centenas de e-mails assim).
"""

import asyncio
import contextlib
import contextvars
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Tuple

from .content_origin import eleva_sob_contaminacao, fontes_contaminadas
from .tool_risk import Risco, resumir

try:
    from ..logger import get_logger
except ImportError:  # execucao fora do pacote
    from core.logger import get_logger

logger = get_logger(__name__)

MODO_PERGUNTAR_SEMPRE = "perguntar_sempre"
MODO_SO_PERIGOSO = "so_perigoso"
MODO_AUTONOMA = "autonoma"
MODOS = (MODO_PERGUNTAR_SEMPRE, MODO_SO_PERIGOSO, MODO_AUTONOMA)

ORIGEM_TELEGRAM = "telegram"
ORIGEM_AUTONOMO = "autonomo"
ORIGEM_AGENDADO = "agendado"

origem_atual: "contextvars.ContextVar[str]" = contextvars.ContextVar("qf_origem", default="desconhecida")

_RAIZ = Path(__file__).resolve().parents[2]  # backend/
_ARQ_MODO = _RAIZ / ".runtime" / "autonomy.json"
_ARQ_AUDITORIA = _RAIZ / ".runtime" / "audit" / "tool_risk.jsonl"


@contextlib.contextmanager
def com_origem(origem: str):
    """`with com_origem("telegram"): await brain.ask(...)` — marca de onde veio o pedido."""
    token = origem_atual.set(origem)
    try:
        yield
    finally:
        origem_atual.reset(token)


async def com_origem_async(origem: str, corrotina: Awaitable[Any]) -> Any:
    """Versao de uma linha: `await com_origem_async("agendado", brain.ask(...))`."""
    token = origem_atual.set(origem)
    try:
        return await corrotina
    finally:
        origem_atual.reset(token)


@dataclass
class _Pendente:
    id: str
    ferramenta: str
    resumo: str
    risco: str
    origem: str
    criado: float
    futuro: "asyncio.Future[bool]"
    # Veio depois de ler conteudo de terceiros (WhatsApp, web...)? Vira aviso no cartao.
    fontes: Tuple[str, ...] = ()


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApprovalBroker:
    def __init__(
        self,
        arquivo_modo: Optional[Path] = None,
        arquivo_auditoria: Optional[Path] = None,
        timeout_s: float = 60.0,
        telegram_confiavel: bool = True,
    ) -> None:
        self._enviar: Optional[Callable[[Dict[str, Any]], Awaitable[int]]] = None
        self._pendentes: Dict[str, _Pendente] = {}
        self.timeout_s = timeout_s
        self.telegram_confiavel = telegram_confiavel
        self._arq_modo = arquivo_modo or _ARQ_MODO
        self._arq_auditoria = arquivo_auditoria or _ARQ_AUDITORIA
        self._telemetria: Any = None
        self._modo = self._carregar_modo()

    # ----------------------------------------------------------------- configuracao

    def configurar(self, enviar: Callable[[Dict[str, Any]], Awaitable[int]]) -> None:
        """`enviar(evento) -> quantas telas receberam` (o main liga ao ConnectionManager)."""
        self._enviar = enviar

    def _carregar_modo(self) -> str:
        try:
            modo = json.loads(self._arq_modo.read_text(encoding="utf-8")).get("modo", "")
            if modo in MODOS:
                return modo
        except Exception:
            pass
        env = os.getenv("AUTONOMY_MODE", "").strip().lower()
        return env if env in MODOS else MODO_SO_PERIGOSO

    @property
    def modo(self) -> str:
        return self._modo

    def definir_modo(self, modo: str) -> bool:
        if modo not in MODOS:
            return False
        self._modo = modo
        try:
            self._arq_modo.parent.mkdir(parents=True, exist_ok=True)
            self._arq_modo.write_text(json.dumps({"modo": modo}), encoding="utf-8")
        except Exception as exc:
            logger.debug(f"[APROVACAO] Falha ao persistir modo: {exc}")
        logger.info(f"[APROVACAO] Modo de autonomia: {modo}")
        return True

    def exige(self, risco: Risco) -> bool:
        """Este risco pede aprovacao no modo atual?"""
        if self._modo == MODO_AUTONOMA:
            return False
        if self._modo == MODO_PERGUNTAR_SEMPRE:
            return risco in (Risco.ESCRITA, Risco.CRITICA)
        return risco == Risco.CRITICA

    # ----------------------------------------------------------------- o gate

    async def gate(self, ferramenta: str, argumentos: Mapping[str, Any], risco: Risco) -> Tuple[bool, str]:
        """Decide se a chamada pode rodar. Retorna (permitido, motivo_da_negativa)."""
        origem = origem_atual.get()

        # Fase 0.4: depois de ler conteudo de TERCEIROS, o turno esta contaminado (o texto pode
        # estar tentando mandar o LLM fazer algo). Ai o gate endurece:
        #  - o que cria persistencia/vazamento (agendar, macro, memorizar, imagem no visor...) sobe p/ critica;
        #  - critica pergunta SEMPRE: ignora o modo autonomo e a confianca no Telegram.
        fontes = fontes_contaminadas()
        if fontes and eleva_sob_contaminacao(ferramenta, argumentos):
            risco = Risco.CRITICA
        # B8: padrão de ofuscação/download-exec/alteração do sistema no comando: pergunta SEMPRE
        # (também no modo autônomo e via Telegram de confiança).
        from .shell_guard import sinais_da_chamada
        padroes = sinais_da_chamada(ferramenta, argumentos) if risco == Risco.CRITICA else []
        forcar = (bool(fontes) or bool(padroes)) and risco == Risco.CRITICA
        sufixo = f" | contaminado por: {', '.join(fontes)}" if fontes else ""
        if padroes:
            sufixo += f" | padrões de risco: {', '.join(padroes)}"

        if not forcar and not self.exige(risco):
            if risco != Risco.LEITURA:
                self._auditar(ferramenta, argumentos, risco, "liberado", origem, f"modo={self._modo}{sufixo}")
            return True, ""

        if origem == ORIGEM_AUTONOMO:
            self._auditar(ferramenta, argumentos, risco, "negado", origem, f"loop autônomo{sufixo}")
            return False, (
                "ação crítica não pode ser feita pelo loop autônomo sem o Matheus presente. "
                "NÃO tente de novo nem contorne por outra ferramenta."
            )

        if origem == ORIGEM_TELEGRAM and self.telegram_confiavel and not fontes and not padroes:
            self._auditar(ferramenta, argumentos, risco, "liberado", origem, "dono via Telegram")
            return True, ""

        if self._enviar is None:
            self._auditar(ferramenta, argumentos, risco, "negado", origem, f"sem canal de aprovação{sufixo}")
            return False, "não há canal para pedir a aprovação do Matheus. NÃO tente de novo."

        return await self._perguntar(ferramenta, argumentos, risco, origem, fontes)

    async def _perguntar(
        self, ferramenta: str, argumentos: Mapping[str, Any], risco: Risco, origem: str,
        fontes: Tuple[str, ...] = (),
    ) -> Tuple[bool, str]:
        aid = uuid.uuid4().hex[:12]
        pendente = _Pendente(
            id=aid,
            ferramenta=ferramenta,
            resumo=resumir(ferramenta, argumentos),
            risco=risco.value,
            origem=origem,
            criado=time.time(),
            futuro=asyncio.get_running_loop().create_future(),
            fontes=tuple(fontes),
        )
        self._pendentes[aid] = pendente

        try:
            alcancados = await self._enviar(self._evento_pedido(pendente))  # type: ignore[misc]
        except Exception as exc:
            logger.warning(f"[APROVACAO] Falha ao enviar pedido: {exc}")
            alcancados = 0

        if not alcancados:
            self._pendentes.pop(aid, None)
            self._auditar(ferramenta, argumentos, risco, "negado", origem, "nenhuma tela conectada")
            return False, (
                "nenhuma tela da Quinta está aberta para o Matheus confirmar. "
                "Diga isso a ele e NÃO tente de novo."
            )

        resultado = "expirou"
        try:
            permitido = await asyncio.wait_for(pendente.futuro, timeout=self.timeout_s)
            resultado = "aprovado" if permitido else "negado"
        except asyncio.TimeoutError:
            permitido = False
        except asyncio.CancelledError:
            resultado = "cancelado"
            await self._avisar_resolvido(aid, resultado)
            self._pendentes.pop(aid, None)
            raise
        finally:
            self._pendentes.pop(aid, None)

        await self._avisar_resolvido(aid, resultado)
        extra = f" | contaminado por: {', '.join(fontes)}" if fontes else ""
        self._auditar(ferramenta, argumentos, risco, resultado, origem, pendente.resumo[:200] + extra)
        if permitido:
            return True, ""
        motivo = (
            "o Matheus recusou" if resultado == "negado"
            else f"o Matheus não respondeu em {int(self.timeout_s)}s"
        )
        return False, f"{motivo}. NÃO tente de novo nem contorne por outra ferramenta; avise que não foi feito."

    def responder(self, approval_id: str, permitido: bool) -> bool:
        """Chamado quando chega `approval_response`. False se o pedido nao existe mais."""
        pendente = self._pendentes.get(str(approval_id))
        if not pendente or pendente.futuro.done():
            return False
        pendente.futuro.set_result(bool(permitido))
        return True

    # ----------------------------------------------------------------- eventos p/ a UI

    def _evento_pedido(self, p: _Pendente) -> Dict[str, Any]:
        return {
            "type": "approval_requested",
            "payload": {
                "approval_id": p.id,
                "ferramenta": p.ferramenta,
                "risco": p.risco,
                "resumo": p.resumo,
                "origem": p.origem,
                "expira_em_s": int(self.timeout_s),
                "criado_em": p.criado,
                # Conteudo de terceiros (WhatsApp, web...) foi lido antes deste pedido: a UI avisa.
                "contaminado": bool(p.fontes),
                "fontes": list(p.fontes),
            },
            "timestamp": _agora(),
            "request_id": p.id,
        }

    def eventos_pendentes(self) -> List[Dict[str, Any]]:
        """Pedidos ainda abertos — reenviados quando uma tela (re)conecta."""
        agora = time.time()
        eventos = []
        for p in self._pendentes.values():
            if agora - p.criado < self.timeout_s:
                ev = self._evento_pedido(p)
                ev["payload"]["expira_em_s"] = max(1, int(self.timeout_s - (agora - p.criado)))
                eventos.append(ev)
        return eventos

    async def _avisar_resolvido(self, aid: str, resultado: str) -> None:
        """Avisa todas as telas para fechar o cartao (outra aba respondeu, ou expirou)."""
        if self._enviar is None:
            return
        try:
            await self._enviar({
                "type": "approval_resolved",
                "payload": {"approval_id": aid, "resultado": resultado},
                "timestamp": _agora(),
                "request_id": aid,
            })
        except Exception:
            pass

    # ----------------------------------------------------------------- auditoria

    def _auditar(
        self, ferramenta: str, argumentos: Mapping[str, Any], risco: Risco,
        decisao: str, origem: str, motivo: str = "",
    ) -> None:
        """Uma linha JSONL por decisao (parametros sensiveis mascarados pelo ToolCallTelemetry)."""
        try:
            if self._telemetria is None:
                try:
                    from ..telemetry.audit_logger import AuditLogger, ToolCallTelemetry
                except ImportError:
                    from core.telemetry.audit_logger import AuditLogger, ToolCallTelemetry
                self._telemetria = ToolCallTelemetry(logger=AuditLogger(str(self._arq_auditoria)))
            self._telemetria.emit(
                tool_name=ferramenta,
                parameters=dict(argumentos),
                decision=decisao,
                duration_ms=0,
                success=decisao in ("aprovado", "liberado"),
                message=f"risco={risco.value} origem={origem} {motivo}".strip(),
            )
        except Exception as exc:
            logger.debug(f"[APROVACAO] Falha ao auditar: {exc}")


_instance: Optional[ApprovalBroker] = None


def get_broker() -> ApprovalBroker:
    global _instance
    if _instance is None:
        _instance = ApprovalBroker()
    return _instance
