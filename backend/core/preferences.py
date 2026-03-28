"""
Persistência de Preferências (Preference Rules Engine)
Sistema que aprende preferências do usuário e as aplica automaticamente.

Padrão: If-Then rules em banco de dados
Exemplo: "sempre usar Spotify para Rock" → Se genre=Rock, então platform=Spotify
"""

import asyncio
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime, timedelta
import sqlite3
from pathlib import Path
import uuid


class RuleCondition(Enum):
    """Tipos de condições para regras."""
    GENRE = "genre"  # Gênero musical
    ARTIST = "artist"  # Artista específico
    TIME_OF_DAY = "time_of_day"  # Horário (morning, afternoon, evening, night)
    CONTEXT = "context"  # Contexto ("work", "workout", "relaxing")
    DEVICE = "device"  # Dispositivo ("phone", "desktop", "car")
    LANGUAGE = "language"  # Idioma


class RuleAction(Enum):
    """Ações que uma regra pode disparar."""
    USE_PLATFORM = "use_platform"  # Spotify, YouTube, Local
    PLAY_NOW = "play_now"  # Play now vs add to queue
    SET_VOLUME = "set_volume"  # Volume padrão
    USE_BROWSER = "use_browser"  # Qual navegador para YouTube
    ENABLE_LOOP = "enable_loop"  # Loop automático
    APPLY_EQ = "apply_eq"  # Equalizador


@dataclass
class PreferenceRule:
    """Regra de preferência do usuário."""
    rule_id: str  # ID único
    condition_type: RuleCondition
    condition_value: str  # Ex: "rock", "artist_name", "evening"
    action_type: RuleAction
    action_value: str  # Ex: "spotify", "true", "80"
    priority: int = 50  # 0-100, maior = mais importante
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used: Optional[str] = None
    usage_count: int = 0
    effectiveness: float = 1.0  # Rating da regra (0-1)
    
    def to_dict(self):
        return {
            'rule_id': self.rule_id,
            'condition_type': self.condition_type.value,
            'condition_value': self.condition_value,
            'action_type': self.action_type.value,
            'action_value': self.action_value,
            'priority': self.priority,
            'enabled': self.enabled,
            'created_at': self.created_at,
            'last_used': self.last_used,
            'usage_count': self.usage_count,
            'effectiveness': self.effectiveness
        }


class PreferenceRulesEngine:
    """
    Motor de regras de preferências com persistência em banco de dados.
    """
    
    DB_SCHEMA = """
    CREATE TABLE IF NOT EXISTS preference_rules (
        rule_id TEXT PRIMARY KEY,
        condition_type TEXT NOT NULL,
        condition_value TEXT NOT NULL,
        action_type TEXT NOT NULL,
        action_value TEXT NOT NULL,
        priority INTEGER DEFAULT 50,
        enabled BOOLEAN DEFAULT 1,
        created_at TEXT NOT NULL,
        last_used TEXT,
        usage_count INTEGER DEFAULT 0,
        effectiveness REAL DEFAULT 1.0
    );
    
    CREATE INDEX IF NOT EXISTS idx_condition ON preference_rules(condition_type, condition_value);
    CREATE INDEX IF NOT EXISTS idx_priority ON preference_rules(priority DESC);
    CREATE INDEX IF NOT EXISTS idx_enabled ON preference_rules(enabled);
    """
    
    def __init__(
        self,
        db_path: str = "backend/temp_vision/preferences.db",
        event_bus_callback: Optional[Callable] = None
    ):
        """
        Args:
            db_path: Caminho para banco de dados SQLite
            event_bus_callback: Função para emitir eventos (async)
        """
        self.db_path = db_path
        self._event_bus = event_bus_callback
        self._rules: Dict[str, PreferenceRule] = {}
        self._initialized = False
        
        # Criar diretório se não existir
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    async def _emit_event(self, event_type: str, data: Any = None):
        """Emitir evento via EventBus."""
        if self._event_bus:
            try:
                await self._event_bus(event_type, data)
            except Exception as e:
                print(f"[ERRO] Falha ao emitir evento {event_type}: {e}")
    
    def _get_connection(self):
        """Obter conexão com banco de dados."""
        return sqlite3.connect(self.db_path)
    
    async def initialize(self):
        """Inicializar banco de dados e carregar regras."""
        def _init_db():
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.executescript(self.DB_SCHEMA)
            conn.commit()
            conn.close()
        
        try:
            await asyncio.to_thread(_init_db)
            await self.load_rules()
            self._initialized = True
            await self._emit_event('preferences_engine_initialized')
        except Exception as e:
            print(f"[ERRO] Falha ao inicializar preferences: {e}")
    
    async def load_rules(self):
        """Carrega todas as regras do banco."""
        def _load():
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM preference_rules ORDER BY priority DESC")
            rows = cursor.fetchall()
            conn.close()
            return rows
        
        try:
            rows = await asyncio.to_thread(_load)
            
            for row in rows:
                rule = PreferenceRule(
                    rule_id=row[0],
                    condition_type=RuleCondition(row[1]),
                    condition_value=row[2],
                    action_type=RuleAction(row[3]),
                    action_value=row[4],
                    priority=row[5],
                    enabled=bool(row[6]),
                    created_at=row[7],
                    last_used=row[8],
                    usage_count=row[9],
                    effectiveness=row[10]
                )
                self._rules[rule.rule_id] = rule
            
            await self._emit_event('preferences_loaded', {'count': len(self._rules)})
        except Exception as e:
            print(f"[ERRO] Falha ao carregar regras: {e}")
    
    async def add_rule(
        self,
        condition_type: RuleCondition,
        condition_value: str,
        action_type: RuleAction,
        action_value: str,
        priority: int = 50
    ) -> str:
        """
        Adiciona nova regra de preferência.
        
        Exemplo:
            engine.add_rule(
                condition_type=RuleCondition.GENRE,
                condition_value="rock",
                action_type=RuleAction.USE_PLATFORM,
                action_value="spotify",
                priority=80
            )
        
        Args:
            condition_type: Tipo de condição
            condition_value: Valor da condição
            action_type: Tipo de ação
            action_value: Valor da ação
            priority: Prioridade (0-100)
            
        Returns:
            ID da regra criada
        """
        import uuid
        rule_id = str(uuid.uuid4())[:8]
        
        rule = PreferenceRule(
            rule_id=rule_id,
            condition_type=condition_type,
            condition_value=condition_value.lower(),
            action_type=action_type,
            action_value=action_value,
            priority=priority
        )
        
        def _insert():
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO preference_rules 
                (rule_id, condition_type, condition_value, action_type, action_value, priority, created_at, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rule.rule_id,
                rule.condition_type.value,
                rule.condition_value,
                rule.action_type.value,
                rule.action_value,
                rule.priority,
                rule.created_at,
                1
            ))
            conn.commit()
            conn.close()
        
        try:
            await asyncio.to_thread(_insert)
            self._rules[rule_id] = rule
            
            await self._emit_event('preference_rule_added', {
                'rule_id': rule_id,
                'condition': f"{condition_type.value}={condition_value}",
                'action': f"{action_type.value}={action_value}"
            })
            
            return rule_id
        except Exception as e:
            print(f"[ERRO] Falha ao adicionar regra: {e}")
            return ""
    
    async def get_applicable_rules(self, context: Dict[str, str]) -> List[PreferenceRule]:
        """
        Obtém regras aplicáveis para dado contexto.
        
        Args:
            context: Dicionário com contexto atual
                {
                    'genre': 'rock',
                    'time_of_day': 'evening',
                    'context': 'work',
                    'device': 'desktop'
                }
        
        Returns:
            Lista de regras aplicáveis ordenadas por prioridade
        """
        applicable = []
        
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            
            # Verificar se a condição da regra é atendida
            context_key = {
                RuleCondition.GENRE: 'genre',
                RuleCondition.ARTIST: 'artist',
                RuleCondition.TIME_OF_DAY: 'time_of_day',
                RuleCondition.CONTEXT: 'context',
                RuleCondition.DEVICE: 'device',
                RuleCondition.LANGUAGE: 'language'
            }.get(rule.condition_type)
            
            if context_key and context.get(context_key, '').lower() == rule.condition_value:
                applicable.append(rule)
        
        # Ordenar por prioridade e efetividade
        applicable.sort(key=lambda r: (r.priority * r.effectiveness), reverse=True)
        
        return applicable
    
    async def evaluate_context(self, context: Dict[str, str]) -> Dict[str, str]:
        """
        Avalia contexto e retorna ações recomendadas.
        
        Args:
            context: Contexto atual
            
        Returns:
            Dicionário de {action_type: action_value}
        """
        rules = await self.get_applicable_rules(context)
        
        actions = {}
        for rule in rules:
            # Pode haver múltiplas regras, usar a de maior prioridade para cada ação
            if rule.action_type not in actions:
                actions[rule.action_type.value] = rule.action_value
        
        await self._emit_event('context_evaluated', {
            'context': context,
            'actions': actions,
            'matching_rules': len(rules)
        })
        
        return actions
    
    async def record_rule_usage(self, rule_id: str, was_effective: bool = True):
        """
        Registra uso de uma regra e sua efetividade.
        
        Args:
            rule_id: ID da regra
            was_effective: Se a regra resultou em ação frutífera
        """
        if rule_id not in self._rules:
            return
        
        rule = self._rules[rule_id]
        rule.usage_count += 1
        rule.last_used = datetime.now().isoformat()
        
        # Atualizar effectiveness (moving average)
        if was_effective:
            rule.effectiveness = min(1.0, rule.effectiveness + 0.05)
        else:
            rule.effectiveness = max(0.0, rule.effectiveness - 0.1)
        
        def _update():
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE preference_rules 
                SET last_used = ?, usage_count = ?, effectiveness = ?
                WHERE rule_id = ?
            """, (rule.last_used, rule.usage_count, rule.effectiveness, rule_id))
            conn.commit()
            conn.close()
        
        try:
            await asyncio.to_thread(_update)
            await self._emit_event('rule_usage_recorded', {
                'rule_id': rule_id,
                'effectiveness': rule.effectiveness
            })
        except Exception as e:
            print(f"[ERRO] Falha ao registrar uso: {e}")
    
    async def disable_rule(self, rule_id: str):
        """Desabilita uma regra."""
        if rule_id in self._rules:
            self._rules[rule_id].enabled = False
            
            def _update():
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE preference_rules SET enabled = 0 WHERE rule_id = ?", (rule_id,))
                conn.commit()
                conn.close()
            
            try:
                await asyncio.to_thread(_update)
                await self._emit_event('rule_disabled', {'rule_id': rule_id})
            except Exception as e:
                print(f"[ERRO] Falha ao desabilitar regra: {e}")
    
    async def suggest_rule_from_interaction(self, query: str, chosen_action: str):
        """
        Cria regra sugerida baseada em padrão de interação.
        
        Exemplo:
            User sempre pede "rock" e escolhe "spotify"
            → Sistema sugere regra: rock → spotify
        
        Args:
            query: Consulta que o usuário fez
            chosen_action: Ação que o usuário escolheu
        """
        # Análise simples para extrair condição
        query_lower = query.lower()
        
        # Detectar gêneros conhecidos
        genres = ['rock', 'pop', 'jazz', 'clássica', 'música clássica', 'samba', 'forró']
        detected_genre = next((g for g in genres if g in query_lower), None)
        
        if detected_genre:
            # Criar regra sugerida para gênero -> ação
            await self._emit_event('rule_suggestion_available', {
                'suggested_condition': f"genre={detected_genre}",
                'suggested_action': chosen_action,
                'confidence': 0.8
            })


async def create_preferences_engine(db_path: str = "backend/temp_vision/preferences.db",
                                    event_bus_callback: Optional[Callable] = None) -> PreferenceRulesEngine:
    """
    Factory para criar e inicializar motor de preferências.
    
    Args:
        db_path: Caminho do banco de dados
        event_bus_callback: Callback para eventos
        
    Returns:
        PreferenceRulesEngine inicializado
    """
    engine = PreferenceRulesEngine(db_path, event_bus_callback)
    await engine.initialize()
    return engine
