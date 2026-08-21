import os
import pandas as pd
from supabase import create_client
from auth import pegar_token
import time
import hashlib
import hmac
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configurações
PARTNER_ID = 2014045
PARTNER_KEY = "shpk55617356626c5347767977714e586e4c4f557075544e546e42784a757967"
SHOP_ID = 1588032704
CSV_PATH = "integration/produtos_shopee.csv"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def request_com_retry(url, payload, tentativas=3):
    for i in range(tentativas):
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                res_json = r.json()
                if res_json.get("error"):
                    print(f"⚠️ Erro retornado pela API da Shopee: {res_json}")
                return r
            time.sleep(1)
        except Exception as e:
            print(f"⚠️ Erro tentativa {i+1}: {e}")
            time.sleep(2)
    return None

def gerar_assinatura(path, access_token):
    timestamp = int(time.time())
    base_string = f"{PARTNER_ID}{path}{timestamp}{access_token}{SHOP_ID}"
    sign = hmac.new(
        PARTNER_KEY.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return timestamp, sign

def chamar_api_shopee(path, payload):
    access_token = pegar_token()
    url_base = "https://partner.shopeemobile.com"
    timestamp, sign = gerar_assinatura(path, access_token)
    url = f"{url_base}{path}?partner_id={PARTNER_ID}&timestamp={timestamp}&sign={sign}&access_token={access_token}&shop_id={SHOP_ID}"
    return request_com_retry(url, payload)

def atualizar_preco(item_id, preco):
    path = "/api/v2/product/update_price"
    payload = {"item_id": int(item_id), "price_list": [{"model_id": 0, "original_price": float(preco)}]}
    r = chamar_api_shopee(path, payload)
    if r: print(f"💰 Preço atualizado ({item_id}) → {preco}")

def atualizar_item_completo(item_id, nome, desc, img, peso):
    path = "/api/v2/product/update_item"
    payload = {
        "item_id": int(item_id),
        "item_name": str(nome)[:120],
        "description": str(desc)[:3000],
        "weight": float(peso),
        "logistic_info": [
            {"logistic_id": 91003, "enabled": True},
            {"logistic_id": 90024, "enabled": True},
            {"logistic_id": 91006, "enabled": True}
        ]
    }
    if img: payload["images"] = {"image_url_list": [img]}
    r = chamar_api_shopee(path, payload)
    if r: print(f"🧠 Item atualizado ({item_id})")

def set_status_item(item_id, unlist):
    path = "/api/v2/product/unlist_item"
    payload = {"item_list": [{"item_id": int(item_id), "unlist": unlist}]}
    chamar_api_shopee(path, payload)

def processar_produto(row):
    try:
        item_id = int(row["ID do Produto"])
        nome = row["Nome do Produto"]
        nome_novo = row.get("nome_produto", nome)
        preco = row["preco_venda"]
        descricao = row.get("descricao", "")
        
        # Trata coluna de imagem dinamicamente
        coluna_imagem = next((col for col in row.index if col.lower() in ['imagem', 'image', 'url_imagem', 'img']), None)
        imagem = row[coluna_imagem] if coluna_imagem and pd.notna(row[coluna_imagem]) else ""
        
        peso = row.get("peso", 0.1)
        if pd.isna(peso) or peso <= 0:
            peso = 0.1

        print(f"🔎 Processando: {nome} (ID: {item_id})")

        if pd.notna(preco):
            set_status_item(item_id, False) # Ativa o produto
            atualizar_preco(item_id, preco)
            atualizar_item_completo(item_id, nome_novo, descricao, imagem, peso)
        else:
            set_status_item(item_id, True) # Inativa se não tiver preço
            print(f"❌ Produto inativado por falta de preço: {item_id}")
            
    except Exception as e:
        print(f"⚠️ Erro ao processar o produto {row.get('Nome do Produto', 'Desconhecido')}: {e}")

def sincronizar():
    print("\n📦 Lendo produtos_shopee.csv…")
    df_ids = pd.read_csv(CSV_PATH)
    df_ids.columns = df_ids.columns.str.strip().str.replace('\ufeff', '')

    print(f"➡ {len(df_ids)} produtos carregados do CSV.")

    print("📊 Carregando dados do Supabase (silver_products)...")
    response = supabase.table("silver_products").select("*").execute()
    df_silver = pd.DataFrame(response.data)

    print(f"✅ {len(df_silver)} registros carregados do Supabase.")

    # Realiza o merge entre o CSV da Shopee e os dados tratados do Supabase
    df_final = df_ids.merge(
        df_silver,
        left_on="Nome do Produto",
        right_on="nome_produto",
        how="inner"
    )

    print(f"🔗 Merge realizado. Total de produtos pareados para atualização: {len(df_final)}")

    # Executa a atualização em paralelo usando ThreadPoolExecutor (max 5 threads para respeitar limites da API)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(processar_produto, row) for _, row in df_final.iterrows()]
        for future in as_completed(futures):
            future.result()

    print("🏁 Sincronização em lote concluída com sucesso!")

if __name__ == "__main__":
    sincronizar()