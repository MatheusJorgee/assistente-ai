"""
System Tool: o que está acontecendo no PC, com dados REAIS (somente leitura).

Antes, listar_processos e listar_servicos devolviam listas inventadas ("Simulação para teste") e
listar_arquivos mostrava só 10 itens. Agora tudo vem do sistema de verdade (psutil / os), e há
medição de uso de disco para responder "o que está ocupando espaço?".
"""

import asyncio
import datetime as _dt
import json
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ..tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from ..host import disk_usage as du
    from .. import get_logger
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from ..host import disk_usage as du
    from .. import get_logger

logger = get_logger(__name__)

ACOES = ["info_sistema", "discos", "uso_de_disco", "maiores_arquivos", "listar_processos",
         "listar_servicos", "listar_arquivos", "info_arquivo"]


def _fmt_itens_pastas(res: Dict[str, Any]) -> str:
    if res.get("erro"):
        return f"[ERRO] {res['erro']}"
    linhas = [f"Maiores itens em {res['raiz']}:"]
    for i in res["itens"]:
        linhas.append(f"  {du.formatar_bytes(i['bytes']):>10}  {i['nome']}" + ("  (medição parcial)" if i.get("parcial") else ""))
    if not res.get("completo"):
        linhas.append(f"[Prazo esgotado: valores parciais; ficaram sem medir/terminar: {', '.join(res.get('nao_medidas') or []) or 'algumas pastas'}."
                      " Para aprofundar, rode de novo numa subpasta ou com limite_s maior.]")
    return "\n".join(linhas)


def _fmt_arquivos(res: Dict[str, Any]) -> str:
    if not res["itens"]:
        return f"Nenhum arquivo grande em {res['raiz']}" + ("" if res["completo"] else " (busca parcial: prazo esgotado).")
    linhas = [f"Maiores arquivos em {res['raiz']}:"]
    linhas += [f"  {du.formatar_bytes(i['bytes']):>10}  {i['caminho']}" for i in res["itens"]]
    if not res["completo"]:
        linhas.append("[Prazo esgotado: pode haver arquivos maiores que não foram vistos.]")
    return "\n".join(linhas)


class SystemTool(MotorTool):
    """Consulta o sistema com dados reais."""

    def __init__(self):
        super().__init__(
            metadata=ToolMetadata(
                name="sistema",
                description=(
                    "Consulta o PC com dados REAIS (somente leitura, sem pedir aprovação). Use para: "
                    "'o que está ocupando espaço?' -> acao=uso_de_disco (pastas maiores; sem caminho = a sua "
                    "pasta de usuário; caminho='C:\\\\' para o disco todo) e acao=maiores_arquivos; "
                    "espaço livre das unidades -> acao=discos; processos e consumo -> acao=listar_processos; "
                    "serviços do Windows -> acao=listar_servicos; conteúdo de uma pasta -> listar_arquivos; "
                    "detalhes de um arquivo -> info_arquivo; visão geral (CPU, RAM, uptime) -> info_sistema. "
                    "Nunca invente números: rode a ação."
                ),
                category="system",
                parameters=[
                    ToolParameter(name="acao", type="string", description="Ação a executar", required=True, choices=ACOES),
                    ToolParameter(name="filtro", type="string", description="Filtro por nome (processos/serviços)", required=False, default=None),
                    ToolParameter(name="caminho", type="string", description="Pasta ou arquivo alvo", required=False, default=None),
                    ToolParameter(name="top", type="int", description="Quantos itens mostrar (padrão 15)", required=False, default=15),
                    ToolParameter(name="min_mb", type="int", description="maiores_arquivos: tamanho mínimo em MB (padrão 100)", required=False, default=100),
                    ToolParameter(name="limite_s", type="int", description="Tempo máximo da medição em segundos (padrão 40, máx 120)", required=False, default=40),
                ],
                examples=["acao=uso_de_disco", "acao=uso_de_disco, caminho=C:\\\\", "acao=maiores_arquivos, min_mb=500",
                          "acao=listar_processos", "acao=discos"],
                security_level=SecurityLevel.LOW,
                tags=["system", "disco", "processo"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        return str(kwargs.get("acao", "")).lower() in ACOES

    async def execute(self, **kwargs) -> str:
        acao = str(kwargs.get("acao", "")).lower()
        filtro = kwargs.get("filtro")
        caminho = kwargs.get("caminho")
        top = max(1, min(int(kwargs.get("top") or 15), 100))
        limite = max(5, min(int(kwargs.get("limite_s") or 40), 120))
        try:
            if acao == "info_sistema":
                return await asyncio.to_thread(self._info_sistema)
            if acao == "discos":
                return self._discos()
            if acao == "uso_de_disco":
                raiz = Path(caminho).expanduser() if caminho else Path.home()
                return _fmt_itens_pastas(await asyncio.to_thread(du.medir_pastas, raiz, top, float(limite)))
            if acao == "maiores_arquivos":
                raiz = Path(caminho).expanduser() if caminho else Path.home()
                min_b = max(1, int(kwargs.get("min_mb") or 100)) * 1024 * 1024
                return _fmt_arquivos(await asyncio.to_thread(du.maiores_arquivos, raiz, top, min_b, float(limite)))
            if acao == "listar_processos":
                return await asyncio.to_thread(self._listar_processos, filtro, top)
            if acao == "listar_servicos":
                return await asyncio.to_thread(self._listar_servicos, filtro)
            if acao == "listar_arquivos":
                return await asyncio.to_thread(self._listar_arquivos, caminho or ".", top if kwargs.get("top") else 50)
            if acao == "info_arquivo":
                if not caminho:
                    return "[ERRO] caminho é obrigatório para info_arquivo"
                return await asyncio.to_thread(self._info_arquivo, caminho)
            return f"[ERRO] Ação desconhecida: {acao}"
        except Exception as exc:
            logger.warning(f"[SYSTEM] {acao} falhou: {exc}")
            return f"[ERRO] {acao} falhou: {type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------ ações

    @staticmethod
    def _discos() -> str:
        discos = du.resumo_discos()
        if not discos:
            return "[ERRO] Não consegui ler as unidades de disco."
        return "\n".join(
            f"{d['unidade']}  total {du.formatar_bytes(d['total'])} | usado {du.formatar_bytes(d['usado'])} "
            f"({d['usado'] / d['total'] * 100:.0f}%) | livre {du.formatar_bytes(d['livre'])}" for d in discos
        )

    def _info_sistema(self) -> str:
        info: Dict[str, Any] = {
            "so": f"{platform.system()} {platform.release()} ({platform.version()})",
            "maquina": platform.machine(), "processador": platform.processor(), "python": platform.python_version(),
        }
        try:
            import psutil
            info["cpu_nucleos"] = psutil.cpu_count(logical=True)
            info["cpu_uso_pct"] = psutil.cpu_percent(interval=0.3)
            vm = psutil.virtual_memory()
            info["ram"] = f"{du.formatar_bytes(vm.used)} de {du.formatar_bytes(vm.total)} ({vm.percent:.0f}%)"
            info["ligado_ha"] = str(_dt.timedelta(seconds=int(_dt.datetime.now().timestamp() - psutil.boot_time())))
            bat = psutil.sensors_battery()
            if bat is not None:
                info["bateria"] = f"{bat.percent:.0f}% ({'na tomada' if bat.power_plugged else 'na bateria'})"
        except Exception:
            pass
        info["discos"] = self._discos().splitlines()
        return json.dumps(info, indent=2, ensure_ascii=False)

    @staticmethod
    def _listar_processos(filtro: Optional[str], top: int) -> str:
        import psutil
        alvo = (filtro or "").lower()
        linhas: List[Dict[str, Any]] = []
        for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
            try:
                nome = p.info.get("name") or ""
                if alvo and alvo not in nome.lower():
                    continue
                mem = p.info["memory_info"].rss if p.info.get("memory_info") else 0
                linhas.append({"pid": p.info["pid"], "nome": nome, "mem": mem})
            except Exception:
                continue
        linhas.sort(key=lambda x: x["mem"], reverse=True)
        cab = f"{len(linhas)} processo(s)" + (f" contendo '{filtro}'" if filtro else "") + f"; os {min(top, len(linhas))} que mais usam memória:"
        return "\n".join([cab] + [f"  {du.formatar_bytes(x['mem']):>10}  {x['nome']} (PID {x['pid']})" for x in linhas[:top]])

    @staticmethod
    def _listar_servicos(filtro: Optional[str]) -> str:
        if sys.platform != "win32":
            return "[ERRO] Serviços do Windows só existem no Windows."
        import psutil
        alvo = (filtro or "").lower()
        itens = []
        for s in psutil.win_service_iter():
            try:
                d = s.as_dict()
                if alvo and alvo not in d["name"].lower() and alvo not in (d.get("display_name") or "").lower():
                    continue
                itens.append(f"  {d['status']:<9} {d['name']} — {d.get('display_name', '')}")
            except Exception:
                continue
        return f"{len(itens)} serviço(s)" + (f" contendo '{filtro}'" if filtro else "") + ":\n" + "\n".join(itens[:60])

    @staticmethod
    def _info_arquivo(caminho: str) -> str:
        p = Path(caminho).expanduser()
        if not p.exists():
            return f"[ERRO] Caminho não encontrado: {caminho}"
        st = p.stat()
        info = {
            "caminho": str(p.resolve()), "tipo": "pasta" if p.is_dir() else "arquivo",
            "tamanho": du.formatar_bytes(st.st_size) if p.is_file() else "use acao=uso_de_disco para medir a pasta",
            "modificado": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        }
        return json.dumps(info, indent=2, ensure_ascii=False)

    @staticmethod
    def _listar_arquivos(caminho: str, limite: int) -> str:
        p = Path(caminho).expanduser()
        if not p.is_dir():
            return f"[ERRO] Não é uma pasta: {caminho}"
        itens = []
        for e in p.iterdir():
            try:
                itens.append((e.is_dir(), e.name, e.stat().st_size if e.is_file() else 0))
            except OSError:
                continue
        itens.sort(key=lambda x: (not x[0], x[1].lower()))
        linhas = [f"  {'[pasta]' if d else du.formatar_bytes(t):>10}  {n}" for d, n, t in itens[:limite]]
        extra = f"\n  ... e mais {len(itens) - limite}" if len(itens) > limite else ""
        return f"{len(itens)} item(ns) em {p}:\n" + "\n".join(linhas) + extra
