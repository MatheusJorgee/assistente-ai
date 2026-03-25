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