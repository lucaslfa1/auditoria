from playwright.sync_api import sync_playwright
import sys
import time
import os
from pathlib import Path

# Pasta onde os áudios brutos serão salvos temporariamente antes de serem organizados
ROOT_DIR = Path(__file__).resolve().parent.parent
PASTA_DOWNLOADS = ROOT_DIR / "downloads_temp"

sys.path.insert(0, str(ROOT_DIR / "backend"))
from db.connection import get_connection


def get_config(chave: str) -> str:
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT valor FROM configuracoes WHERE chave = %s", (chave,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception as e:
        print(f"Erro ao ler banco de dados: {e}")
        return ""

def extrair_ligacoes():
    URL_LOGIN = get_config('rpa_url_login')
    USUARIO = get_config('rpa_usuario')
    SENHA = get_config('rpa_senha')

    if not URL_LOGIN or not USUARIO or not SENHA:
        print("Erro: As credenciais do RPA não estão configuradas. Por favor, acesse o Dashboard > Configurações Globais e preencha a URL, Usuário e Senha.")
        return

    os.makedirs(PASTA_DOWNLOADS, exist_ok=True)
    
    with sync_playwright() as p:
        # Abre o navegador (headless=False permite que você veja o robô trabalhando como um fantasma)
        browser = p.chromium.launch(headless=False)
        
        # Configura o navegador para aceitar downloads automaticamente na pasta definida
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        print("Acessando a página de login do sistema...")
        page.goto(URL_LOGIN)

        # -------------------------------------------------------------------
        # 1. LOGIN
        # (Os seletores abaixo são exemplos. Será necessário inspecionar a 
        # página real para descobrir os nomes corretos dos campos)
        # -------------------------------------------------------------------
        print("Realizando login...")
        # page.fill("input[name='username']", USUARIO)
        # page.fill("input[name='password']", SENHA)
        # page.click("button[type='submit']")

        # Aguarda a página principal carregar completamente
        page.wait_for_load_state("networkidle")
        
        # -------------------------------------------------------------------
        # 2. NAVEGAR ATÉ A TELA "CONTATO" (conforme imagens fornecidas)
        # -------------------------------------------------------------------
        print("Navegando para a aba de pesquisa de Contatos...")
        # page.click("text=Contato") # Exemplo de clique em um menu
        
        # -------------------------------------------------------------------
        # 3. PREENCHER OS FILTROS DA IMAGEM
        # -------------------------------------------------------------------
        print("Preenchendo filtros (1 dia, ID do funcionário, etc)...")
        
        # Exemplo: Selecionar período "1 dia"
        # page.click("dropdown-periodo") 
        # page.click("text=1 dia")
        
        # Exemplo: Preencher "ID do funcionário" ou "Número manipulado"
        # page.fill("input[placeholder='ID do funcionário']", "11253") 
        
        # Clica no botão azul "Pesquisar" (destacado na sua imagem)
        # page.click("button:has-text('Pesquisar')")
        
        # Aguarda os resultados carregarem na tela
        time.sleep(3)
        
        # -------------------------------------------------------------------
        # 4. SELECIONAR E BAIXAR
        # -------------------------------------------------------------------
        print("Iniciando o download dos áudios...")
        
        # Exemplo: clicar no checkbox para selecionar todas as ligações da lista
        # page.click("input.selecionar-todos")
        
        # Espera o sistema de telefonia gerar o arquivo e inicia o download
        # with page.expect_download() as download_info:
        #     page.click("button:has-text('Exportar')") # ou o botão equivalente de download
        
        # download = download_info.value
        # caminho_final = PASTA_DOWNLOADS / download.suggested_filename
        # download.save_as(caminho_final)
        
        # print(f"Download concluído com sucesso e salvo em: {caminho_final}")
        
        time.sleep(5) # Pausa rápida para você ver o resultado antes de fechar
        browser.close()

if __name__ == "__main__":
    print("Iniciando robô de extração (RPA)...")
    # extrair_ligacoes() # Descomente esta linha quando preencher os dados acima
    print("Script estruturado. Preencha as URLs e seletores antes de executar.")
