from duckduckgo_search import DDGS # <-- Adicionar aos imports

class OSAutomation:
    def controlar_energia(self, acao: str, delay: int = 10, **kwargs) -> str:
        """Controla energia do sistema: shutdown, restart, sleep. Absorve parâmetros extra do Gemini.
        
        Args:
            acao (str): 'shutdown' (desligar), 'restart' (reiniciar), 'sleep' (suspender)
            delay (int): Segundos para aguardar antes de executar (padrão: 10)
            
        Returns:
            str: Mensagem de resultado
        """
        acao_lower = acao.lower().strip()
        
        # Normalizar comandos
        if acao_lower in ['desligar', 'shutdown', 'shudown', 'deslizar']:
            acao_normalizada = 'shutdown'
            msg_user = f"Computador será desligado em {delay} segundos."
        elif acao_lower in ['reiniciar', 'restart', 'reboot', 're-iniciar']:
            acao_normalizada = 'restart'
            msg_user = f"Computador será reiniciado em {delay} segundos."
        elif acao_lower in ['dormir', 'sleep', 'suspender', 'hibernar', 'dormer']:
            acao_normalizada = 'sleep'
            msg_user = "Computador entrando em modo de suspensão."
        else:
            return f"Ação desconhecida: '{acao}'. Use: desligar (shutdown), reiniciar (restart), ou dormir (sleep)."
        
        try:
            sistema = os.name
            
            if sistema == 'nt':  # Windows
                if acao_normalizada == 'shutdown':
                    os.system(f'shutdown /s /t {delay}')
                elif acao_normalizada == 'restart':
                    os.system(f'shutdown /r /t {delay}')
                else:  # sleep
                    os.system('rundll32.exe powrprof.dll,SetSuspendState 0,1,0')
            
            else:  # Linux/Mac
                if acao_normalizada == 'shutdown':
                    os.system(f'shutdown -h +{delay // 60}')
                elif acao_normalizada == 'restart':
                    os.system(f'shutdown -r +{delay // 60}')
                else:  # sleep
                    os.system('systemctl suspend')
            
            print(f">>> [ENERGIA] {msg_user}")
            return msg_user
            
        except Exception as e:
            return f"Erro ao executar controle de energia: {str(e)}"
        
    def pesquisar_internet_silenciosa(self, query: str) -> str:
        """
        Realiza uma pesquisa real na web sem abrir o navegador.
        Usa Playwright com DuckDuckGo, fallback para DuckDuckGo API JSON.
        Retorna os 3 principais resultados em formato de texto para o LLM processar.
        """
        print(f">>> [WEB SCALPEL] Extraindo dados da internet para: '{query}'...")
        
        def _buscar_playwright():
            try:
                from playwright.sync_api import sync_playwright
                import time
                
                resultados = []
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    
                    url_ddg = f"https://duckduckgo.com/?q={query}&t=h_&ia=web"
                    
                    try:
                        page.goto(url_ddg, wait_until="domcontentloaded", timeout=10000)
                        time.sleep(2)
                        
                        results_html = page.query_selector_all('[data-testid="result"]')
                        if not results_html:
                            results_html = page.query_selector_all('.result')
                        
                        for result in results_html[:3]:
                            try:
                                link_elem = result.query_selector('a[data-testid="result-title-a"]')
                                if not link_elem:
                                    link_elem = result.query_selector('a')
                                
                                if link_elem:
                                    titulo = link_elem.text_content()
                                    url_res = link_elem.get_attribute('href')
                                    
                                    desc_elem = result.query_selector('[data-testid="result-snippet"]')
                                    if not desc_elem:
                                        desc_elem = result.query_selector('.result__snippet')
                                    
                                    descricao = desc_elem.text_content() if desc_elem else 'Descrição indisponível'
                                    
                                    resultados.append({
                                        'titulo': titulo.strip(),
                                        'descricao': descricao.strip(),
                                        'url': url_res
                                    })
                            except:
                                continue
                        
                    finally:
                        browser.close()
                
                return resultados if resultados else None
            except:
                return None
        
        def _buscar_ddg_api():
            try:
                import requests
                
                url = 'https://api.duckduckgo.com/'
                params = {'q': query, 'format': 'json', 'no_html': 1}
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                
                response = requests.get(url, params=params, headers=headers, timeout=8)
                data = response.json()
                resultados = []
                
                if data.get('Heading') or data.get('Abstract'):
                    resultados.append({
                        'titulo': data.get('Heading', 'Resultado'),
                        'descricao': data.get('Abstract', ''),
                        'url': data.get('AbstractURL', '')
                    })
                
                if 'RelatedTopics' in data and data['RelatedTopics']:
                    for topic in data['RelatedTopics'][:2]:
                        if 'Text' in topic and 'FirstURL' in topic:
                            resultados.append({
                                'titulo': topic.get('FirstURL', '').split('/')[-1],
                                'descricao': topic['Text'][:150],
                                'url': topic['FirstURL']
                            })
                
                return resultados if resultados else None
            except:
                return None
        
        try:
            resultados = _buscar_playwright()
            
            if not resultados:
                resultados = _buscar_ddg_api()
            
            if not resultados:
                return "AVISO: Não consegui extrair informações neste momento. Tenta novamente ou reformula a pergunta."
            
            contexto_extraido = "RESULTADOS DA PESQUISA ONLINE:\n"
            for i, r in enumerate(resultados, 1):
                contexto_extraido += f"[{i}] Título: {r['titulo']}\nDescrição: {r['descricao']}\nURL: {r['url']}\n\n"
            
            return contexto_extraido
            
        except Exception as e:
            print(f">>> [ERRO WEB SCALPEL] {str(e)}")
            return "ERRO DE REDE: Não consegui aceder aos motores de busca. Tenta novamente em alguns minutos."
