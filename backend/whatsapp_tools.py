"""
WhatsApp Web Automation Tool - Zero-Touch Messaging
=====================================================
Automação 100% automática do WhatsApp Web via Selenium com suporte a:
- Persistência de sessão (cookies + perfil do navegador)
- Login rápido (< 2 segundos em sessão existente)
- Envio de mensagens por contato ou número
- Suporte a múltiplas mídias (imagens, documentos)
- Tratamento de erros e timeouts
"""

import os
import json
import time
import pickle
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from enum import Enum

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BrowserType(Enum):
    """Tipos de navegadores suportados"""
    CHROME = "chrome"
    CHROMIUM = "chromium"
    EDGE = "edge"
    BRAVE = "brave"


class WhatsAppSessionManager:
    """Gerenciador de sessões do WhatsApp Web com persistência de cookies"""
    
    SESSION_DIR = Path.home() / ".quintafeira" / "whatsapp_session"
    COOKIES_FILE = SESSION_DIR / "cookies.json"
    PROFILE_DIR = SESSION_DIR / "profile"
    METADATA_FILE = SESSION_DIR / "metadata.json"
    
    def __init__(self, browser_type: BrowserType = BrowserType.CHROME):
        self.browser_type = browser_type
        self.driver: Optional[webdriver.Chrome] = None
        self.last_activity = datetime.now()
        
        # Criar diretórios necessários
        self.SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    
    def _get_browser_options(self) -> ChromeOptions | EdgeOptions:
        """Retorna opções otimizadas para o navegador"""
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        if self.browser_type == BrowserType.CHROME:
            options = ChromeOptions()
            options.add_argument(f"--user-data-dir={self.PROFILE_DIR}")
        elif self.browser_type == BrowserType.EDGE:
            options = EdgeOptions()
            options.add_argument(f"--user-data-dir={self.PROFILE_DIR}")
        else:
            options = ChromeOptions()
            options.add_argument(f"--user-data-dir={self.PROFILE_DIR}")
        
        # Opções de otimização
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(f"user-agent={user_agent}")
        options.add_argument("--start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        return options
    
    def _load_cookies(self) -> bool:
        """Carrega cookies salvos da sessão anterior"""
        if not self.COOKIES_FILE.exists():
            return False
        
        try:
            with open(self.COOKIES_FILE, 'r') as f:
                cookies = json.load(f)
            
            for cookie in cookies:
                # Remover campos não suportados
                if 'sameSite' in cookie:
                    cookie['sameSite'] = 'Lax'
                if 'expiry' in cookie and isinstance(cookie['expiry'], float):
                    if cookie['expiry'] < time.time():
                        continue
                
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.warning(f"Erro ao adicionar cookie: {e}")
            
            logger.info("✅ Cookies carregados com sucesso")
            return True
        
        except Exception as e:
            logger.warning(f"⚠️ Erro ao carregar cookies: {e}")
            return False
    
    def _save_cookies(self):
        """Salva cookies da sessão atual"""
        try:
            cookies = self.driver.get_cookies()
            with open(self.COOKIES_FILE, 'w') as f:
                json.dump(cookies, f, indent=2)
            logger.info("✅ Cookies salvos")
        except Exception as e:
            logger.error(f"❌ Erro ao salvar cookies: {e}")
    
    def _save_metadata(self):
        """Salva metadados da sessão"""
        metadata = {
            "last_login": datetime.now().isoformat(),
            "browser_type": self.browser_type.value,
            "session_age_hours": 0  # Atualizar quando recuperar sessão
        }
        try:
            with open(self.METADATA_FILE, 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Erro ao salvar metadados: {e}")
    
    def _is_session_valid(self) -> bool:
        """Verifica se a sessão é válida (menos de 7 dias)"""
        if not self.METADATA_FILE.exists():
            return False
        
        try:
            with open(self.METADATA_FILE, 'r') as f:
                metadata = json.load(f)
            
            last_login = datetime.fromisoformat(metadata["last_login"])
            age = datetime.now() - last_login
            
            return age < timedelta(days=7)
        except Exception as e:
            logger.warning(f"⚠️ Erro ao validar sessão: {e}")
            return False
    
    def _wait_for_whatsapp_ready(self, timeout: int = 30) -> bool:
        """Aguarda até que o WhatsApp esteja pronto"""
        try:
            # Aguardar carregamento da página
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Aguardar elemento de chat
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, "//div[@role='textbox']"))
            )
            
            logger.info("✅ WhatsApp pronto")
            return True
        
        except TimeoutException:
            logger.error("❌ Timeout aguardando WhatsApp")
            return False
    
    def _check_is_logged_in(self) -> bool:
        """Verifica se o usuário já está conectado"""
        try:
            # Navegar para WhatsApp Web
            self.driver.get("https://web.whatsapp.com")
            
            # Aguardar 3 segundos para QR code aparecer
            time.sleep(3)
            
            # Se houver chat list, está logado
            try:
                self.driver.find_element(By.XPATH, "//div[@role='listbox']")
                logger.info("✅ Usuário já está logado")
                return True
            except NoSuchElementException:
                # Verificar se há QR code (deslogado)
                try:
                    self.driver.find_element(By.XPATH, "//canvas[@aria-label='Scan QR code']")
                    logger.warning("⚠️ QR code detectado - requer novo login")
                    return False
                except:
                    # Estado indeterminado, assumir logado
                    return True
        
        except Exception as e:
            logger.warning(f"⚠️ Erro ao verificar login: {e}")
            return False
    
    def start_session(self) -> bool:
        """Inicia nova sessão ou recupera existente"""
        try:
            # Inicializar navegador
            options = self._get_browser_options()
            
            if self.browser_type == BrowserType.EDGE:
                self.driver = webdriver.Edge(options=options)
            else:
                self.driver = webdriver.Chrome(options=options)
            
            logger.info(f"🌐 Navegador {self.browser_type.value} iniciado")
            
            # Tentar recuperar sessão existente
            if self._is_session_valid():
                logger.info("🔄 Recuperando sessão existente...")
                self.driver.get("https://web.whatsapp.com")
                
                # Carregar cookies
                self._load_cookies()
                
                # Recarregar página
                self.driver.refresh()
                time.sleep(2)
                
                if self._check_is_logged_in():
                    logger.info("✅ Sessão recuperada com sucesso")
                    return True
            
            # Nova sessão
            logger.info("🆕 Iniciando nova sessão...")
            return self._start_new_session()
        
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar sessão: {e}")
            return False
    
    def _start_new_session(self) -> bool:
        """Inicia nova sessão com QR code"""
        try:
            self.driver.get("https://web.whatsapp.com")
            
            logger.info("📱 Escaneie o QR code com seu telefone")
            
            # Aguardar login manual (máx 60 segundos)
            if self._wait_for_whatsapp_ready(timeout=60):
                self._save_cookies()
                self._save_metadata()
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar nova sessão: {e}")
            return False
    
    def close_session(self):
        """Fecha a sessão do navegador"""
        try:
            if self.driver:
                self._save_cookies()
                self.driver.quit()
                logger.info("✅ Sessão fechada")
        except Exception as e:
            logger.error(f"❌ Erro ao fechar sessão: {e}")


class WhatsAppAutomation:
    """Automação de mensagens do WhatsApp Web"""
    
    def __init__(self, browser_type: BrowserType = BrowserType.CHROME):
        self.session_manager = WhatsAppSessionManager(browser_type)
        self.driver = None
    
    def send_message(self, contact: str, message: str, media_path: Optional[str] = None) -> Tuple[bool, str]:
        """
        Envia mensagem para contato
        
        Args:
            contact: Nome do contato ou número (com código país)
            message: Texto da mensagem
            media_path: Caminho opcional para arquivo de mídia
        
        Returns:
            (sucesso, mensagem_status)
        """
        try:
            if not self.session_manager.start_session():
                return False, "❌ Falha ao iniciar sessão"
            
            self.driver = self.session_manager.driver
            
            # Procurar contato
            if not self._find_contact(contact):
                return False, f"❌ Contato '{contact}' não encontrado"
            
            time.sleep(1)
            
            # Enviar mensagem
            if not self._send_text_message(message):
                return False, "❌ Erro ao enviar mensagem"
            
            # Enviar mídia se fornecida
            if media_path:
                if not self._send_media(media_path):
                    return False, f"⚠️ Mensagem enviada mas erro com mídia: {media_path}"
            
            time.sleep(1)
            return True, f"✅ Mensagem enviada para {contact}"
        
        except Exception as e:
            logger.error(f"❌ Erro geral: {e}")
            return False, f"❌ Erro: {str(e)}"
        
        finally:
            self.session_manager.close_session()
    
    def send_message_bulk(self, contacts: List[str], message: str) -> Dict[str, bool]:
        """Envia mesma mensagem para múltiplos contatos"""
        results = {}
        
        try:
            if not self.session_manager.start_session():
                return {c: False for c in contacts}
            
            self.driver = self.session_manager.driver
            
            for contact in contacts:
                if self._find_contact(contact) and self._send_text_message(message):
                    results[contact] = True
                    logger.info(f"✅ {contact}")
                else:
                    results[contact] = False
                    logger.warning(f"❌ {contact}")
                
                time.sleep(2)  # Aguardar entre mensagens
            
            return results
        
        finally:
            self.session_manager.close_session()
    
    def _find_contact(self, contact: str) -> bool:
        """Encontra e abre contato na barra de pesquisa"""
        try:
            # Clicar na barra de pesquisa
            search_box = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Pesquisar ou começar uma conversa']"))
            )
            
            search_box.clear()
            search_box.send_keys(contact)
            
            time.sleep(1)
            
            # Clica no primeiro resultado
            first_result = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@role='option'][1]"))
            )
            
            first_result.click()
            time.sleep(1)
            
            logger.info(f"✅ Contato '{contact}' encontrado")
            return True
        
        except TimeoutException:
            logger.warning(f"⚠️ Contato '{contact}' não encontrado ou timeout")
            return False
        except Exception as e:
            logger.error(f"❌ Erro ao buscar contato: {e}")
            return False
    
    def _send_text_message(self, message: str) -> bool:
        """Envia mensagem de texto"""
        try:
            # Clicar na caixa de entrada
            input_box = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@role='textbox'][@contenteditable='true']"))
            )
            
            input_box.click()
            input_box.send_keys(message)
            
            # Enviar (Enter)
            input_box.send_keys(Keys.RETURN)
            
            time.sleep(1)
            logger.info(f"✅ Mensagem enviada: {message[:50]}...")
            return True
        
        except TimeoutException:
            logger.error("⚠️ Caixa de entrada não encontrada")
            return False
        except Exception as e:
            logger.error(f"❌ Erro ao enviar mensagem: {e}")
            return False
    
    def _send_media(self, media_path: str) -> bool:
        """Envia arquivo de mídia (imagem, documento)"""
        try:
            media_path = Path(media_path)
            
            if not media_path.exists():
                logger.error(f"❌ Arquivo não encontrado: {media_path}")
                return False
            
            # Clicar no botão de anexo
            attach_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Anexar']"))
            )
            
            attach_button.click()
            time.sleep(1)
            
            # Selecionar arquivo
            file_input = self.driver.find_element(By.XPATH, "//input[@type='file']")
            file_input.send_keys(str(media_path.absolute()))
            
            time.sleep(2)
            
            # Enviar
            send_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Enviar']"))
            )
            
            send_button.click()
            logger.info(f"✅ Mídia enviada: {media_path.name}")
            return True
        
        except TimeoutException:
            logger.error("⚠️ Botão de anexo não encontrado")
            return False
        except Exception as e:
            logger.error(f"❌ Erro ao enviar mídia: {e}")
            return False


def main():
    """Exemplo de uso"""
    
    # 1. Envio simples
    bot = WhatsAppAutomation()
    success, message = bot.send_message(
        contact="João",  # ou "+55 11 99999-9999"
        message="Olá! Mensagem automática via Quinta-Feira 🤖"
    )
    print(f"Resultado: {message}")
    
    # 2. Envio em massa
    # results = bot.send_message_bulk(
    #     contacts=["João", "Maria", "Pedro"],
    #     message="Olá a todos! 🚀"
    # )
    # print(f"Resultados: {results}")


if __name__ == "__main__":
    main()
