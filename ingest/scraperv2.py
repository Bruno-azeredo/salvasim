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
import io
from google.cloud import storage

warnings.filterwarnings("ignore")

CHROMEDRIVER = ChromeDriverManager().install()
MAX_WORKERS = 5

# Configurações do Google Cloud Storage
BUCKET_NAME = "econ-itap"

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
# CONFIGURAR CEP (Com Validação de Loja)
# ===========================

def configurar_cep(driver):
    tentativas_cep = 10

    for tentativa in range(tentativas_cep):
        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script(
                    "return document.readyState"
                ) == "complete"
            )

            botao_cep = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        'button[data-test-id="regionalization-bar-zip-btn-desktop"]'
                    )
                )
            )

            driver.execute_script(
                """
                arguments[0].scrollIntoView({
                    block: 'center',
                    inline: 'center'
                });
                """,
                botao_cep
            )

            time.sleep(3)

            try:
                WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (
                            By.CSS_SELECTOR,
                            'button[data-test-id="regionalization-bar-zip-btn-desktop"]'
                        )
                    )
                ).click()

            except Exception:
                driver.execute_script(
                    "arguments[0].click();",
                    botao_cep
                )

            entrega = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        '//h2[contains(normalize-space(), "Entrega em Casa")]'
                    )
                )
            )

            driver.execute_script(
                "arguments[0].click();",
                entrega
            )

            input_cep = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (By.ID, "location-search")
                )
            )

            input_cep.click()
            input_cep.clear()
            input_cep.send_keys("06855-400")

            numero = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        '//input[@placeholder="Ex: 6157"]'
                    )
                )
            )

            numero.click()
            numero.clear()
            numero.send_keys("100")

            confirmar = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        '//button[@type="button" and normalize-space()="Confirmar"]'
                    )
                )
            )

            driver.execute_script(
                "arguments[0].click();",
                confirmar
            )

            WebDriverWait(driver, 20).until(
                EC.invisibility_of_element_located(
                    (By.ID, "location-search")
                )
            )

            loja_atual = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        '//span[@data-test-id="regionalization-bar-seller-delivery-by" and contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "itapecerica da serra")]'
                    )
                )
            )

            nome_loja = loja_atual.text.strip()
            print(f"✅ CEP configurado com sucesso — {nome_loja}")
            return nome_loja
        
        except Exception:
            time.sleep(3)

    print("❌ Erro ao configurar o CEP — não foi possível selecionar a loja de Itapecerica da Serra.")
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
                    
                    # --- BUSCA DE PREÇO ---
                    preco_elem = container.select_one("p.text-sm.text-neutral-500.font-bold")
                    if not preco_elem or not preco_elem.text.strip():
                        preco_elem = container.select_one("p.text-lg.text-neutral-500.font-bold")
                    
                    preco = preco_elem.text.strip() if preco_elem else ""

                    # --- BUSCA DE IMAGEM ---
                    imagem_url = ""
                    if container:
                        img_elem = container.find("img")
                        if img_elem:
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
# GOOGLE CLOUD STORAGE (PARQUET)
# ===========================

def salvar_historico_gcs(df_novo):
    print("🔌 Iniciando cliente do Google Cloud Storage...")
    client = storage.Client()
    
    bucket = client.bucket(BUCKET_NAME)
    print(f"🪣 Acessando o bucket: {BUCKET_NAME}...")
    
    data_hoje = datetime.now().strftime('%Y-%m-%d')
    
    # Adicionamos 'atacadao/' na frente para criar a estrutura de pastas no GCS
    nome_arquivo = f"atacadao/historico_{data_hoje}.parquet"
    blob = bucket.blob(nome_arquivo)
    
    df_final = df_novo
    
    try:
        if blob.exists():
            print(f"📥 Baixando arquivo existente do dia no GCS: {nome_arquivo}...")
            conteudo_bytes = blob.download_as_bytes()
            df_antigo = pd.read_parquet(io.BytesIO(conteudo_bytes))
            df_final = pd.concat([df_antigo, df_novo]).drop_duplicates()
    except Exception as e:
        print(f"⚠️ Aviso ao verificar arquivo existente (normal se for o primeiro do dia): {e}")
    
    buffer = io.BytesIO()
    df_final.to_parquet(buffer, index=False)
    buffer.seek(0)
    
    print(f"☁️ Enviando arquivo do dia para o Google Cloud Storage ({nome_arquivo})...")
    blob.upload_from_file(buffer, content_type="application/octet-stream")
    print("✅ Arquivo diário salvo com sucesso na pasta do Atacadão!")