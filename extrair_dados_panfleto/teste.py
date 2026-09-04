import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

CHROMEDRIVER = ChromeDriverManager().install()

def baixar_todas_as_paginas():
    url = "https://www.tiendeo.com.br/Encartes-Catalogos/assai-atacadista"
    
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    
    driver = webdriver.Chrome(service=Service(CHROMEDRIVER), options=options)
    pasta_destino = "encarte_assai_completo"
    os.makedirs(pasta_destino, exist_ok=True)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        print("Acessando a página do encarte no Tiendeo...")
        driver.get(url)
        time.sleep(3)
        
        print("Clicando na capa do encarte para abrir o visualizador completo...")
        wait = WebDriverWait(driver, 10)
        capa = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "img[data-testid='main_flyer_cover']")))
        driver.execute_script("arguments[0].click();", capa)
        time.sleep(3)
        
        print("Rolando o visualizador para carregar todas as páginas no DOM...")
        ultimo_tamanho = driver.execute_script("return document.body.scrollHeight")
        for _ in range(15):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
            tamanho_atual = driver.execute_script("return document.body.scrollHeight")
            if tamanho_atual == ultimo_tamanho:
                break
            ultimo_tamanho = tamanho_atual
            
        imagens = driver.find_elements(By.CSS_SELECTOR, "img.css-uwwqev.e1uluwxs0")
        
        urls_unicas = []
        for img in imagens:
            img_url = img.get_attribute("src")
            if img_url and "page_assets" in img_url and img_url not in urls_unicas:
                urls_unicas.append(img_url)
                
        print(f"Total de páginas de encarte encontradas: {len(urls_unicas)}")
        
        for idx, img_url in enumerate(urls_unicas, start=1):
            print(f"Baixando página {idx}...")
            resp = requests.get(img_url, headers=headers)
            
            if resp.status_code == 200:
                extensao = "webp" if "webp" in img_url.lower() else "jpeg"
                caminho = os.path.join(pasta_destino, f"pagina_{idx:02d}.{extensao}")
                with open(caminho, "wb") as f:
                    f.write(resp.content)
                print(f"-> Salvo com sucesso: {caminho}")
            else:
                print(f"-> Erro HTTP {resp.status_code} ao baixar a imagem {idx}")

        print(f"\nProcesso concluído! Todas as imagens foram salvas na pasta '{pasta_destino}'.")

    except Exception as e:
        print(f"Ocorreu um erro durante a execução: {e}")
    finally:
        driver.quit()
        print("Driver encerrado.")

if __name__ == "__main__":
    baixar_todas_as_paginas()