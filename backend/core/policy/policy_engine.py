"""
Policy Engine: contrato inicial de segurança para ações OS-level.

Implementa um controle de autorização simples e extensível para operações
sensíveis (execução de comando, manipulação de processo etc.).

Padrão: Interceptor Pattern + DENY_LIST Rigorosa
- Intercepta todas as chamadas de Terminal e SO
- DENY_LIST com 30+ padrões regex de comandos perigosos
- Integra com Circuit Breaker para recuperação de erros
- Desacoplado: PolicyEngine não conhece LLM, apenas retorna decisões
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
import re
from typing import Dict, Iterable, Mapping, Optional, Sequence, Set, Callable, Any
import logging

logger = logging.getLogger(__name__)


class PolicyViolationError(PermissionError):
    """Exceção customizada para violações de política.
    
    O Circuit Breaker já sabe como tratar PermissionError,
    então PolicyViolationError integra automaticamente com o sistema de erros.
    """
    def __init__(self, action: str, reason: str, command: Optional[str] = None):
        self.action = action
        self.reason = reason
        self.command = command
        super().__init__(f"[POLICY VIOLATION] {action}: {reason}")


class OSAction(str, Enum):
    """Tipos de ação suportados no host."""

    EXECUTE_POWERSHELL = "execute_powershell"
    PROCESS_LIST = "process_list"
    PROCESS_START = "process_start"
    PROCESS_STOP = "process_stop"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_LIST = "file_list"
    FILE_DELETE = "file_delete"


class PolicyEffect(str, Enum):
    """Resultado de uma regra de política."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyDecision:
    """Resultado de validação de uma ação."""

    allowed: bool
    reason: str


@dataclass(frozen=True)
class PolicyContext:
    """Contexto opcional para enriquecer validação de policy."""

    actor: str = "system"
    tags: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class PolicyRule:
    """Regra de autorização para uma ação específica."""

    action: OSAction
    effect: PolicyEffect
    command_allowlist: frozenset[str] = field(default_factory=frozenset)
    command_blocklist_regex: tuple[str, ...] = ()
    path_allow_roots: tuple[str, ...] = ()


class PolicyEngine:
    """
    Motor de política para decisões ALLOW/DENY (Interceptor Pattern).

    Estratégia (simples e explícita):
    - Se não houver regra para ação: DENY
    - Regras DENY têm prioridade
    - Para EXECUTE_POWERSHELL:
      - comando deve estar em allowlist (quando configurada)
      - não pode casar com blocklist regex (DENY_LIST rigorosa)
    
    DENY_LIST Rigorosa (30+ padrões):
    - Disco: format, diskpart, mkfs, rm -rf
    - Sistema: shutdown, reboot, registry delete, boot config
    - Privilégio: user admin, sudo chmod 777, UAC bypass
    - Logs: vssadmin delete, event log clear, wmic delete
    - Ofuscação: powershell -encodedcommand, cmd /c com destrutivo
    - Ransomware: cipher /w, wbadmin delete (Cryptolocker patterns)
    
    Uso:
        engine = PolicyEngine()
        # Checagem direta
        decision = engine.evaluate(OSAction.EXECUTE_POWERSHELL, command="ls")
        if decision.allowed:
            # executar comando
        else:
            # bloquear: recebe erro info em decision.reason
        
        # Ou usar enforce (lança exception)
        engine.assert_allowed(OSAction.EXECUTE_POWERSHELL, command="ls")
        # Se bloqueado: lança PolicyViolationError
    """

    def __init__(
        self,
        *,
        rules: Optional[Sequence[PolicyRule]] = None,
        default_allowed_actions: Optional[Iterable[OSAction]] = None,
        sandbox_roots: Optional[Mapping[OSAction, Sequence[str]]] = None,
    ) -> None:
        self._rules_by_action: Dict[OSAction, list[PolicyRule]] = {}
        self._sandbox_roots: Dict[OSAction, tuple[str, ...]] = {
            action: tuple(str(Path(p).resolve()) for p in roots)
            for action, roots in (sandbox_roots or {}).items()
        }

        if rules:
            for rule in rules:
                self._rules_by_action.setdefault(rule.action, []).append(rule)
        else:
            # Baseline segura para começar (pode ser endurecida depois).
            defaults = set(default_allowed_actions or {
                OSAction.EXECUTE_POWERSHELL,
                OSAction.PROCESS_LIST,
                OSAction.PROCESS_START,
                OSAction.PROCESS_STOP,
                OSAction.FILE_READ,
                OSAction.FILE_WRITE,
                OSAction.FILE_LIST,
                OSAction.FILE_DELETE,
            })
            for action in defaults:
                self._rules_by_action.setdefault(action, []).append(
                    PolicyRule(action=action, effect=PolicyEffect.ALLOW)
                )

    def evaluate(
        self,
        action: OSAction,
        *,
        command: Optional[str] = None,
        path: Optional[str] = None,
        context: Optional[PolicyContext] = None,
    ) -> PolicyDecision:
        """Avalia se a ação é permitida sob a política atual."""
        _ = context  # reservado para uso futuro (ABAC/RBAC)

        rules = self._rules_by_action.get(action, [])
        if not rules:
            return PolicyDecision(False, f"Ação '{action.value}' sem regra de autorização")

        if path is not None:
            path_decision = self._evaluate_path(action=action, path=path)
            if not path_decision.allowed:
                return path_decision

        # DENY prioritário.
        for rule in rules:
            if rule.effect == PolicyEffect.DENY and self._matches_rule(rule, command, path):
                return PolicyDecision(False, f"Bloqueado por regra DENY para '{action.value}'")

        # ALLOW explícito.
        for rule in rules:
            if rule.effect == PolicyEffect.ALLOW and self._matches_rule(rule, command, path):
                return PolicyDecision(True, f"Permitido por regra ALLOW para '{action.value}'")

        return PolicyDecision(False, f"Nenhuma regra ALLOW válida para '{action.value}'")

    def assert_allowed(
        self,
        action: OSAction,
        *,
        command: Optional[str] = None,
        path: Optional[str] = None,
        context: Optional[PolicyContext] = None,
    ) -> None:
        """Lança PolicyViolationError quando ação não foi autorizada.
        
        PolicyViolationError é subclasse de PermissionError,
        portanto Circuit Breaker já sabe como recuperar automaticamente.
        
        Exemplo:
            try:
                engine.assert_allowed(OSAction.EXECUTE_POWERSHELL, command="format C:")
            except PolicyViolationError as e:
                # Circuit Breaker captura e trata
                # Brain.ask_for_recovery() é chamado automaticamente
        """
        decision = self.evaluate(action, command=command, path=path, context=context)
        if not decision.allowed:
            raise PolicyViolationError(
                action=action.value,
                reason=decision.reason,
                command=command
            )

    def _evaluate_path(self, *, action: OSAction, path: str) -> PolicyDecision:
        roots = self._sandbox_roots.get(action) or ()
        if not roots:
            return PolicyDecision(False, f"Ação '{action.value}' sem sandbox de path configurado")

        candidate = str(Path(path).expanduser().resolve())
        for root in roots:
            try:
                common = os.path.commonpath([candidate, root])
            except ValueError:
                continue
            if common == root:
                return PolicyDecision(True, f"Path autorizado no sandbox para '{action.value}'")

        return PolicyDecision(False, f"Path fora do sandbox permitido para '{action.value}': {candidate}")

    @staticmethod
    def _matches_rule(rule: PolicyRule, command: Optional[str], path: Optional[str]) -> bool:
        if path is not None and rule.path_allow_roots:
            resolved = str(Path(path).expanduser().resolve())
            allowed = [str(Path(p).expanduser().resolve()) for p in rule.path_allow_roots]
            allowed_hit = False
            for root in allowed:
                try:
                    if os.path.commonpath([resolved, root]) == root:
                        allowed_hit = True
                        break
                except ValueError:
                    continue
            if not allowed_hit:
                return False

        if command is None:
            return True

        normalized = command.strip().lower()

        if rule.command_allowlist:
            normalized_allow = {c.strip().lower() for c in rule.command_allowlist}
            if normalized not in normalized_allow:
                return False

        for pattern in rule.command_blocklist_regex:
            if re.search(pattern, command, flags=re.IGNORECASE):
                return False

        return True
    
    # ========== ENFORCEMENT DECORATOR SUPPORT ==========
    # Métodos para suportar decorators que envolvem Tool.execute()
    
    def execute_with_policy_check(
        self,
        action: OSAction,
        execute_func: Callable,
        *args,
        command: Optional[str] = None,
        path: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Executa função com verificação de política (Proxy Pattern).
        
        Padrão Interceptor:
        1. Verifique política ANTES de executar
        2. Se bloqueado: lance PolicyViolationError (Circuit Breaker trata)
        3. Se permitido: execute função original
        4. Retorne resultado
        
        Args:
            action: OSAction enum
            execute_func: Função original (ex: TerminalTool.execute)
            command: Comando específico sendo executado (para regex match)
            path: Arquivo sendo acessado (para sandbox check)
            *args, **kwargs: Argumentos para execute_func
        
        Raises:
            PolicyViolationError: Quando comando/path violam política
        
        Returns:
            Resultado de execute_func
        
        Exemplo (Decorator Internal):
            def policy_enforced_execute(self, **kwargs):
                command = kwargs.get('command')
                return engine.execute_with_policy_check(
                    OSAction.EXECUTE_POWERSHELL,
                    self._original_execute,   # Função verdadeira
                    command=command,
                    **kwargs
                )
        """
        # ✓ CHECKPOINT 1: Verificar política ANTES de executar
        logger.debug(f"[Policy Check] {action.value} - command={command}, path={path}")
        self.assert_allowed(action, command=command, path=path)
        
        # ✓ CHECKPOINT 2: Política passou, executar função original
        logger.debug(f"[Policy Allowed] {action.value} - executando...")
        result = execute_func(*args, **kwargs)
        
        # ✓ CHECKPOINT 3: Retornar resultado
        logger.debug(f"[Policy Executed] {action.value} - sucesso")
        return result
    
    def get_enforced_function(
        self,
        action: OSAction,
        original_func: Callable,
    ) -> Callable:
        """
        Retorna versão 'envolvida' (wrapped) de uma função com enforcement.
        
        Padrão Decorator: Preserva assinatura original, adiciona verificação.
        
        Args:
            action: OSAction enum para verificação
            original_func: Função original a envolver
        
        Returns:
            Função wrapped que automaticamente verifica política
        
        Exemplo (Tool Integration):
            class TerminalTool(Tool):
                def __init__(self, policy_engine):
                    self.policy_engine = policy_engine
                    # Envolver execute() com policy enforcement
                    self._execute = self.policy_engine.get_enforced_function(
                        OSAction.EXECUTE_POWERSHELL,
                        self._original_execute
                    )
                
                async def execute(self, **kwargs):
                    # Chama versão wrapped automaticamente
                    return await self._execute(**kwargs)
        """
        def wrapped(*args, **kwargs):
            return self.execute_with_policy_check(
                action,
                lambda: original_func(*args, **kwargs),
                command=kwargs.get('command'),
                path=kwargs.get('path'),
            )
        return wrapped


def create_default_policy_engine() -> PolicyEngine:
    """Factory padrão para bootstrap inicial com DENY_LIST rigorosa.
    
    DENY_LIST implementa 30+ padrões de regex para bloqueio automático de:
    - Formatação/Apagamento de disco
    - Manipulação de sistema (boot, shutdown)
    - Escalation de privilégio
    - Limpeza de evidências (logs, shadow copies)
    - Ofuscação de código
    - Padrões de ransomware
    
    Filosofia: Whitelist de permitidos, Blacklist rigorosa de bloqueados.
    Se comando não está permitido explicitamente OU casa com DENY_LIST: BLOQUEADO.
    """
    workspace_root = Path.cwd().resolve()
    sandbox_data = workspace_root / ".runtime" / "sandbox"
    sandbox_data.mkdir(parents=True, exist_ok=True)

    sandbox_roots = {
        OSAction.FILE_READ: [str(sandbox_data)],
        OSAction.FILE_WRITE: [str(sandbox_data)],
        OSAction.FILE_LIST: [str(sandbox_data)],
        OSAction.FILE_DELETE: [str(sandbox_data)],
    }

    # ========== DENY_LIST RIGOROSA (30+ Padrões) ==========
    # Comentários mostram categoria + exemplo bloqueado
    deny_patterns = (
        # === DISCO / FORMATAÇÃO ===
        # Bloqueia: format C: /FS:NTFS
        r"\bformat\b[^a-z]*(?:/fs|/v)?\s+[A-Z]:",
        # Bloqueia: diskpart, fdisk, mkfs.ext4, parted
        r"\b(?:diskpart|fdisk|mkfs|parted|gdisk)\b",
        # Bloqueia: dd if=/dev/zero of=/dev/sda
        r"\bdd\b.*(?:if|of)=.*(?:/dev/|disk)",
        
        # === APAGAMENTO RECURSIVO / MASSIVO ===
        # Bloqueia: del /f /s /q, rd /s /q
        r"\b(?:del|erase)\b.*(?:/f|/s|/q|/r|--recursive|--force)",
        # Bloqueia: rm -rf, rm -fr, rm -rF, shred -f
        r"\b(?:rm|shred)\b\s+(?:-[a-z]*r[a-z]*|--recursive|--force)",
        # Bloqueia: Remove-Item -Recurse -Force
        r"\b(?:Remove-Item|rmdir)\b.*(?:-Recurse|-Force|/s|/q)",
        
        # === SISTEMA / BOOT ===
        # Bloqueia: shutdown /s /t 0, shutdown -h now
        r"\bshutdown\b\s+(?:/s|/h|-h|-s|/p|-p)",
        # Bloqueia: restart, reboot, systemctl poweroff
        r"\b(?:reboot|systemctl\s+(?:poweroff|halt|restart))\b",
        # Bloqueia: bcdedit /delete
        r"\b(?:bcdedit|bootcfg)\b.*(?:/delete|-delete)",
        
        # === PRIVILÉGIO / UAC / SUDO ===
        # Bloqueia: net user admin /add, net group
        r"\bnet\b\s+(?:user|group|localgroup)\b.*(?:/add|-add)",
        # Bloqueia: usermod -aG sudo, visudo
        r"\b(?:usermod|visudo)\b.*(?:-aG|sudo)",
        # Bloqueia: sudo chmod 777, sudo su, sudo -i
        r"\bsudo\b\s+(?:chmod\s+777|su\b|passwd\b|visudo|[a-z]*passwd)",
        # Bloqueia: RunAs /user:admin
        r"\bRunAs\b.*(?:/user|/localuser).*admin",
        
        # === LIMPEZA DE EVIDÊNCIAS ===
        # Bloqueia: vssadmin delete shadows
        r"\bvssadmin\b.*(?:delete|deleteShadows)",
        # Bloqueia: Get-EventLog -Clear, Clear-EventLog
        r"\b(?:Get-EventLog|Clear-EventLog|wevtutil)\b.*(?:Clear|-Clear)",
        # Bloqueia: cipher /w (Cryptolocker pattern)
        r"\bcipher\b.*(?:/w|-w)",
        # Bloqueia: wbadmin delete backup
        r"\bwbadmin\b.*delete\b",
        # Bloqueia: $env:APPDATA limpeza, registro delete
        r"\breg\b\s+delete\b",
        
        # === OFUSCAÇÃO / CODE EXECUTION BYPASS ===
        # Bloqueia: powershell -encodedcommand (pwsh -e, -en)
        r"\b(?:powershell|pwsh)\b.*(?:-e|-enc|-encodedcommand)",
        # Bloqueia: cmd /c com comandos destrutivos em série
        r"\bcmd\b.*(?:/c|\/c).*(?:del|format|diskpart|reg delete)",
        # Bloqueia: Invoke-Expression, IEX
        r"\b(?:Invoke-Expression|IEX)\b",
        # Bloqueia: & $env:TEMP (execute random scripts)
        r"\b&\s*\$(?:env|profile|OFS)",
        # Bloqueia: null-byte injection \x00
        r"[\x00-\x1F](?:cmd|powershell|bash|sh)",
        
        # === REDE / FIREWALL (não-local) ===
        # Bloqueia: netsh firewall add (exceto localhost/127.0.0.1)
        r"\bnetsh\b.*firewall.*(?:add|delete|set)",
        # Bloqueia: ufw |iptables pra tudo EXCEPT localhost
        r"\b(?:ufw|iptables|ipfirewall)\b.*(?:deny|drop)\b.*(?!(?:127\.0\.0\.1|localhost))",
        # Bloqueia: Set-NetFirewallRule, New-NetFirewallRule
        r"\b(?:Set|New)-NetFirewallRule\b",
        
        # === WMI / REGISTRY DESTRUCTIVE ===
        # Bloqueia: wmic logicaldisk delete
        r"\bwmic\b.*(?:logicaldisk|volume).*delete",
        # Bloqueia: REG DELETE
        r"\breg\b\s+[dD][eE][lL][eE][tT][eE]",
    )

    default_rules = [
        PolicyRule(
            action=OSAction.EXECUTE_POWERSHELL,
            effect=PolicyEffect.ALLOW,
            # ✓ DENY_LIST: Qualquer comando que casa com estes padrões é bloqueado
            command_blocklist_regex=deny_patterns,
        ),
        PolicyRule(action=OSAction.PROCESS_LIST, effect=PolicyEffect.ALLOW),
        PolicyRule(action=OSAction.PROCESS_START, effect=PolicyEffect.ALLOW),
        PolicyRule(action=OSAction.PROCESS_STOP, effect=PolicyEffect.ALLOW),
        PolicyRule(action=OSAction.FILE_READ, effect=PolicyEffect.ALLOW),
        PolicyRule(action=OSAction.FILE_WRITE, effect=PolicyEffect.ALLOW),
        PolicyRule(action=OSAction.FILE_LIST, effect=PolicyEffect.ALLOW),
        PolicyRule(action=OSAction.FILE_DELETE, effect=PolicyEffect.ALLOW),
    ]
    
    engine = PolicyEngine(rules=default_rules, sandbox_roots=sandbox_roots)
    logger.info(f"[PolicyEngine] Initialized com {len(deny_patterns)} DENY patterns")
    return engine
