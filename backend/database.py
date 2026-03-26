import sqlite3
import os

class BaseDadosMemoria:
    def __init__(self):
        self.app_env = os.getenv("APP_ENV", "development").strip().lower()
        self.local_only_memory = os.getenv("LOCAL_ONLY_MEMORY", "true").strip().lower() == "true"
        self.memoria_ativa = os.getenv("ENABLE_LONG_TERM_MEMORY", "true").strip().lower() == "true"

        # Em produção, mantém a memória longa desativada por padrão para evitar persistência indevida.
        if self.app_env == "production" and self.local_only_memory:
            self.memoria_ativa = False
            self.caminho_db = ""
            print(">>> [MEMÓRIA] Memória longa desativada em produção (LOCAL_ONLY_MEMORY=true).")
            return

        self.caminho_db = self._resolver_caminho_db_local()
        self._inicializar_db()

    def _resolver_caminho_db_local(self) -> str:
        caminho_custom = os.getenv("MEMORY_DB_PATH", "").strip()
        if caminho_custom:
            pasta = os.path.dirname(caminho_custom)
            if pasta:
                os.makedirs(pasta, exist_ok=True)
            return caminho_custom

        # Padrão: banco local fora do repositório para nunca ser comitado por engano.
        base_local = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
        pasta_memoria = os.path.join(base_local, "QuintaFeira", "data")
        os.makedirs(pasta_memoria, exist_ok=True)
        return os.path.join(pasta_memoria, "memoria_quinta_feira.db")

    def _inicializar_db(self):
        if not self.memoria_ativa:
            return

        with sqlite3.connect(self.caminho_db) as conexao:
            cursor = conexao.cursor()
            
            # 1. Tabela Original: Fatos e Contexto (Memória Declarativa)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS memorias_longo_prazo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    categoria TEXT NOT NULL,
                    informacao TEXT NOT NULL,
                    data_registo DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 2. NOVA TABELA ARQUITETURAL: Cache Cognitiva (Memória Processual/Skills)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache_habilidades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    objetivo TEXT NOT NULL,
                    ambiente TEXT NOT NULL,
                    comando_exato TEXT NOT NULL,
                    data_registo DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache_resolucoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contexto TEXT NOT NULL,
                    termo_original TEXT NOT NULL,
                    alvo_canonico TEXT NOT NULL,
                    confianca TEXT NOT NULL,
                    fonte TEXT NOT NULL DEFAULT 'oraculo',
                    data_registo DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(contexto, termo_original)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache_planos_gerais (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pedido_original TEXT NOT NULL,
                    categoria TEXT NOT NULL,
                    alvo_principal TEXT NOT NULL,
                    alvo_secundario TEXT NOT NULL DEFAULT '',
                    plataforma_preferida TEXT NOT NULL DEFAULT 'auto',
                    confianca TEXT NOT NULL DEFAULT 'MEDIA',
                    fonte TEXT NOT NULL DEFAULT 'oraculo',
                    data_registo DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(pedido_original)
                )
            ''')
            conexao.commit()

    # --- MÉTODOS DE MEMÓRIA DECLARATIVA (ORIGINAIS) ---

    def guardar_memoria(self, informacao: str, categoria: str) -> str:
        if not self.memoria_ativa:
            return "Memória de longo prazo desativada neste ambiente."

        with sqlite3.connect(self.caminho_db) as conexao:
            cursor = conexao.cursor()
            cursor.execute(
                'INSERT INTO memorias_longo_prazo (categoria, informacao) VALUES (?, ?)', 
                (categoria, informacao)
            )
            conexao.commit()
        print(f">>> [BASE DE DADOS] Nova memória consolidada: [{categoria}] {informacao}")
        return "Informação guardada com sucesso na base de dados de longo prazo."

    def ler_memorias(self) -> str:
        """Busca todas as memórias para injetar no cérebro da IA ao iniciar."""
        if not self.memoria_ativa:
            return ""

        with sqlite3.connect(self.caminho_db) as conexao:
            cursor = conexao.cursor()
            cursor.execute('SELECT categoria, informacao FROM memorias_longo_prazo ORDER BY data_registo ASC')
            resultados = cursor.fetchall()

        if not resultados:
            return "" 

        contexto_memoria = "\n[MEMÓRIAS DE LONGO PRAZO CONSOLIDADAS DO USUÁRIO]\n"
        contexto_memoria += "Você deve lembrar e respeitar as seguintes informações gravadas no passado:\n"
        for categoria, informacao in resultados:
            contexto_memoria += f"- [{categoria.upper()}]: {informacao}\n"
        
        return contexto_memoria

    # ==========================================
    # NOVOS MÉTODOS PARA O MOTOR DE HABILIDADES
    # ==========================================
    
    def salvar_habilidade(self, objetivo: str, ambiente: str, comando_exato: str):
        """Grava um comando que a Quinta-Feira acabou de aprender com o Oráculo."""
        if not self.memoria_ativa:
            return

        with sqlite3.connect(self.caminho_db) as conexao:
            cursor = conexao.cursor()
            # Evita duplicados: verifica se já existe um comando exato para este objetivo
            cursor.execute('SELECT id FROM cache_habilidades WHERE objetivo = ? AND ambiente = ?', (objetivo, ambiente))
            if not cursor.fetchone():
                cursor.execute(
                    'INSERT INTO cache_habilidades (objetivo, ambiente, comando_exato) VALUES (?, ?, ?)', 
                    (objetivo, ambiente, comando_exato)
                )
                conexao.commit()
                print(f">>> [CACHE COGNITIVA] Nova skill gravada: [{ambiente}] {objetivo} -> {comando_exato}")

    def ler_habilidades_como_ferramenta(self) -> str:
        """
        Retorna todas as habilidades aprendidas formatadas como um manual de instruções
        para o System Prompt da Quinta-Feira.
        """
        if not self.memoria_ativa:
            return ""

        with sqlite3.connect(self.caminho_db) as conexao:
            cursor = conexao.cursor()
            cursor.execute('SELECT objetivo, ambiente, comando_exato FROM cache_habilidades')
            resultados = cursor.fetchall()

        if not resultados:
            return ""

        manual = "\n[MANUAL DE COMANDOS APRENDIDOS (CACHE COGNITIVA)]\n"
        manual += "Você já aprendeu a executar as seguintes ações. NÃO consulte o Oráculo para estas ações, use a ferramenta 'executar_comando_terminal' ou equivalente injetando o comando exato abaixo:\n\n"
        
        for objetivo, ambiente, comando in resultados:
            manual += f"-> OBJETIVO: {objetivo}\n"
            manual += f"   AMBIENTE: {ambiente}\n"
            manual += f"   COMANDO EXATO: {comando}\n\n"
            
        return manual

    def buscar_resolucao(self, contexto: str, termo_original: str):
        """Busca resolução canônica previamente aprendida para um termo em um contexto."""
        if not self.memoria_ativa:
            return None

        contexto_limpo = (contexto or "").strip().lower()
        termo_limpo = (termo_original or "").strip().lower()
        if not contexto_limpo or not termo_limpo:
            return None

        with sqlite3.connect(self.caminho_db) as conexao:
            cursor = conexao.cursor()
            cursor.execute(
                '''
                SELECT alvo_canonico, confianca, fonte
                FROM cache_resolucoes
                WHERE contexto = ? AND termo_original = ?
                ORDER BY data_registo DESC
                LIMIT 1
                ''',
                (contexto_limpo, termo_limpo)
            )
            linha = cursor.fetchone()

        if not linha:
            return None

        return {
            "alvo_canonico": linha[0],
            "confianca": linha[1],
            "fonte": linha[2],
        }

    def salvar_resolucao(self, contexto: str, termo_original: str, alvo_canonico: str, confianca: str, fonte: str = "oraculo"):
        """Salva ou atualiza resolução canônica para reaproveitar sem consultar o Oráculo novamente."""
        if not self.memoria_ativa:
            return

        contexto_limpo = (contexto or "").strip().lower()
        termo_limpo = (termo_original or "").strip().lower()
        alvo_limpo = (alvo_canonico or "").strip()
        confianca_limpa = (confianca or "BAIXA").strip().upper()
        fonte_limpa = (fonte or "oraculo").strip().lower()

        if not contexto_limpo or not termo_limpo or not alvo_limpo:
            return

        with sqlite3.connect(self.caminho_db) as conexao:
            cursor = conexao.cursor()
            cursor.execute(
                '''
                INSERT INTO cache_resolucoes (contexto, termo_original, alvo_canonico, confianca, fonte)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(contexto, termo_original)
                DO UPDATE SET
                    alvo_canonico = excluded.alvo_canonico,
                    confianca = excluded.confianca,
                    fonte = excluded.fonte,
                    data_registo = CURRENT_TIMESTAMP
                ''',
                (contexto_limpo, termo_limpo, alvo_limpo, confianca_limpa, fonte_limpa)
            )
            conexao.commit()

    def buscar_plano_geral(self, pedido_original: str):
        """Busca um plano de ação já aprendido para um pedido semelhante."""
        if not self.memoria_ativa:
            return None

        pedido = (pedido_original or "").strip().lower()
        if not pedido:
            return None

        with sqlite3.connect(self.caminho_db) as conexao:
            cursor = conexao.cursor()
            cursor.execute(
                '''
                SELECT categoria, alvo_principal, alvo_secundario, plataforma_preferida, confianca, fonte
                FROM cache_planos_gerais
                WHERE pedido_original = ?
                ORDER BY data_registo DESC
                LIMIT 1
                ''',
                (pedido,)
            )
            linha = cursor.fetchone()

        if not linha:
            return None

        return {
            "categoria": linha[0],
            "alvo_principal": linha[1],
            "alvo_secundario": linha[2],
            "plataforma_preferida": linha[3],
            "confianca": linha[4],
            "fonte": linha[5],
        }

    def buscar_planos_gerais_candidatos(self, pedido_original: str, limite: int = 30):
        """Retorna candidatos de planos para matching por similaridade fora do SQL."""
        if not self.memoria_ativa:
            return []

        pedido = (pedido_original or "").strip().lower()
        if not pedido:
            return []

        tokens = [t for t in pedido.split() if len(t) >= 3]
        with sqlite3.connect(self.caminho_db) as conexao:
            cursor = conexao.cursor()

            if tokens:
                filtros = " OR ".join(["pedido_original LIKE ?" for _ in tokens])
                params = [f"%{t}%" for t in tokens]
                params.append(int(limite))
                cursor.execute(
                    f'''
                    SELECT pedido_original, categoria, alvo_principal, alvo_secundario, plataforma_preferida, confianca, fonte
                    FROM cache_planos_gerais
                    WHERE {filtros}
                    ORDER BY data_registo DESC
                    LIMIT ?
                    ''',
                    params
                )
            else:
                cursor.execute(
                    '''
                    SELECT pedido_original, categoria, alvo_principal, alvo_secundario, plataforma_preferida, confianca, fonte
                    FROM cache_planos_gerais
                    ORDER BY data_registo DESC
                    LIMIT ?
                    ''',
                    (int(limite),)
                )

            linhas = cursor.fetchall()

        retorno = []
        for linha in linhas:
            retorno.append({
                "pedido_original": linha[0],
                "categoria": linha[1],
                "alvo_principal": linha[2],
                "alvo_secundario": linha[3],
                "plataforma_preferida": linha[4],
                "confianca": linha[5],
                "fonte": linha[6],
            })
        return retorno

    def salvar_plano_geral(
        self,
        pedido_original: str,
        categoria: str,
        alvo_principal: str,
        alvo_secundario: str = "",
        plataforma_preferida: str = "auto",
        confianca: str = "MEDIA",
        fonte: str = "oraculo",
    ):
        """Salva o plano de execução de um pedido geral para reaproveitar no futuro."""
        if not self.memoria_ativa:
            return

        pedido = (pedido_original or "").strip().lower()
        categoria_limpa = (categoria or "conversa").strip().lower()
        alvo_principal_limpo = (alvo_principal or "").strip()
        alvo_secundario_limpo = (alvo_secundario or "").strip()
        plataforma_limpa = (plataforma_preferida or "auto").strip().lower()
        confianca_limpa = (confianca or "MEDIA").strip().upper()
        fonte_limpa = (fonte or "oraculo").strip().lower()

        if not pedido or not alvo_principal_limpo:
            return

        with sqlite3.connect(self.caminho_db) as conexao:
            cursor = conexao.cursor()
            cursor.execute(
                '''
                INSERT INTO cache_planos_gerais
                (pedido_original, categoria, alvo_principal, alvo_secundario, plataforma_preferida, confianca, fonte)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pedido_original)
                DO UPDATE SET
                    categoria = excluded.categoria,
                    alvo_principal = excluded.alvo_principal,
                    alvo_secundario = excluded.alvo_secundario,
                    plataforma_preferida = excluded.plataforma_preferida,
                    confianca = excluded.confianca,
                    fonte = excluded.fonte,
                    data_registo = CURRENT_TIMESTAMP
                ''',
                (
                    pedido,
                    categoria_limpa,
                    alvo_principal_limpo,
                    alvo_secundario_limpo,
                    plataforma_limpa,
                    confianca_limpa,
                    fonte_limpa,
                )
            )
            conexao.commit()