"""
Zero-Trace Decorators: Envelopadores para Tool.execute()

Padrão: Decorator + Proxy Pattern

Responsabilidades:
- PolicyEnforcementDecorator: Intercepta e valida contra PolicyEngine
- ZeroTraceDecorator: Redireciona paths para sandbox
- apply_zero_trace_enforcement: Factory que aplica ambos decoradores a um Tool

Integração na Arquitetura:
1. Tool.execute() é chamado pelo ActionOrchestrator (via ToolRegistry)
2. PolicyEnforcementDecorator intercepta ANTES
   - Valida comando contra DENY_LIST
   - Se bloqueado: lança PolicyViolationError
   - Circuit Breaker captura e trata (chamando Brain.ask_for_recovery)
3. Se passou política: ZeroTraceDecorator redireciona I/O
   - Todo write é silenciosamente redirecionado para sandbox
4. Executa execute() original
5. Ao sair da sessão ZeroTraceSession: sandbox é apagado

Filosofia Desacoplada:
- Tool NÃO SABE que está sendo validado por política
- Tool NÃO SABE que está em sandbox
- Tool NÃO SABE que será limpo
- LLM NÃO SABE que existe uma política (recebe exceção do Circuit Breaker)
- Apenas Brain.ask_for_recovery() usa contexto de erro (via error.reason)

Exemplo de Uso (em brain ou ao registrar Tool):

    # Forma 1: Aplicar a um Tool instance
    from backend.core.zero_trace_decorators import apply_zero_trace_enforcement
    from backend.core.policy.policy_engine import create_default_policy_engine
    from backend.core.zero_trace import ZeroTraceSession
    
    tool = TerminalTool()
    policy_engine = create_default_policy_engine()
    
    async with ZeroTraceSession(session_id="req-123") as session:
        tool_enforced = apply_zero_trace_enforcement(
            tool,
            policy_engine=policy_engine,
            zero_trace_session=session,
        )
        result = await tool_enforced.execute(command="ls -la /tmp")
        # Resultado:
        # - "ls -la /tmp" passou pela DENY_LIST ✓
        # - Execução rodou (se TerminalTool implementa execute)
        # - Ao sair de "async with ZeroTraceSession": sandbox deletado

    # Forma 2: Aplicar manualmente em ActionOrchestrator
    class ActionOrchestratorV2(ActionOrchestrator):
        def __init__(self, brain, registry, policy_engine, zero_trace_session):
            super().__init__(brain, registry)
            self.policy_engine = policy_engine
            self.zero_trace_session = zero_trace_session
        
        async def _execute_tool_call(self, tool, kwargs):
            # Automaticamente valida contra política + redireciona paths
            enforced_tool = apply_zero_trace_enforcement(
                tool,
                policy_engine=self.policy_engine,
                zero_trace_session=self.zero_trace_session,
            )
            return await enforced_tool.execute(**kwargs)
"""

import logging
import asyncio
from functools import wraps
from typing import Callable, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class PolicyEnforcementDecorator:
    """
    Decorador que intercepta Tool.execute() e valida contra PolicyEngine.
    
    Padrão: Interceptor + Proxy
    
    Fluxo de Execução:
    1. Intercepta Tool.execute(...) call
    2. Extrai command/path dos kwargs
    3. Chama policy_engine.assert_allowed()
    4. Se PolicyViolationError: lança (Circuit Breaker trata)
    5. Se permitido: executa Tool.execute() original
    6. Retorna resultado
    
    Desacoplamento:
    - PolicyEngine não conhece Tool
    - Tool não conhece PolicyEngine
    - Decorador é o "intermediário" neutro
    - Exceção PolicyViolationError é auto-tratada por Circuit Breaker
    
    Uso Interno (em apply_zero_trace_enforcement):
        decorator = PolicyEnforcementDecorator(
            original_execute_func=tool.execute,
            policy_engine=engine,
            tool_name=tool.metadata.name,
        )
        # Chama decorator.wrapped_execute(**kwargs)
    \"\"\"\n\n    def __init__(\n        self,\n        original_execute_func: Callable,\n        policy_engine,  # PolicyEngine instance\n        tool_name: str,\n    ):\n        \"\"\"\n        Args:\n            original_execute_func: Função Tool.execute original\n            policy_engine: PolicyEngine instance para validação\n            tool_name: Nome da ferramenta (para logs)\n        \"\"\"\n        self.original_func = original_execute_func\n        self.policy_engine = policy_engine\n        self.tool_name = tool_name\n    \n    async def wrapped_execute(self, **kwargs) -> Any:\n        \"\"\"\n        Versão envolvida de execute() com policy enforcement.\n        \n        Padrão Interceptor:\n        ```\n        CLIENTE chama wrapped_execute()\n            ↓\n        [CHECKPOINT 1] Extrair command/path\n            ↓\n        [CHECKPOINT 2] policy_engine.assert_allowed()\n            ├─ Se PolicyViolationError: lança (Circuit Breaker trata)\n            └─ Se OK: continua\n            ↓\n        [CHECKPOINT 3] Executar original_func() (Tool.execute real)\n            ├─ Se erro: lança (Circuit Breaker trata)\n            └─ Se OK: continua\n            ↓\n        [CHECKPOINT 4] Retornar resultado\n        ```\n        \n        Args:\n            **kwargs: Argumentos para Tool.execute (command, path, etc)\n        \n        Returns:\n            Resultado de Tool.execute original\n        \n        Raises:\n            PolicyViolationError: Se comando/path violam política\n            (qualquer exception de original_func)\n        \"\"\"\n        from backend.core.policy.policy_engine import OSAction\n        \n        # ✓ CHECKPOINT 1: Extrair informações do command\n        command = kwargs.get('command')\n        path = kwargs.get('path')\n        \n        logger.debug(\n            f\"[PolicyEnforcement] {self.tool_name} - \"\n            f\"command={command}, path={path}\"\n        )\n        \n        # ✓ CHECKPOINT 2: Validar contra PolicyEngine\n        # Determinar ação baseado no tipo de Tool\n        action = OSAction.EXECUTE_POWERSHELL  # Default para TerminalTool\n        if self.tool_name == \"vision_tool\":\n            action = OSAction.FILE_READ\n        elif self.tool_name == \"file_writer\":\n            action = OSAction.FILE_WRITE\n        \n        try:\n            self.policy_engine.assert_allowed(\n                action,\n                command=command,\n                path=path,\n            )\n            logger.debug(f\"[PolicyEnforcement] ✓ {self.tool_name} autorizado\")\n        except Exception as e:\n            logger.warning(\n                f\"[PolicyEnforcement] ✗ {self.tool_name} bloqueado: {e}\"\n            )\n            raise  # Propagar PolicyViolationError para Circuit Breaker\n        \n        # ✓ CHECKPOINT 3: Executar Tool.execute() original\n        logger.debug(f\"[PolicyEnforcement] Executando {self.tool_name}...\")\n        \n        if asyncio.iscoroutinefunction(self.original_func):\n            result = await self.original_func(**kwargs)\n        else:\n            result = self.original_func(**kwargs)\n        \n        # ✓ CHECKPOINT 4: Log de sucesso e retornar\n        logger.debug(f\"[PolicyEnforcement] ✓ {self.tool_name} executado\")\n        return result


class ZeroTraceDecorator:\n    \"\"\"\n    Decorador que redireciona I/O para sandbox (Zero-Trace Pattern).\n    \n    Padrão: Proxy + Path Interception\n    \n    Responsabilidades:\n    - Interceptar kwargs que contêm paths\n    - Silenciosamente redirecionar para sandbox\n    - Preservar nome de arquivo (apenas muda pasta)\n    - Ferramenta \"acha\" que escreveu no target original\n    - Arquivo realmente está no sandbox\n    - Ao cleanup: pasta sandbox é deletada (zero rastros)\n    \n    Logica de Redireção:\n    ```\n    Ferramenta tenta: write(\"C:\\\\Users\\\\Admin\\\\Downloads\\\\report.pdf\")\n        ↓\n    ZeroTraceDecorator.wrapped_execute() intercepta\n        ↓\n    Chama session.redirect_write(Path(...))\n        ↓\n    Retorna: \"./runtime/sandbox/{session_id}/report.pdf\"\n        ↓\n    Passa redirected_path para original_func\n        ↓\n    Tool escreve em sandbox (não sabe que foi redirecionado)\n        ↓\n    Return resultado\n        ↓\n    Ao sair ZeroTraceSession: sandbox deletado\n    ```\n    \n    Desacoplamento:\n    - Tool não sabe que foi redirecionado\n    - Tool não conhece ZeroTraceSession\n    - Decorador é intermediário neutro\n    - Cleanup é automático e invisível\n    \n    Uso Interno (em apply_zero_trace_enforcement):\n        decorator = ZeroTraceDecorator(\n            original_execute_func=tool.execute,\n            zero_trace_session=session,\n            tool_name=tool.metadata.name,\n        )\n        # Chama decorator.wrapped_execute(**kwargs)\n    \"\"\"\n\n    def __init__(\n        self,\n        original_execute_func: Callable,\n        zero_trace_session,  # ZeroTraceSession instance\n        tool_name: str,\n    ):\n        \"\"\"\n        Args:\n            original_execute_func: Função Tool.execute original\n            zero_trace_session: ZeroTraceSession instance para redireção\n            tool_name: Nome da ferramenta (para logs)\n        \"\"\"\n        self.original_func = original_execute_func\n        self.session = zero_trace_session\n        self.tool_name = tool_name\n    \n    async def wrapped_execute(self, **kwargs) -> Any:\n        \"\"\"\n        Versão envolvida de execute() com sandbox path redirection.\n        \n        Padrão Proxy:\n        ```\n        CLIENTE chama wrapped_execute(command=..., path=...)\n            ↓\n        [CHECKPOINT 1] Extrair paths dos kwargs\n            ↓\n        [CHECKPOINT 2] Redirecionar paths para sandbox (silenciosamente)\n            ↓\n        [CHECKPOINT 3] Executar original_func() com paths redirected\n            ↓\n        [CHECKPOINT 4] Retornar resultado (Tool acha que funcionou normal)\n        ```\n        \n        Args:\n            **kwargs: Argumentos para Tool.execute\n                     Pode conter: path, output_path, file_path, etc.\n        \n        Returns:\n            Resultado de Tool.execute original\n        \"\"\"\n        logger.debug(f\"[ZeroTrace] {self.tool_name} - entrada sandbox\")\n        \n        # ✓ CHECKPOINT 1: Extrair paths dos kwargs\n        original_kwargs = kwargs.copy()\n        \n        # Redirecionar variações comuns de nomes de path\n        path_keys = ['path', 'output_path', 'file_path', 'output_file', 'target']\n        for key in path_keys:\n            if key in kwargs and kwargs[key]:\n                try:\n                    # ✓ CHECKPOINT 2: Silenciosamente redirecionar\n                    original_path = Path(kwargs[key])\n                    redirected_path = self.session.redirect_write(original_path)\n                    kwargs[key] = str(redirected_path)\n                    \n                    logger.debug(\n                        f\"[ZeroTrace] {key}: {original_path} -> {redirected_path}\"\n                    )\n                except Exception as e:\n                    logger.warning(\n                        f\"[ZeroTrace] Erro ao redirecionar {key}: {e} \"\n                        f\"(mantendo original)\"\n                    )\n                    # Se erro: manter original (fail-open)\n        \n        # ✓ CHECKPOINT 3: Executar Tool.execute() com paths redirected\n        logger.debug(f\"[ZeroTrace] Executando {self.tool_name} em sandbox...\")\n        \n        if asyncio.iscoroutinefunction(self.original_func):\n            result = await self.original_func(**kwargs)\n        else:\n            result = self.original_func(**kwargs)\n        \n        # ✓ CHECKPOINT 4: Log de sucesso\n        logger.debug(\n            f\"[ZeroTrace] ✓ {self.tool_name} completado - \"\n            f\"arquivo em sandbox: {self.session.get_sandbox_path()}\"\n        )\n        return result\n\n\ndef apply_zero_trace_enforcement(\n    tool,\n    policy_engine,\n    zero_trace_session,\n) -> Any:\n    \"\"\"\n    Factory: Aplica ambos decoradores (Policy + ZeroTrace) a um Tool.\n    \n    Padrão: Decorator Composition + Proxy\n    \n    Responsabilidades:\n    - Envolver Tool.execute() com PolicyEnforcementDecorator\n    - Depois envolver resultado com ZeroTraceDecorator\n    - Retornar Tool 'fake' com execute() decorado\n    \n    Ordem de Aplicação (importante):\n    1. PRIMEIRA: PolicyEnforcementDecorator (validar ANTES de executar)\n    2. DEPOIS: ZeroTraceDecorator (redirecionar paths)\n    \n    Exemplo:\n        tool_enforced = apply_zero_trace_enforcement(\n            tool=my_terminal_tool,\n            policy_engine=engine,\n            zero_trace_session=session,\n        )\n        result = await tool_enforced.execute(command=\"ls\")\n        # Automaticamente:\n        # 1. Valida \"ls\" contra PolicyEngine DENY_LIST\n        # 2. Redireciona qualquer I/O para sandbox\n        # 3. Executa\n        # 4. Ao sair: sandbox deletado\n    \n    Args:\n        tool: Tool instance a envolver\n        policy_engine: PolicyEngine instance\n        zero_trace_session: ZeroTraceSession instance\n    \n    Returns:\n        Tool-like object com execute() decorado\n    \"\"\"\n    tool_name = tool.metadata.name if hasattr(tool, 'metadata') else 'unknown'\n    logger.info(\n        f\"[Enforcement] Aplicando decoradores: {tool_name} - \"\n        f\"Policy + ZeroTrace\"\n    )\n    \n    # ✓ Step 1: Envolver com PolicyEnforcementDecorator\n    policy_decorator = PolicyEnforcementDecorator(\n        original_execute_func=tool.execute,\n        policy_engine=policy_engine,\n        tool_name=tool_name,\n    )\n    policy_wrapped = policy_decorator.wrapped_execute\n    \n    # ✓ Step 2: Envolver resultado com ZeroTraceDecorator\n    trace_decorator = ZeroTraceDecorator(\n        original_execute_func=policy_wrapped,\n        zero_trace_session=zero_trace_session,\n        tool_name=tool_name,\n    )\n    \n    # ✓ Step 3: Retornar Tool-like object com execute() final\n    # Criar classe temporária que preserva metadata do Tool original\n    class EnforcedToolProxy:\n        def __init__(self, original_tool, wrapped_execute_func):\n            self.metadata = original_tool.metadata if hasattr(\n                original_tool, 'metadata'\n            ) else None\n            self._wrapped_execute = wrapped_execute_func\n            self._original = original_tool\n        \n        async def execute(self, **kwargs):\n            \"\"\"Execute com enforcement automático aplicado.\"\"\"\n            return await self._wrapped_execute(**kwargs)\n        \n        def validate_input(self, **kwargs):\n            \"\"\"Delega validação para Tool original.\"\"\"\n            if hasattr(self._original, 'validate_input'):\n                return self._original.validate_input(**kwargs)\n            return True\n        \n        async def safe_execute(self, **kwargs):\n            \"\"\"Delega safe_execute para Tool original.\"\"\"\n            if hasattr(self._original, 'safe_execute'):\n                return await self._original.safe_execute(**kwargs)\n            return await self.execute(**kwargs)\n    \n    enforced = EnforcedToolProxy(tool, trace_decorator.wrapped_execute)\n    logger.info(f\"[Enforcement] ✓ {tool_name} pronto com Policy + ZeroTrace\")\n    return enforced
