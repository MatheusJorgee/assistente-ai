"""
Tool Registry com Limpeza de Schema Pydantic
==============================================

Responsabilidades:
- Extrair apenas name, description, parameters de ferramentas
- Remover metadados Pydantic (extra_forbidden, model_config, etc)
- Gerar JSON Schema puro compatível com Gemini
- Suportar múltiplas estratégias de geração de schema

Padrão: Strategy (diferentes lipogens de schema) + Facade (interface limpa)
"""

import inspect
import json
from typing import Any, Dict, List, Callable, Optional
from abc import ABC, abstractmethod
from pydantic import BaseModel
from docstring_parser import parse as parse_docstring


class SchemaStrategy(ABC):
    """Interface para diferentes estratégias de schema generation."""
    
    @abstractmethod
    def extract(self, func: Callable) -> Dict[str, Any]:
        """Extrai schema de uma função."""
        pass


class PydanticSchemaStrategy(SchemaStrategy):
    """Extrai schema de função com anotações Pydantic."""
    
    def extract(self, func: Callable) -> Dict[str, Any]:
        """
        Extrai apenas os campos válidos para Gemini:
        - type (sempre 'object')
        - properties (Dict[str, {type, description}])
        - required (List[str] de parâmetros obrigatórios)
        
        REMOVE:
        - additionalProperties
        - extra_forbidden (❌ GENINI NÃO ACEITA)
        - model_config
        """
        sig = inspect.signature(func)
        docstring = parse_docstring(func.__doc__ or "")
        
        properties = {}
        required = []
        
        # Iterar parâmetros excluindo 'self' e 'cls'
        for param_name, param in sig.parameters.items():
            if param_name in ('self', 'cls'):
                continue
            
            param_annotation = param.annotation
            description = ""
            
            # Encontrar descrição no docstring
            for param_doc in docstring.params:
                if param_doc.arg_name == param_name:
                    description = param_doc.description or ""
                    break
            
            # Mapear tipo Python → JSON Schema
            param_type = self._map_type(param_annotation)
            
            # Montar propriedade
            prop_schema = {
                "type": param_type,
                "description": description or f"Parâmetro {param_name}"
            }

            if param_type == "array":
                prop_schema["items"] = {"type": "string"}
            elif param_type == "object":
                prop_schema["properties"] = {}

            properties[param_name] = prop_schema
            
            # Se não tem default, é obrigatório
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
        
        # ✅ SCHEMA PURO (Gemini aceita)
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }
    
    @staticmethod
    def _map_type(annotation) -> str:
        """Mapeia tipos Python para JSON Schema."""
        if annotation is inspect.Parameter.empty or annotation is None:
            return "string"
        
        type_str = str(annotation).lower()
        
        if 'int' in type_str:
            return 'integer'
        elif 'float' in type_str or 'decimal' in type_str:
            return 'number'
        elif 'bool' in type_str:
            return 'boolean'
        elif 'list' in type_str or 'array' in type_str:
            return 'array'
        elif 'dict' in type_str:
            return 'object'
        else:
            return 'string'


class SimpleSchemaStrategy(SchemaStrategy):
    """Estratégia fallback: todos parâmetros são strings."""
    
    def extract(self, func: Callable) -> Dict[str, Any]:
        sig = inspect.signature(func)
        
        properties = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            if param_name in ('self', 'cls'):
                continue
            
            properties[param_name] = {
                "type": "string",
                "description": f"Entrada para {param_name}"
            }
            
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }


class ToolDefinition:
    """Representa uma ferramenta pronta para Gemini."""
    
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        func: Callable,
        module_path: Optional[str] = None
    ):
        self.name = name
        self.description = description
        self.parameters = parameters  # ← Schema puro (sem Pydantic)
        self.func = func
        self.module_path = module_path or func.__module__
    
    def to_gemini_tool(self) -> Dict[str, Any]:
        """Retorna formato esperado pelo Gemini."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Representa a ferramenta como dicionário."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "module": self.module_path
        }


class ToolRegistryClean:
    """
    Registry centralizador de ferramentas com limpeza de schema.
    
    Responsabilidades:
    - Registrar ferramentas de automação
    - Gerar schemas Pydantic-safe
    - Fornecer lista pronta para Gemini
    - Executar ferramentas por nome
    """
    
    def __init__(self, schema_strategy: Optional[SchemaStrategy] = None):
        self.tools: Dict[str, ToolDefinition] = {}
        self.schema_strategy = schema_strategy or PydanticSchemaStrategy()
    
    def register(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        schema_override: Optional[Dict[str, Any]] = None
    ) -> ToolDefinition:
        """
        Registra uma função como ferramenta.
        
        Args:
            func: Função a registrar
            name: Nome da ferramenta (default: func.__name__)
            description: Descrição (default: func.__doc__)
            schema_override: Schema customizado (ignora strategy)
        
        Returns:
            ToolDefinition criado
        """
        tool_name = name or func.__name__
        tool_description = description or (func.__doc__ or "").strip().split('\n')[0]
        
        # Gerar schema
        if schema_override:
            schema = schema_override
        else:
            try:
                schema = self.schema_strategy.extract(func)
            except Exception as e:
                # Fallback: se strategy falhar, usar schema simples
                print(f"[TOOL_REGISTRY] Aviso: Schema extraction falhou para {tool_name}: {e}")
                schema = SimpleSchemaStrategy().extract(func)
        
        tool_def = ToolDefinition(
            name=tool_name,
            description=tool_description,
            parameters=schema,
            func=func
        )
        
        self.tools[tool_name] = tool_def
        print(f"✓ [TOOL_REGISTRY] Registrado: {tool_name}")
        return tool_def
    
    def get_all_tools(self) -> List[ToolDefinition]:
        """Retorna todas as ferramentas."""
        return list(self.tools.values())
    
    def get_gemini_tools(self) -> List[Dict[str, Any]]:
        """
        Retorna lista de ferramentas no formato Gemini.
        
        ✓ GARANTIDO: Nenhum metadado Pydantic
        """
        return [tool.to_gemini_tool() for tool in self.tools.values()]
    
    def list_tools(self) -> Dict[str, str]:
        """Lista nomes e descrições das ferramentas."""
        return {
            name: tool.description
            for name, tool in self.tools.items()
        }
    
    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """
        Executa uma ferramenta por nome.
        
        Args:
            tool_name: Nome da ferramenta registrada
            arguments: Argumentos para a função
        
        Returns:
            Resultado da execução
        
        Raises:
            KeyError: Se ferramenta não existe
            TypeError: Se argumentos inválidos
        """
        if tool_name not in self.tools:
            raise KeyError(f"Ferramenta '{tool_name}' não registrada")
        
        tool = self.tools[tool_name]
        
        # Chamar função (se for async, awaitar)
        if inspect.iscoroutinefunction(tool.func):
            return await tool.func(**arguments)
        else:
            return tool.func(**arguments)
    
    def export_schema(self, output_path: Optional[str] = None) -> str:
        """
        Exporta schema de todas ferramentas como JSON.
        
        Útil para documentação/debugging.
        """
        schema_dict = {
            "tools": [tool.to_dict() for tool in self.tools.values()],
            "count": len(self.tools),
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }
        
        schema_json = json.dumps(schema_dict, indent=2, ensure_ascii=False)
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(schema_json)
            print(f"✓ Schema exportado: {output_path}")
        
        return schema_json


def create_tool_registry() -> ToolRegistryClean:
    """Factory para criar registry com estratégia padrão."""
    return ToolRegistryClean(schema_strategy=PydanticSchemaStrategy())
