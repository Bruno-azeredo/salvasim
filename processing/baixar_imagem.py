from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import warnings
import time
import re
import os
import requests

warnings.filterwarnings("ignore")

CHROMEDRIVER = ChromeDriverManager().install()
MAX_WORKERS = 5

# ===========================
# DRIVER
# ===========================

def criar_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.page_load_strategy = "eager"
    
    driver = webdriver.Chrome(service=Service(CHROMEDRIVER), options=options)
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(10)
    return driver

# ===========================
# CONFIGURAR CEP
# ===========================

def configurar_cep(driver):
    tentativas_cep = 10

    for tentativa in range(tentativas_cep):
        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

            botao_cep = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'button[data-test-id="regionalization-bar-zip-btn-desktop"]'))
            )

            driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", botao_cep)
            time.sleep(3)

            try:
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-test-id="regionalization-bar-zip-btn-desktop"]'))
                ).click()
            except Exception:
                driver.execute_script("arguments[0].click();", botao_cep)

            entrega = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, '//h2[contains(normalize-space(), "Entrega em Casa")]'))
            )
            driver.execute_script("arguments[0].click();", entrega)

            input_cep = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, "location-search")))
            input_cep.click()
            input_cep.clear()
            input_cep.send_keys("06855-400")

            numero = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, '//input[@placeholder="Ex: 6157"]')))
            numero.click()
            numero.clear()
            numero.send_keys("100")

            confirmar = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, '//button[@type="button" and normalize-space()="Confirmar"]'))
            )
            driver.execute_script("arguments[0].click();", confirmar)

            WebDriverWait(driver, 20).until(EC.invisibility_of_element_located((By.ID, "location-search")))

            loja_atual = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//span[@data-test-id="regionalization-bar-seller-delivery-by" and contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "itapecerica da serra")]'))
            )

            print(f"✅ CEP configurado — {loja_atual.text.strip()}")
            return True
        except Exception:
            time.sleep(3)

    print("❌ Erro ao configurar o CEP.")
    return False

# ===========================
# ABRIR PÁGINA
# ===========================

def abrir_pagina(driver, url, tentativas=3):
    for tentativa in range(tentativas):
        try:
            driver.get(url)
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            return True, driver
        except:
            if tentativa == tentativas - 1:
                return False, driver
            time.sleep(2)

# ===========================
# PROCESSAR CATEGORIA
# ===========================

def processar_categoria(url):
    driver = criar_driver()
    dados = []

    try:
        driver.get("https://www.atacadao.com.br")
        time.sleep(3)
        configurar_cep(driver)

        for page_num in range(1, 51):
            page_url = f"{url}?page={page_num}"
            ok, driver = abrir_pagina(driver, page_url)
            if not ok: break

            time.sleep(3)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(5)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            produtos = soup.select('[data-testid="product-link"]')

            if not produtos: break

            for link_elem in produtos:
                try:
                    nome = link_elem.text.strip()
                    container = link_elem.find_parent("li") or link_elem.find_parent("article") or link_elem.find_parent("div")
                    
                    preco_elem = container.select_one("p.text-sm.text-neutral-500.font-bold")
                    if not preco_elem or not preco_elem.text.strip():
                        preco_elem = container.select_one("p.text-lg.text-neutral-500.font-bold")
                    preco = preco_elem.text.strip() if preco_elem else ""

                    imagem_url = ""
                    if container:
                        img_elem = container.find("img")
                        if img_elem:
                            src = img_elem.get("src") or img_elem.get("data-src") or ""
                            if src:
                                imagem_url = f"https://www.atacadao.com.br{src}" if src.startswith("/") else src

                    if nome and preco and imagem_url:
                        dados.append({"nome": nome, "imagem_url": imagem_url})
                except: continue
        return dados
    finally:
        driver.quit()

# ===========================
# DOWNLOAD DAS IMAGENS NA MÁQUINA
# ===========================

def baixar_imagens(dados):
    pasta_destino = "imagens_produtos"
    os.makedirs(pasta_destino, exist_ok=True)
    print(f"\n📥 Baixando imagens para a pasta local '{pasta_destino}'...")

    for item in dados:
        nome = item.get("nome", "")
        url_img = item.get("imagem_url", "")

        if not nome or not url_img:
            continue

        # Limpa o nome do produto para evitar caracteres inválidos no Windows/Linux
        nome_limpo = re.sub(r'[\\/*?:"<>|]', "", nome).strip().replace(" ", "_")
        
        # Pega a extensão da imagem da URL
        extensao = os.path.splitext(url_img.split("?")[0])[1]
        if not extensao or len(extensao) > 5:
            extensao = ".jpg"

        caminho_arquivo = os.path.join(pasta_destino, f"{nome_limpo}{extensao}")

        try:
            resposta = requests.get(url_img, timeout=10)
            if resposta.status_code == 200:
                with open(caminho_arquivo, "wb") as f:
                    f.write(resposta.content)
                print(f"🖼️ Salva: {nome_limpo}{extensao}")
            else:
                print(f"⚠️ Falha ao baixar: {nome}")
        except Exception as e:
            print(f"❌ Erro em '{nome}': {e}")

# ===========================
# MAIN
# ===========================

def main():
    with open("configs/urls.txt", "r") as f:
        urls = [l.strip() for l in f if l.strip()]

    todos_produtos = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(processar_categoria, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                resultado = future.result()
                todos_produtos.extend(resultado)
                print(f"✅ {url} -> {len(resultado)} produtos coletados")
            except Exception as e:
                print(f"❌ Erro em {url}: {e}")
                
    if todos_produtos:
        baixar_imagens(todos_produtos)
        print("\n🎉 Processo finalizado! Todas as imagens foram salvas na sua máquina.")

if __name__ == "__main__":
    main()