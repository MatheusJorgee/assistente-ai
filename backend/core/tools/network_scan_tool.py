"""
NetworkScanTool — descobre dispositivos ativos na rede local via TCP probe.

100% local, sem nmap nem chamadas externas.
Tenta portas comuns em cada host; retorna o primeiro que responder.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import time

try:
    from ..tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger

logger = get_logger(__name__)

_PROBE_PORTS = (80, 443, 22, 8080, 554, 7, 21)  # HTTP, HTTPS, SSH, alt-HTTP, RTSP, echo, FTP


class NetworkScanTool(MotorTool):
    """Escaneia a rede local e retorna IPs/hostnames ativos."""

    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="network_scan_local",
                description=(
                    "Escaneia a rede local e retorna dispositivos ativos com IP, "
                    "hostname e latência. Opera 100% local, sem chamadas externas."
                ),
                category="system",
                parameters=[
                    ToolParameter(
                        name="subnet",
                        type="string",
                        description=(
                            "CIDR da sub-rede (ex: '192.168.1.0/24'). "
                            "Use 'auto' para detectar automaticamente."
                        ),
                        required=False,
                        default="auto",
                    ),
                    ToolParameter(
                        name="timeout_ms",
                        type="int",
                        description="Timeout por host em milissegundos (padrão: 300).",
                        required=False,
                        default=300,
                    ),
                    ToolParameter(
                        name="resolve_hostnames",
                        type="bool",
                        description="Se True, tenta resolver nomes via DNS reverso.",
                        required=False,
                        default=True,
                    ),
                ],
                examples=[
                    "subnet=auto, timeout_ms=300",
                    "subnet=192.168.0.0/24, resolve_hostnames=False",
                ],
                security_level=SecurityLevel.MEDIUM,
                tags=["network", "scan", "local", "zero-trace"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        subnet = str(kwargs.get("subnet", "auto"))
        if subnet == "auto":
            return True
        try:
            ipaddress.ip_network(subnet, strict=False)
            return True
        except ValueError:
            return False

    async def execute(self, **kwargs) -> str:
        subnet = str(kwargs.get("subnet", "auto"))
        timeout_s = int(kwargs.get("timeout_ms", 300)) / 1000.0
        resolve = bool(kwargs.get("resolve_hostnames", True))

        if subnet == "auto":
            subnet = self._detect_subnet()

        hosts = list(ipaddress.ip_network(subnet, strict=False).hosts())
        tasks = [self._probe(str(h), timeout_s, resolve) for h in hosts]
        results = await asyncio.gather(*tasks)
        alive = [r for r in results if r]

        logger.info("[NETSCAN] %d/%d hosts ativos em %s", len(alive), len(hosts), subnet)
        return json.dumps(
            {"subnet": subnet, "total_scanned": len(hosts), "devices": alive},
            ensure_ascii=False,
            indent=2,
        )

    async def _probe(self, ip: str, timeout: float, resolve: bool) -> dict | None:
        for port in _PROBE_PORTS:
            try:
                t0 = time.monotonic()
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port), timeout=timeout
                )
                latency_ms = round((time.monotonic() - t0) * 1000, 1)
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

                hostname = ip
                if resolve:
                    try:
                        hostname = socket.gethostbyaddr(ip)[0]
                    except Exception:
                        pass

                return {"ip": ip, "hostname": hostname, "port": port, "latency_ms": latency_ms}
            except Exception:
                continue
        return None

    @staticmethod
    def _detect_subnet() -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        finally:
            s.close()
        prefix = local_ip.rsplit(".", 1)[0]
        return f"{prefix}.0/24"
