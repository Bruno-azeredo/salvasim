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

warnings.filterwarnings("ignore")

CHROMEDRIVER = ChromeDriverManager().install()
# ===========================
# CONFIG
# ===========================

MAX_WORKERS = 10

options = webdriver.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--window-size=1920,1080")


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
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-features=Translate,BackForwardCache")

    options.page_load_strategy = "eager"

    driver = webdriver.Chrome(
        service=Service(CHROMEDRIVER),
        options=options
    )

    driver.set_page_load_timeout(60)
    driver.implicitly_wait(10)

    return driver


# ===========================
# CONFIGURAR CEP
# ===========================

def configurar_cep(driver):

    try:

        print("🔧 Configurando CEP...")

        # ----------------------------------------------------
        # Abre modal de CEP
        # ----------------------------------------------------
        cep_atual = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    '//span[@data-test-id="regionalization-bar-desktop-cep"]'
                )
            )
        )

        driver.execute_script("arguments[0].click();", cep_atual)

        # ----------------------------------------------------
        # Entrega em Casa
        # ----------------------------------------------------
        try:

            entrega = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        '//button[.//h2[contains(normalize-space(),"Entrega em Casa")]]'
                    )
                )
            )

            driver.execute_script("arguments[0].click();", entrega)

            print("✅ Entrega em Casa")

        except TimeoutException:
            pass

        # ----------------------------------------------------
        # CEP
        # ----------------------------------------------------
        input_cep = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable(
                (
                    By.ID,
                    "location-search"
                )
            )
        )

        input_cep.clear()
        input_cep.send_keys("06855-400")

        print("✅ CEP digitado")

        # ----------------------------------------------------
        # Número
        # ----------------------------------------------------
        numero = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    '//input[@placeholder="Ex: 6157"]'
                )
            )
        )

        numero.clear()
        numero.send_keys("100")

        print("✅ Número digitado")

        # ----------------------------------------------------
        # Confirmar
        # ----------------------------------------------------
        confirmar = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    '//button[@type="button" and normalize-space()="Confirmar"]'
                )
            )
        )

        driver.execute_script("arguments[0].click();", confirmar)

        print("✅ CEP confirmado")

        # ----------------------------------------------------
        # Aguarda o modal fechar
        # ----------------------------------------------------
        WebDriverWait(driver, 30).until(
            EC.invisibility_of_element_located(
                (
                    By.ID,
                    "location-search"
                )
            )
        )

        # ----------------------------------------------------
        # Aguarda o cabeçalho atualizar
        # ----------------------------------------------------
        loja_atual = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located(
                (
                    By.XPATH,
                    '//span[@data-test-id="regionalization-bar-seller-delivery-by"]'
                )
            )
        )

        texto_loja = loja_atual.text.strip()

        print(f"🏪 Loja atual: {texto_loja}")

        print("✅ CEP configurado com sucesso")

        return texto_loja

    except Exception as e:

        print(f"❌ Erro ao configurar CEP: {e}")

        # Salva evidências para depuração
        try:
            print(f"📍 URL atual: {driver.current_url}")
            driver.save_screenshot("erro_configurar_cep.png")
        except:
            pass

        return None

# ===========================
# ABRIR PÁGINA
# ===========================

def abrir_pagina(driver, url, tentativas=5):

    for tentativa in range(tentativas):

        try:

            driver.get(url)

            WebDriverWait(driver,20).until(
                EC.presence_of_element_located(
                    (
                        By.TAG_NAME,
                        "body"
                    )
                )
            )

            return True, driver

        except Exception as e:

            print(
                f"⚠ Tentativa {tentativa+1}/{tentativas}"
            )

            print(e)

            if "Timed out receiving message from renderer" in str(e):

                try:
                    driver.quit()
                except:
                    pass

                driver = criar_driver()

                driver.get("https://www.atacadao.com.br")

                time.sleep(3)

                configurar_cep(driver)

                driver.get(url)

                return True, driver

# ===========================
# PROCESSAR UMA CATEGORIA
# ===========================

def processar_categoria(url):

    driver = criar_driver()

    dados = []

    data_extracao = datetime.today().strftime("%Y-%m-%d")

    try:

        print(f"\n🚀 Iniciando categoria: {url}")

        driver.get("https://www.atacadao.com.br")
        time.sleep(3)
        configurar_cep(driver)

        match = re.search(
            r'atacadao\.com\.br/([^/]+)/([^/?#]+)',
            url
        )

        if match:
            categoria = match.group(1).lower()
            subcategoria = match.group(2).lower()
        else:
            categoria = ""
            subcategoria = ""

        print(f"🧭 {categoria} | {subcategoria}")

        page_num = 1

        while page_num <= 50:

            page_url = f"{url}?page={page_num}"

            ok, driver = abrir_pagina(driver, page_url)

            if not ok:
                print(f"❌ Falha ao abrir {page_url}")
                break

            time.sleep(3)

            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )

            time.sleep(5)

            soup = BeautifulSoup(
                driver.page_source,
                "html.parser"
            )

            produtos = soup.select(
                '[data-testid="product-link"]'
            )

            print(
                f"Página {page_num}: {len(produtos)} produtos"
            )

            if not produtos:

                print("🔄 Recarregando página...")

                driver.refresh()

                time.sleep(8)

                soup = BeautifulSoup(
                    driver.page_source,
                    "html.parser"
                )

                produtos = soup.select(
                    '[data-testid="product-link"]'
                )

                if not produtos:
                    break

            for link_elem in produtos:

                try:

                    nome = link_elem.text.strip()

                    href = link_elem.get("href","")

                    link = (
                        f"https://www.atacadao.com.br{href}"
                        if href else ""
                    )

                    container = (
                        link_elem.find_parent("li")
                        or link_elem.find_parent("article")
                        or link_elem.find_parent("div")
                    )

                    img_elem = (

                        container.select_one(
                            'div[data-product-card-image="true"] img[src^="/_next/image"]'
                        )

                        or

                        container.select_one(
                            'span img[src^="/_next/image"]'
                        )

                        or

                        container.select_one(
                            'div img[src^="/_next/image"]'
                        )

                    )

                    imagem_url = ""

                    if img_elem:

                        imagem_url = img_elem.get(
                            "src",
                            ""
                        )

                        imagem_url = (
                            "https://www.atacadao.com.br"
                            + imagem_url
                        )

                    preco_elem = (
                        container.select_one(
                            "p.text-lg.text-neutral-500.font-bold"
                        )
                        if container
                        else None
                    )

                    preco = (
                        preco_elem.text.strip()
                        if preco_elem
                        else ""
                    )

                    if nome and preco:

                        dados.append({

                            "nome": nome,

                            "preco": preco,

                            "link": link,

                            "imagem_url": imagem_url,

                            "categoria": categoria,

                            "subcategoria": subcategoria,

                            "data_extracao": data_extracao

                        })

                        print(f"✓ {nome}")

                except Exception as e:

                    print(e)

            if page_num % 110 == 0:

                print("♻ Reiniciando Chrome...")

                try:
                    driver.quit()
                except:
                    pass

                driver = criar_driver()

                driver.get(
                    "https://www.atacadao.com.br"
                )
                time.sleep(3)
                configurar_cep(driver)

            page_num += 1

        return dados

    finally:

        try:
            driver.quit()
        except:
            pass

# ===========================
# MAIN
# ===========================

def main():

    with open("configs/urls.txt", "r") as f:
        urls = [
            linha.strip()
            for linha in f
            if linha.strip()
        ]

    print(f"📂 Categorias encontradas: {len(urls)}")

    dados = []

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                processar_categoria,
                url
            ): url
            for url in urls
        }

        for future in as_completed(futures):

            url = futures[future]

            try:

                resultado = future.result()

                dados.extend(resultado)

                print(
                    f"✅ {url} -> "
                    f"{len(resultado)} produtos"
                )

            except Exception as e:

                print(
                    f"❌ Erro em {url}"
                )

                print(e)

    print(
        f"\nTotal produtos: {len(dados)}"
    )

    return dados

# ===========================
# SALVAR PARQUET
# ===========================

def salvar_parquet(dados):
    if not dados:
        print("⚠ Nenhum dado coletado para salvar.")
        return

    hoje = datetime.today().strftime("%Y-%m-%d")
    path = f"data/raw/atacadao/{hoje}"
    
    # Cria a pasta localmente
    os.makedirs(path, exist_ok=True)

    df = pd.DataFrame(dados)
    caminho_arquivo = f"{path}/data.parquet"
    df.to_parquet(caminho_arquivo, index=False)
    
    print(f"\n✅ {len(df)} produtos salvos em {caminho_arquivo}!")


# ===========================
# RUN
# ===========================

if __name__ == "__main__":

    inicio = time.time()

    dados = main()

    salvar_parquet(dados)

    fim = time.time()

    print(
        f"\n⏱ Tempo total: "
        f"{(fim-inicio)/60:.2f} minutos"
    )