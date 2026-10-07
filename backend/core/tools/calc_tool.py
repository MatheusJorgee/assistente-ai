"""
CalcTool — matemática exata para o raciocínio da Quinta-Feira.

LLMs erram aritmética de cabeça. Com esta ferramenta ela calcula DE VERDADE:
expressões numéricas, porcentagens, juros, conversões e funções científicas —
avaliadas com AST restrito (sem eval cru, sem acesso a nomes do runtime).
"""

from __future__ import annotations

import ast
import math
import operator

try:
    from ..tools.base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger
except ImportError:
    from .base import MotorTool, ToolMetadata, ToolParameter, SecurityLevel
    from .. import get_logger

logger = get_logger(__name__)

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Funções e constantes permitidas (somente matemática pura)
_FUNCS = {
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "sqrt": math.sqrt, "log": math.log, "log2": math.log2, "log10": math.log10,
    "exp": math.exp, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "radians": math.radians, "degrees": math.degrees,
    "floor": math.floor, "ceil": math.ceil, "factorial": math.factorial,
    "gcd": math.gcd, "lcm": math.lcm,
}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf}

_MAX_POW = 10 ** 6  # limita expoentes pra não travar o processo


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"constante não numérica: {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError(f"nome desconhecido: {node.id}")
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and (abs(left) > _MAX_POW or abs(right) > 10000):
            raise ValueError("potência grande demais")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise ValueError("função não permitida")
        if node.keywords:
            raise ValueError("argumentos nomeados não suportados")
        args = [_eval_node(a) for a in node.args]
        if node.func.id == "factorial" and (args and args[0] > 5000):
            raise ValueError("fatorial grande demais")
        return _FUNCS[node.func.id](*args)
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_eval_node(e) for e in node.elts]  # p/ min/max/sum((..))
    raise ValueError(f"sintaxe não permitida: {type(node).__name__}")


def _run(expressao: str):
    tree = ast.parse(expressao, mode="eval")
    return _eval_node(tree)


def calcular_expressao(expressao: str) -> float:
    """
    Avalia expressão matemática com AST restrito. Levanta ValueError se inválida.

    Vírgula é ambígua ('min(4, 9)' vs decimal brasileiro '2,5'): tenta primeiro
    como veio (vírgula = separador); se falhar ou virar tupla solta, reinterpreta
    vírgula como decimal.
    """
    expressao = (expressao or "").strip().replace("^", "**")
    if not expressao or len(expressao) > 500:
        raise ValueError("expressão vazia ou longa demais")

    try:
        resultado = _run(expressao)
        if not isinstance(resultado, list):  # tupla solta = vírgula era decimal
            return resultado
    except (SyntaxError, ValueError):
        pass

    resultado = _run(expressao.replace(",", "."))
    if isinstance(resultado, list):
        raise ValueError("expressão ambígua — use ponto como separador decimal")
    return resultado


class CalcTool(MotorTool):
    """Calculadora exata (AST seguro) para qualquer aritmética."""

    def __init__(self) -> None:
        super().__init__(
            metadata=ToolMetadata(
                name="calcular",
                description=(
                    "Calculadora EXATA. Use SEMPRE que a resposta envolver aritmética "
                    "(contas, porcentagens, juros, médias, conversões, raízes) em vez de "
                    "calcular de cabeça — de cabeça você erra. Aceita expressão matemática "
                    "com + - * / // % ** ( ), funções (sqrt, log, sin, round, abs, min, max, "
                    "sum, factorial...) e constantes (pi, e). Ex.: '1250*1.075**12' ou "
                    "'sqrt(2)*round(17.4)'."
                ),
                category="reasoning",
                parameters=[
                    ToolParameter(
                        name="expressao",
                        type="string",
                        description="Expressão matemática a avaliar. Ex.: '(2300*0.12)/30'.",
                        required=True,
                    ),
                ],
                examples=[
                    'expressao="1250 * 1.075 ** 12"',
                    'expressao="sqrt(144) + 17 % 5"',
                ],
                security_level=SecurityLevel.LOW,
                tags=["matematica", "raciocinio", "exato"],
            )
        )

    def validate_input(self, **kwargs) -> bool:
        exp = kwargs.get("expressao")
        return isinstance(exp, str) and bool(exp.strip())

    async def execute(self, **kwargs) -> str:
        expressao = str(kwargs["expressao"])
        try:
            resultado = calcular_expressao(expressao)
        except ValueError as exc:
            return f"[ERRO] Expressão inválida: {exc}"
        except Exception as exc:
            return f"[ERRO] Falha no cálculo: {type(exc).__name__}: {exc}"

        if isinstance(resultado, float) and resultado.is_integer():
            resultado = int(resultado)
        logger.info("[CALC] %s = %s", expressao, resultado)
        return f"{expressao} = {resultado}"
