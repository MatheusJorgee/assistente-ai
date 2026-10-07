"""
Cliente MCP mínimo (JSON-RPC 2.0 por stdio), sem dependência externa.

MCP (Model Context Protocol) é o padrão para plugar ferramentas de terceiros (navegador, arquivos,
calendário, repositórios...). Aqui só o necessário: initialize, tools/list e tools/call.

Segurança:
  - o servidor só sobe se VOCÊ o listou em .runtime/mcp.json (o modelo não adiciona servidores);
  - o ambiente do processo é o mínimo (build_env): sem GEMINI_API_KEY nem tokens, a não ser o que o
    seu mcp.json der explicitamente àquele servidor;
  - mensagens e saídas têm teto de tamanho e toda chamada tem prazo (servidor travado não trava a Quinta);
  - servidor que cai é reiniciado no máximo 2 vezes por hora.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

PROTOCOLO = "2024-11-05"
MSG_MAX = 1024 * 1024        # linha JSON máxima vinda do servidor
SAIDA_MAX = 20_000            # caracteres devolvidos ao modelo por chamada
REINICIOS_POR_HORA = 2


class ErroMCP(Exception):
    pass


class ServidorMCP:
    def __init__(self, nome: str, comando: str, args: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None, timeout_s: float = 30.0, cwd: Optional[str] = None) -> None:
        self.nome = nome
        self.comando = comando
        self.args = list(args or [])
        self.env_extra = dict(env or {})
        self.timeout_s = max(1.0, min(float(timeout_s), 300.0))
        self.cwd = cwd
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._leitor: Optional[asyncio.Task] = None
        self._pendentes: Dict[int, asyncio.Future] = {}
        self._prox_id = 1
        self._reinicios: List[float] = []
        self._morto = False   # o leitor viu o fim da saída (o servidor caiu)
        self.ferramentas: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ ciclo de vida

    @property
    def vivo(self) -> bool:
        return self._proc is not None and self._proc.returncode is None and not self._morto

    async def iniciar(self) -> None:
        from ..host.safe_env import build_env
        env = build_env()
        env.update(self.env_extra)   # só o que o SEU mcp.json deu a este servidor
        self._morto = False
        self._proc = await asyncio.create_subprocess_exec(
            self.comando, *self.args,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env=env, cwd=self.cwd, limit=MSG_MAX,
        )
        self._leitor = asyncio.create_task(self._ler_saida())
        await self._requisitar("initialize", {
            "protocolVersion": PROTOCOLO, "capabilities": {},
            "clientInfo": {"name": "quinta-feira", "version": "1.0"},
        }, prazo=self.timeout_s)
        await self._notificar("notifications/initialized", {})

    async def parar(self) -> None:
        if self._leitor:
            self._leitor.cancel()
        proc = self._proc
        self._proc = None
        if proc and proc.stdin:
            try:
                proc.stdin.close()   # fecha o pipe primeiro: servidor bem-comportado sai sozinho
            except Exception:
                pass
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._falhar_pendentes(ErroMCP("servidor parado"))

    async def _garantir(self) -> None:
        if self.vivo:
            return
        agora = time.time()
        self._reinicios = [t for t in self._reinicios if agora - t < 3600]
        if len(self._reinicios) >= REINICIOS_POR_HORA:
            raise ErroMCP(f"o servidor '{self.nome}' caiu vezes demais; desativado até a próxima hora")
        self._reinicios.append(agora)
        await self.parar()
        await self.iniciar()

    # ------------------------------------------------------------------ protocolo

    async def _ler_saida(self) -> None:
        assert self._proc and self._proc.stdout
        try:
            while True:
                linha = await self._proc.stdout.readline()
                if not linha:
                    break
                try:
                    msg = json.loads(linha)
                except ValueError:
                    continue
                if isinstance(msg, dict) and "id" in msg and ("result" in msg or "error" in msg):
                    fut = self._pendentes.pop(msg["id"], None) if isinstance(msg["id"], int) else None
                    if fut and not fut.done():
                        fut.set_result(msg)
        except (asyncio.CancelledError, ValueError):
            pass
        except Exception:
            pass
        finally:
            self._morto = True
            self._falhar_pendentes(ErroMCP(f"o servidor '{self.nome}' encerrou"))

    def _falhar_pendentes(self, exc: Exception) -> None:
        for fut in list(self._pendentes.values()):
            if not fut.done():
                fut.set_exception(exc)
        self._pendentes.clear()

    async def _enviar(self, obj: Dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise ErroMCP("servidor não iniciado")
        self._proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def _notificar(self, metodo: str, params: Dict[str, Any]) -> None:
        await self._enviar({"jsonrpc": "2.0", "method": metodo, "params": params})

    async def _requisitar(self, metodo: str, params: Dict[str, Any], prazo: Optional[float] = None) -> Any:
        rid = self._prox_id
        self._prox_id += 1
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pendentes[rid] = fut
        try:
            await self._enviar({"jsonrpc": "2.0", "id": rid, "method": metodo, "params": params})
            msg = await asyncio.wait_for(fut, timeout=prazo or self.timeout_s)
        except asyncio.TimeoutError:
            self._pendentes.pop(rid, None)
            # Servidor ocupado/travado: derruba, senão a PRÓXIMA chamada ficaria presa atrás desta.
            await self.parar()
            raise ErroMCP(f"'{metodo}' passou de {int(prazo or self.timeout_s)}s sem resposta")
        except (BrokenPipeError, ConnectionResetError):
            raise ErroMCP(f"o servidor '{self.nome}' fechou a conexão")
        if "error" in msg:
            err = msg["error"] if isinstance(msg["error"], dict) else {}
            raise ErroMCP(str(err.get("message") or "erro do servidor")[:300])
        return msg.get("result")

    # ------------------------------------------------------------------ uso

    async def listar_ferramentas(self) -> List[Dict[str, Any]]:
        await self._garantir()
        res = await self._requisitar("tools/list", {})
        itens = res.get("tools") if isinstance(res, dict) else None
        self.ferramentas = [t for t in (itens if isinstance(itens, list) else []) if isinstance(t, dict) and isinstance(t.get("name"), str)]
        return self.ferramentas

    async def chamar(self, ferramenta: str, argumentos: Dict[str, Any], prazo: Optional[float] = None) -> str:
        """Texto devolvido pela ferramenta (cortado). Erros viram ErroMCP."""
        await self._garantir()
        res = await self._requisitar("tools/call", {"name": ferramenta, "arguments": argumentos}, prazo=prazo)
        partes: List[str] = []
        for c in (res.get("content") if isinstance(res, dict) else None) or []:
            if isinstance(c, dict) and c.get("type") == "text":
                partes.append(str(c.get("text", "")))
            elif isinstance(c, dict):
                partes.append(f"[conteúdo do tipo {c.get('type', '?')} omitido]")
        texto = "\n".join(partes).strip() or "(sem saída)"
        if len(texto) > SAIDA_MAX:
            texto = texto[:SAIDA_MAX] + f"\n[saída cortada em {SAIDA_MAX} caracteres]"
        if isinstance(res, dict) and res.get("isError"):
            raise ErroMCP(texto[:500])
        return texto
