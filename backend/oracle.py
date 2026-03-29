import os
import json
from google import genai
from google.genai import types

class OraculoEngine:
    def __init__(self):
        # O Oráculo usa a mesma chave, mas pode usar um modelo diferente (ex: gemini-1.5-pro) 
        # se você precisar de raciocínio mais profundo no futuro. 
        # Por enquanto, o flash bem instruído serve.
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key)
        self.modelo = "gemini-2.5-flash"

    def consultar_comando_tecnico(self, objetivo: str, ambiente: str) -> dict:
        """
        Consulta o modelo superior para descobrir um comando técnico.
        Retorna um dicionário (JSON parseado).
        """
        print(f">>> [ORÁCULO] A pesquisar na rede neural primária: '{objetivo}' para {ambiente}...")
        
        # Prompt estrito para gerar comandos técnicos com foco em segurança.
        prompt_oraculo = f"""
        Você é um Arquiteto Sênior de Automação e Segurança.
        Gere UM comando de terminal mínimo e seguro para cumprir o objetivo: '{objetivo}'.
        Ambiente: {ambiente}.

        Restrições obrigatórias:
        1) Proibido comando destrutivo, persistente ou de escalonamento de privilégio.
        2) Proibido qualquer tentativa de ler, imprimir ou exfiltrar segredos (.env, tokens, chaves, senhas).
        3) Não usar cadeias perigosas com ';', '&&', '||', pipe para bypass ou redirecionamentos arriscados.
        4) Se existir alternativa mais segura, prefira a alternativa mais segura.
        5) Se for Android, preferir 'am start' ou ações diretas do sistema em vez de simulação frágil.

        Classificação de risco:
        - BAIXO: leitura/consulta/abertura sem impacto destrutivo.
        - MEDIO: altera estado reversível do usuário.
        - ALTO: potencial de perda de dados, indisponibilidade ou impacto sensível.

        Responda exclusivamente em JSON válido, sem markdown, sem texto adicional.
        """

        # O Esquema JSON que obriga a IA a responder num formato de software, não de chat.
        esquema_json = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "comando_exato": types.Schema(type=types.Type.STRING, description="O comando de terminal pronto para rodar"),
                "risco": types.Schema(type=types.Type.STRING, description="Classifique como BAIXO, MEDIO ou ALTO"),
                "explicacao": types.Schema(type=types.Type.STRING, description="Resumo técnico de 1 linha do que o comando faz")
            },
            required=["comando_exato", "risco", "explicacao"]
        )

        try:
            # A ARQUITETURA CHAVE AQUI: Temperature = 0.1
            # Reduzimos a criatividade a zero para obtermos precisão matemática.
            resposta = self.client.models.generate_content(
                model=self.modelo,
                contents=prompt_oraculo,
                config=types.GenerateContentConfig(
                    temperature=0.1, 
                    response_mime_type="application/json",
                    response_schema=esquema_json
                )
            )
            
            # Converte a string JSON perfeita de volta para um Dicionário Python
            dados = json.loads(resposta.text)
            return dados
            
        except Exception as e:
            print(f">>> [ERRO ORÁCULO] Falha na consulta cognitiva: {e}")
            return {"comando_exato": "", "risco": "ALTO", "explicacao": "Erro de conexão com o Oráculo."}

    def consultar_identificador_twitch(self, nome_pessoa: str) -> dict:
        """
        Consulta o Oráculo para inferir o possível @/handle da Twitch de uma pessoa.
        Retorna JSON com canal sugerido e nível de confiança.
        """
        print(f">>> [ORÁCULO] A inferir canal Twitch para: '{nome_pessoa}'...")

        prompt = f"""
        Você é um especialista em mapeamento de perfis da Twitch.
        Dado o nome de referência: '{nome_pessoa}', responda com o handle mais provável da Twitch.

        Regras:
        1) Retorne apenas o handle, sem URL, sem @, sem espaços.
        2) Se houver ambiguidade alta, devolva confiança BAIXA e uma sugestão curta de desambiguação.
        3) Não invente com confiança alta quando não houver evidência provável.

        Saída obrigatória: JSON válido, sem markdown.
        """

        esquema = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "canal_twitch": types.Schema(type=types.Type.STRING, description="Handle sugerido da Twitch sem @ e sem URL"),
                "confianca": types.Schema(type=types.Type.STRING, description="ALTA, MEDIA ou BAIXA"),
                "desambiguacao": types.Schema(type=types.Type.STRING, description="Pergunta curta caso a confiança seja baixa")
            },
            required=["canal_twitch", "confianca", "desambiguacao"]
        )

        try:
            resposta = self.client.models.generate_content(
                model=self.modelo,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_schema=esquema
                )
            )
            dados = json.loads(resposta.text)
            return dados
        except Exception as e:
            print(f">>> [ERRO ORÁCULO] Falha ao inferir canal Twitch: {e}")
            return {
                "canal_twitch": "",
                "confianca": "BAIXA",
                "desambiguacao": "Qual é o arroba exato do canal na Twitch?"
            }

    def consultar_alvo_canonico(self, termo: str, contexto: str) -> dict:
        """
        Resolve um termo ambíguo para um alvo canônico conforme o contexto.
        Exemplos de contexto: twitch, youtube, github, instagram, google, web.
        """
        termo = (termo or "").strip()
        contexto = (contexto or "web").strip().lower()
        print(f">>> [ORÁCULO] A inferir alvo canônico para '{termo}' no contexto '{contexto}'...")

        prompt = f"""
        Você é um resolvedor de entidades para automação web.
        Entrada:
        - termo ambíguo: '{termo}'
        - contexto de plataforma: '{contexto}'

        Objetivo:
        - Retornar o identificador canônico mais provável para abrir/pesquisar corretamente.

        Regras:
        1) Se contexto for twitch/youtube/instagram/x/github, retorne handle/slug sem URL e sem @.
        2) Se contexto for web/google genérico, retorne uma frase curta de busca otimizada.
        3) Não invente com confiança ALTA quando houver incerteza.
        4) Em baixa confiança, escreva uma pergunta curta para desambiguação.

        Saída: JSON válido, sem markdown.
        """

        esquema = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "alvo_canonico": types.Schema(type=types.Type.STRING, description="Slug/handle/termo canônico sem URL"),
                "tipo_alvo": types.Schema(type=types.Type.STRING, description="HANDLE, BUSCA, PERFIL, CANAL"),
                "confianca": types.Schema(type=types.Type.STRING, description="ALTA, MEDIA ou BAIXA"),
                "desambiguacao": types.Schema(type=types.Type.STRING, description="Pergunta curta se confiança baixa")
            },
            required=["alvo_canonico", "tipo_alvo", "confianca", "desambiguacao"]
        )

        try:
            resposta = self.client.models.generate_content(
                model=self.modelo,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_schema=esquema
                )
            )
            dados = json.loads(resposta.text)
            return dados
        except Exception as e:
            print(f">>> [ERRO ORÁCULO] Falha ao inferir alvo canônico: {e}")
            return {
                "alvo_canonico": "",
                "tipo_alvo": "BUSCA",
                "confianca": "BAIXA",
                "desambiguacao": "Qual termo exato você quer abrir ou pesquisar?"
            }

    def consultar_busca_musical(self, pedido: str) -> dict:
        """
        Converte pedido musical livre em consulta otimizada, com sugestão de plataforma.
        """
        pedido = (pedido or "").strip()
        print(f">>> [ORÁCULO] A inferir busca musical para: '{pedido}'...")

        prompt = f"""
        Você é um detetive e especialista em descoberta musical para automação.
        Entrada do usuário: '{pedido}'

        Objetivo:
        - Descobrir a música exata e o artista correspondente a partir de dicas do usuário.

        Regras de Dedução (NÍVEL AVANÇADO):
        1) USE O SEU CONHECIMENTO INTERNO: Cruze as informações visuais (clipe, cenário, roupas) e textuais (regras do título).
        2) TRATAMENTO DE PARADOXOS: Humanos costumam misturar memórias. Se a descrição visual apontar para a Música A (ex: Bellyache) e a regra do título apontar para a Música B (ex: idontwannabeyouanymore), priorize a música que obedece à regra do TÍTULO pedida.
        3) Na 'busca_otimizada', retorne APENAS o resultado final resolvido: 'Nome do Artista - Nome da Música'.
        4) Se o usuário não mencionar plataforma, retorne plataforma_preferida = "auto".
        """
        
        esquema = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "raciocinio_detetive": types.Schema(
                    type=types.Type.STRING, 
                    description="Seja direto (máx 3 frases). Analise as dicas. Se houver conflito entre o clipe e a regra do título, explique o conflito e escolha a música baseada no título."
                ),
                "busca_otimizada": types.Schema(type=types.Type.STRING, description="Consulta otimizada para encontrar a música"),
                "plataforma_preferida": types.Schema(type=types.Type.STRING, description="auto, spotify ou youtube"),
                "confianca": types.Schema(type=types.Type.STRING, description="ALTA, MEDIA ou BAIXA"),
                "pergunta_curta": types.Schema(type=types.Type.STRING, description="Pergunta de desambiguação quando confiança for baixa")
            },
            required=["raciocinio_detetive", "busca_otimizada", "plataforma_preferida", "confianca", "pergunta_curta"]
        )

        try:
            resposta = self.client.models.generate_content(
                model=self.modelo,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.15,
                    response_mime_type="application/json",
                    response_schema=esquema
                )
            )
            dados = json.loads(resposta.text)
            
            # --- IMPRIME O PENSAMENTO DO ORÁCULO AQUI ---
            print(f"\n>>> [ORÁCULO PENSANDO] {dados.get('raciocinio_detetive', '')}\n")
            
            return dados
            
        except Exception as e:
            print(f">>> [ERRO ORÁCULO] Falha ao inferir busca musical: {e}")
            return {
                "busca_otimizada": pedido,
                "plataforma_preferida": "auto",
                "confianca": "BAIXA",
                "pergunta_curta": "Pode dizer mais um trecho da música?"
            }
        
    def consultar_plano_geral(self, pedido: str) -> dict:
        """
        Converte um pedido aberto em plano executável (categoria + alvos + plataforma).
        """
        pedido = (pedido or "").strip()
        print(f">>> [ORÁCULO] A inferir plano geral para: '{pedido}'...")

        prompt = f"""
        Você é um roteador de intenções para automação pessoal.
        Entrada: '{pedido}'

        Gere um plano objetivo com categoria e alvos.

        Categorias permitidas:
        - musica
        - abrir_app
        - pesquisar_web
        - terminal
        - conversa

        Regras:
        1) Se for música (inclusive por trecho/letra), categoria = musica.
        2) Se for abrir algo no computador (app/site), categoria = abrir_app.
        3) Se for busca genérica na web, categoria = pesquisar_web.
        4) Use terminal apenas quando claramente for comando técnico/sistema.
        5) Se não houver certeza, confiança BAIXA e uma pergunta curta.

        Saída em JSON válido sem markdown.
        """

        esquema = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "categoria": types.Schema(type=types.Type.STRING, description="musica, abrir_app, pesquisar_web, terminal ou conversa"),
                "alvo_principal": types.Schema(type=types.Type.STRING, description="alvo principal da execução"),
                "alvo_secundario": types.Schema(type=types.Type.STRING, description="parâmetro auxiliar, quando existir"),
                "plataforma_preferida": types.Schema(type=types.Type.STRING, description="auto, spotify, youtube, windows, android ou web"),
                "confianca": types.Schema(type=types.Type.STRING, description="ALTA, MEDIA ou BAIXA"),
                "pergunta_curta": types.Schema(type=types.Type.STRING, description="pergunta curta para desambiguar")
            },
            required=["categoria", "alvo_principal", "alvo_secundario", "plataforma_preferida", "confianca", "pergunta_curta"]
        )

        try:
            resposta = self.client.models.generate_content(
                model=self.modelo,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.15,
                    response_mime_type="application/json",
                    response_schema=esquema
                )
            )
            dados = json.loads(resposta.text)
            
            # --- IMPRIME O PENSAMENTO DO ORÁCULO ---
            print(f"\n>>> [ORÁCULO PENSANDO] {dados.get('raciocinio_detetive', '')}\n")
            
            return dados
        except Exception as e:
            print(f">>> [ERRO ORÁCULO] Falha ao inferir plano geral: {e}")
            return {
                "categoria": "conversa",
                "alvo_principal": pedido,
                "alvo_secundario": "",
                "plataforma_preferida": "auto",
                "confianca": "BAIXA",
                "pergunta_curta": "Pode detalhar melhor o que você quer que eu execute?"
            }
        
        