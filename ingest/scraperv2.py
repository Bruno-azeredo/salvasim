from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import pandas as pd
import warnings
import time
import re
import os
from supabase import create_client

warnings.filterwarnings("ignore")

CHROMEDRIVER = ChromeDriverManager().install()
MAX_WORKERS = 10

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
    try:
        cep_atual = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, '//span[@data-test-id="regionalization-bar-desktop-cep"]'))
        )
        driver.execute_script("arguments[0].click();", cep_atual)

        try:
            entrega = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.XPATH, '//button[.//h2[contains(normalize-space(),"Entrega em Casa")]]'))
            )
            driver.execute_script("arguments[0].click();", entrega)
        except TimeoutException:
            pass

        input_cep = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.ID, "location-search")))
        input_cep.clear()
        input_cep.send_keys("06855-400")

        numero = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, '//input[@placeholder="Ex: 6157"]')))
        numero.clear()
        numero.send_keys("100")

        confirmar = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, '//button[@type="button" and normalize-space()="Confirmar"]'))
        )
        driver.execute_script("arguments[0].click();", confirmar)
        
        WebDriverWait(driver, 30).until(EC.invisibility_of_element_located((By.ID, "location-search")))
        
        loja_atual = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located((By.XPATH, '//span[@data-test-id="regionalization-bar-seller-delivery-by"]'))
        )
        return loja_atual.text.strip()
    except:
        return None

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
# PROCESSAR UMA CATEGORIA
# ===========================

def processar_categoria(url):
    driver = criar_driver()
    dados = []
    data_extracao = datetime.today().strftime("%Y-%m-%d")

    try:
        driver.get("https://www.atacadao.com.br")
        time.sleep(3)
        configurar_cep(driver)

        match = re.search(r'atacadao\.com\.br/([^/]+)/([^/?#]+)', url)
        categoria = match.group(1).lower() if match else ""
        subcategoria = match.group(2).lower() if match else ""

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
                    href = link_elem.get("href", "")
                    link = f"https://www.atacadao.com.br{href}"
                    container = link_elem.find_parent("li") or link_elem.find_parent("article") or link_elem.find_parent("div")
                    
                    preco_elem = container.select_one("p.text-lg.text-neutral-500.font-bold")
                    preco = preco_elem.text.strip() if preco_elem else ""

                    # --- NOVA BUSCA DE IMAGEM ---
                    imagem_url = ""
                    if container:
                        # Tenta pegar a tag img dentro do container do produto
                        img_elem = container.find("img")
                        if img_elem:
                            # Tenta pegar o src normal ou data-src (comum em lazy loading)
                            src = img_elem.get("src") or img_elem.get("data-src") or ""
                            if src:
                                if src.startswith("/"):
                                    imagem_url = f"https://www.atacadao.com.br{src}"
                                else:
                                    imagem_url = src

                    if nome and preco:
                        dados.append({
                            "nome": nome, "preco": preco, "link": link, "imagem_url": imagem_url,
                            "categoria": categoria, "subcategoria": subcategoria,
                            "data_extracao": data_extracao
                        })
                except: continue
        return dados
    finally:
        driver.quit()

# ===========================
# MAIN E SUPABASE
# ===========================

url_db = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url_db, key) if url_db and key else None

def salvar_no_supabase(lista_de_produtos):
    try:
        supabase.table("produtos_atacadao").insert(lista_de_produtos).execute()
        print(f"\n✅ {len(lista_de_produtos)} produtos salvos no Supabase!")
    except Exception as e:
        print(f"\n❌ Erro ao salvar: {e}")

def main():
    with open("configs/urls.txt", "r") as f:
        urls = [l.strip() for l in f if l.strip()]

    dados = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(processar_categoria, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                resultado = future.result()
                dados.extend(resultado)
                print(f"✅ {url} -> {len(resultado)} produtos")
            except Exception as e:
                print(f"❌ Erro em {url}: {e}")
    return dados

if __name__ == "__main__":
    inicio = time.time()
    dados = main()
    if dados:
        salvar_no_supabase(dados)
    print(f"\n⏱ Tempo total: {(time.time()-inicio)/60:.2f} min")