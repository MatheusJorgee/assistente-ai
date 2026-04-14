"""
obsidian_manager.py - Gerente de Vault (Obsidian) para Memória Permanente
===========================================================================

Substitui SQLite por um Obsidian Vault estruturado com Markdown + YAML Frontmatter.

ARQUITETURA:

vault/
├── 00-Meta/
│   └── _index.md              (Metadados do vault)
├── Memorias/
│   ├── Usuario-Preferencias.md    (Facts semânticos)
│   ├── Sistema-Contexto.md
│   └── Episodios-Recentes.md      (Timeline de eventos)
├── Conversas/
│   ├── 2025-04-14--Session001.md  (Chat history backups)
│   └── ...
└── Resumos/
    ├── Conversa-2025-W15.md       (Summaries de contexto antigo)
    └── ...

DESIGN RATIONALE:

1. **Separação Semântica**
   - Memorias: Fatos permanentes (preferências, conhecimento)
   - Conversas: Histórico de chat (referência, auditoria)
   - Resumos: Contexts antigos movidos de RAM (economia de tokens)
   → Usuario vê estrutura, consegue editar, versionável

2. **Frontmatter YAML**
   ```yaml
   ---
   data: 2025-04-14T10:30:00Z
   categoria: preferencias
   tags: [spotify, musica, rotina]
   relevancia: 0.85
   atualizacao: 2025-04-14T10:30:00Z
   ---
   Conteudo...
   ```
   → Queryable sem parsear todo Markdown. Tags para RAG.

3. **RAG via Tags + TF-IDF**
   - User says: "Toca a musica que gosto"
   - Extract keywords: ["toca", "musica", "gosto"]
   - Search tags: ["musica", "preferencia", "spotify"]
   - Find relevant notes by tag intersection + recency
   → 3-5 notes for context, ~1-2k tokens instead of 20k
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import os

try:
    from .logger import get_logger
except ImportError:
    import logging
    get_logger = lambda x: logging.getLogger(x)

logger = get_logger(__name__)


@dataclass
class ObsidianMemory:
    """Representa uma nota no Obsidian Vault."""

    title: str                                    # Nome do arquivo (sem .md)
    content: str                                  # Corpo do markdown
    categoria: str = "episodio"                   # memorias, conversas, resumos, episodio
    tags: list[str] = None                        # Tags para RAG ["musica", "spotify"]
    data: str = ""                                # Data de criação (ISO 8601)
    relevancia: float = 1.0                       # Relevância (0-1) usada em ranking
    atualizacao: str = ""                         # Data de última atualização

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []
        if not self.data:
            self.data = datetime.now().isoformat()
        if not self.atualizacao:
            self.atualizacao = datetime.now().isoformat()

    def to_markdown_with_frontmatter(self) -> str:
        """Serializa nota para Markdown com Frontmatter YAML."""
        frontmatter = {
            "data": self.data,
            "categoria": self.categoria,
            "tags": self.tags,
            "relevancia": self.relevancia,
            "atualizacao": self.atualizacao,
        }

        yaml_str = "---\n"
        for key, value in frontmatter.items():
            if isinstance(value, list):
                # Format list as YAML array
                yaml_str += f"{key}: {json.dumps(value)}\n"
            elif isinstance(value, str):
                yaml_str += f'{key}: "{value}"\n'
            else:
                yaml_str += f"{key}: {value}\n"
        yaml_str += "---\n\n"

        return yaml_str + self.content

    @staticmethod
    def parse_markdown_with_frontmatter(md_text: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Parseia Markdown com Frontmatter YAML.

        Returns:
            (frontmatter_dict, content_body)
        """
        # Regex para extrair frontmatter
        match = re.match(r"^---\n(.*?)\n---\n(.*)", md_text, re.DOTALL)
        if not match:
            return None, md_text

        yaml_text, content = match.groups()

        # Parse YAML simples (sem PyYAML, apenas regex)
        frontmatter = {}
        for line in yaml_text.split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()

            # Parse JSON arrays
            if value.startswith("[") and value.endswith("]"):
                try:
                    frontmatter[key] = json.loads(value)
                except:
                    frontmatter[key] = value
            # Parse números
            elif value.replace(".", "").replace("-", "").isdigit():
                try:
                    frontmatter[key] = float(value) if "." in value else int(value)
                except:
                    frontmatter[key] = value
            # Parse booleanos
            elif value.lower() in ("true", "false"):
                frontmatter[key] = value.lower() == "true"
            # Parse strings
            else:
                frontmatter[key] = value.strip('"\'')

        return frontmatter, content


class ObsidianVaultManager:
    """
    Gerente do Obsidian Vault.

    Interface assíncrona para manipular .md files como banco de dados persistente.
    """

    def __init__(self, vault_path: Optional[Path] = None) -> None:
        """
        Args:
            vault_path: Caminho para pasta vault. Default: backend/.vault
        """
        if vault_path is None:
            backend_root = Path(__file__).resolve().parent.parent
            vault_path = backend_root / ".vault"

        self.vault_path = Path(vault_path)
        self._ensure_vault_structure()

        logger.info(f"[OBSIDIAN] Vault inicializado: {self.vault_path}")

    def _ensure_vault_structure(self) -> None:
        """
        Cria estrutura de pastas do vault se não existir.

        Estrutura:
        - 00-Meta/
        - Memorias/
        - Conversas/
        - Resumos/
        """
        self.vault_path.mkdir(parents=True, exist_ok=True)

        for subdir in ["00-Meta", "Memorias", "Conversas", "Resumos"]:
            (self.vault_path / subdir).mkdir(exist_ok=True)

        # Criar arquivo index se não existir
        index_file = self.vault_path / "00-Meta" / "_index.md"
        if not index_file.exists():
            index_content = """---
data: {date}
categoria: meta
tags: [vault, meta]
---

# Obsidian Vault - Jarvis Memory

Created: {date}
Vault: {vault_path}

## Estrutura
- **Memorias/**: Fatos semânticos permanentes
- **Conversas/**: Histórico de chats
- **Resumos/**: Contextos antigos summarizados
- **00-Meta/**: Metadados do vault

## Estatísticas

- Total Notes: (auto-updated)
- Last Access: (auto-updated)
""".format(
                date=datetime.now().isoformat(),
                vault_path=str(self.vault_path),
            )
            index_file.write_text(index_content, encoding="utf-8")

    async def save_memory(
        self,
        memory: ObsidianMemory,
        subcategoria: Optional[str] = None,
    ) -> Path:
        """
        Salva memória como arquivo .md no vault.

        Args:
            memory: ObsidianMemory a salvar
            subcategoria: Subdirectório dentro de categoria
                         (ex: categoria="Memorias", subcategoria="Preferencias")

        Returns:
            Path do arquivo salvo
        """
        # Determinar caminho
        base_dir = self.vault_path / memory.categoria
        if subcategoria:
            base_dir = base_dir / subcategoria
        base_dir.mkdir(parents=True, exist_ok=True)

        # Sanitizar nome do arquivo
        filename = re.sub(r"[<>:\"/\\|?*]", "-", memory.title)
        if not filename.endswith(".md"):
            filename += ".md"

        file_path = base_dir / filename

        # Serializar e salvar
        md_content = memory.to_markdown_with_frontmatter()
        file_path.write_text(md_content, encoding="utf-8")

        logger.info(f"[OBSIDIAN] Salvo: {file_path.relative_to(self.vault_path)}")
        return file_path

    async def load_memory(self, title: str, categoria: str = "Memorias") -> Optional[ObsidianMemory]:
        """
        Carrega memória do vault.

        Args:
            title: Nome do arquivo (sem .md)
            categoria: Categoria/pasta (Memorias, Conversas, etc)

        Returns:
            ObsidianMemory ou None se não encontrado
        """
        file_path = self.vault_path / categoria / f"{title}.md"
        if not file_path.exists():
            return None

        md_text = file_path.read_text(encoding="utf-8")
        frontmatter, content = ObsidianMemory.parse_markdown_with_frontmatter(md_text)

        memory = ObsidianMemory(
            title=title,
            content=content,
            categoria=categoria,
            **{k: v for k, v in (frontmatter or {}).items() if k in ["tags", "relevancia", "data", "atualizacao"]}
        )
        return memory

    async def search_by_tags(
        self, 
        keywords: list[str],
        categoria: str = "Memorias",
        limit: int = 5,
    ) -> list[ObsidianMemory]:
        """
        RAG: Busca notas por tags (keyword matching).

        Estratégia:
        1. Extract tags do frontmatter
        2. Score cada nota por tag matches
        3. Ordenar por relevancia + recency
        4. Retornar top N

        Args:
            keywords: Lista de palavras-chave para buscar
            categoria: Categoria a buscar (default: Memorias)
            limit: Máximo de notas a retornar

        Returns:
            Lista de ObsidianMemory ordenadas por relevância
        """
        categoria_path = self.vault_path / categoria
        if not categoria_path.exists():
            return []

        results: list[Tuple[ObsidianMemory, float]] = []

        # Iterar sobre todos os .md
        for md_file in categoria_path.glob("*.md"):
            if md_file.name.startswith("_"):
                continue  # Skip meta files

            try:
                md_text = md_file.read_text(encoding="utf-8")
                frontmatter, content = ObsidianMemory.parse_markdown_with_frontmatter(md_text)

                if not frontmatter:
                    continue

                memory = ObsidianMemory(
                    title=md_file.stem,
                    content=content,
                    categoria=categoria,
                    **{k: v for k, v in frontmatter.items() if k in ["tags", "relevancia", "data", "atualizacao"]}
                )

                # Score: quantas keywords matcham com tags?
                score = self._compute_relevance_score(
                    keywords=keywords,
                    tags=memory.tags,
                    content=content,
                    relevancia_base=memory.relevancia,
                    data=memory.data,
                )

                if score > 0:
                    results.append((memory, score))

            except Exception as e:
                logger.warning(f"[OBSIDIAN] Erro ao ler {md_file}: {e}")
                continue

        # Ordenar por score (descendente) e retornar top N
        results.sort(key=lambda x: x[1], reverse=True)
        return [mem for mem, _ in results[:limit]]

    def _compute_relevance_score(
        self,
        keywords: list[str],
        tags: list[str],
        content: str,
        relevancia_base: float = 1.0,
        data: str = "",
    ) -> float:
        """
        Computa score de relevância de uma nota.

        Fatores:
        1. Tag matches (40%)
        2. Content TF-IDF simples (40%)
        3. Recency (20%)
        4. Base relevancia (custom score)

        Args:
            keywords: Palavras-chave da query
            tags: Tags da nota
            content: Corpo da nota
            relevancia_base: Score base (0-1)
            data: Data de criação (ISO 8601)

        Returns:
            Score entre 0-1
        """
        score = 0.0
        keywords_lower = [kw.lower() for kw in keywords]
        tags_lower = [tag.lower() for tag in tags]

        # 1. Tag matches (40%)
        tag_matches = sum(1 for tag in tags_lower if any(kw in tag for kw in keywords_lower))
        tag_score = min(1.0, tag_matches / max(1, len(keywords))) * 0.4

        # 2. Content TF-IDF simples (40%)
        # Count keyword occurrences in content
        content_lower = content.lower()
        keyword_count = sum(content_lower.count(kw) for kw in keywords_lower)
        # Normalize por tamanho do content
        tf_score = min(1.0, keyword_count / max(1, len(content) / 100)) * 0.4

        # 3. Recency (20%)
        # Notas recentes são mais relevantes
        try:
            note_date = datetime.fromisoformat(data)
            days_old = (datetime.now() - note_date).days
            # Decay: 30 dias = 0.5 score
            recency_score = max(0, 1.0 - (days_old / 30)) * 0.2
        except:
            recency_score = 0.1  # Fallback se data inválida

        score = tag_score + tf_score + recency_score
        score *= relevancia_base  # Apply base multiplier

        return min(1.0, score)

    async def search_full_text(
        self,
        query: str,
        categoria: str = "Memorias",
        limit: int = 5,
    ) -> list[ObsidianMemory]:
        """
        Busca full-text simples no vault (fallback para RAG por tags).

        Args:
            query: String de busca
            categoria: Categoria a buscar
            limit: Máximo de resultados

        Returns:
            Notas que contêm a query
        """
        # Extract keywords da query
        keywords = re.findall(r"\b\w{3,}\b", query.lower())
        return await self.search_by_tags(keywords, categoria, limit)

    async def list_all_memories(
        self, 
        categoria: Optional[str] = None
    ) -> list[ObsidianMemory]:
        """
        Lista todas as notas no vault (ou em categoria específica).

        Args:
            categoria: Se None, lista todas; senão lista só dessa categoria

        Returns:
            Lista de ObsidianMemory
        """
        memories: list[ObsidianMemory] = []

        if categoria:
            paths = [self.vault_path / categoria]
        else:
            paths = [p for p in self.vault_path.iterdir() if p.is_dir()]

        for cat_path in paths:
            for md_file in cat_path.glob("*.md"):
                if md_file.name.startswith("_"):
                    continue

                try:
                    md_text = md_file.read_text(encoding="utf-8")
                    frontmatter, content = ObsidianMemory.parse_markdown_with_frontmatter(md_text)
                    memory = ObsidianMemory(
                        title=md_file.stem,
                        content=content,
                        categoria=cat_path.name,
                        **{k: v for k, v in (frontmatter or {}).items() if k in ["tags", "relevancia", "data", "atualizacao"]}
                    )
                    memories.append(memory)
                except Exception as e:
                    logger.warning(f"[OBSIDIAN] Erro ao ler {md_file}: {e}")

        return memories

    async def get_vault_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do vault."""
        memories = await self.list_all_memories()
        
        return {
            "total_notes": len(memories),
            "vault_path": str(self.vault_path),
            "by_categoria": {
                cat: len([m for m in memories if m.categoria == cat])
                for cat in set(m.categoria for m in memories)
            },
            "last_access": datetime.now().isoformat(),
        }


# Singleton global
_vault_instance: Optional[ObsidianVaultManager] = None


async def get_obsidian_vault(vault_path: Optional[Path] = None) -> ObsidianVaultManager:
    """Retorna singleton do Obsidian Vault Manager."""
    global _vault_instance
    if _vault_instance is None:
        _vault_instance = ObsidianVaultManager(vault_path)
    return _vault_instance
