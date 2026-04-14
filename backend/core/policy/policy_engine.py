"""
Policy Engine: contrato inicial de segurança para ações OS-level.

Implementa um controle de autorização simples e extensível para operações
sensíveis (execução de comando, manipulação de processo etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
import re
from typing import Dict, Iterable, Mapping, Optional, Sequence, Set


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
    Motor de política para decisões ALLOW/DENY.

    Estratégia atual (simples e explícita):
    - Se não houver regra para ação: DENY
    - Regras DENY têm prioridade
    - Para EXECUTE_POWERSHELL:
      - comando deve estar em allowlist (quando configurada)
      - não pode casar com blocklist regex
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
        """Lança PermissionError quando ação não for autorizada."""
        decision = self.evaluate(action, command=command, path=path, context=context)
        if not decision.allowed:
            raise PermissionError(decision.reason)

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


def create_default_policy_engine() -> PolicyEngine:
    """Factory padrão para bootstrap inicial."""
    workspace_root = Path.cwd().resolve()
    sandbox_data = workspace_root / ".runtime" / "sandbox"
    sandbox_data.mkdir(parents=True, exist_ok=True)

    sandbox_roots = {
        OSAction.FILE_READ: [str(sandbox_data)],
        OSAction.FILE_WRITE: [str(sandbox_data)],
        OSAction.FILE_LIST: [str(sandbox_data)],
        OSAction.FILE_DELETE: [str(sandbox_data)],
    }

    default_rules = [
        PolicyRule(
            action=OSAction.EXECUTE_POWERSHELL,
            effect=PolicyEffect.ALLOW,
            command_blocklist_regex=(
                r"\bformat\b",
                r"\bdel\s+/f\s+/s\b",
                r"\brd\s+/s\s+/q\b",
                r"\bRemove-Item\b.+-Recurse.+-Force",
                r"\bStop-Computer\b",
                r"\bRestart-Computer\b",
            ),
        ),
        PolicyRule(action=OSAction.PROCESS_LIST, effect=PolicyEffect.ALLOW),
        PolicyRule(action=OSAction.PROCESS_START, effect=PolicyEffect.ALLOW),
        PolicyRule(action=OSAction.PROCESS_STOP, effect=PolicyEffect.ALLOW),
        PolicyRule(action=OSAction.FILE_READ, effect=PolicyEffect.ALLOW),
        PolicyRule(action=OSAction.FILE_WRITE, effect=PolicyEffect.ALLOW),
        PolicyRule(action=OSAction.FILE_LIST, effect=PolicyEffect.ALLOW),
        PolicyRule(action=OSAction.FILE_DELETE, effect=PolicyEffect.ALLOW),
    ]
    return PolicyEngine(rules=default_rules, sandbox_roots=sandbox_roots)
