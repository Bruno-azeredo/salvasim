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

def normalizar_texto(texto):
    if pd.isna(texto): return ""
    return str(texto).strip().lower()

def carregar_todos_do_supabase():
    todos_registros = []
    chunk_size = 1000
    offset = 0
    while True:
        response = supabase.table("silver_products").select("*").range(offset, offset + chunk_size - 1).execute()
        if not response.data: break
        todos_registros.extend(response.data)
        offset += chunk_size
    return pd.DataFrame(todos_registros)

def processar_produto(row):
    try:
        item_id = int(row["ID do Produto"])
        nome_csv = row["Nome do Produto"]
        # Usa o nome oficial vindo do Supabase para atualizar a Shopee
        nome_oficial = row.get("nome_produto", nome_csv)
        preco = row.get("preco_venda")
        descricao = row.get("descricao", "")
        
        coluna_imagem = next((col for col in row.index if col.lower() in ['imagem', 'image', 'url_imagem', 'img']), None)
        imagem = row[coluna_imagem] if coluna_imagem and pd.notna(row[coluna_imagem]) else ""
        
        peso = row.get("peso", 0.1)
        peso = float(peso) if pd.notna(peso) and peso > 0 else 0.1

        if pd.notna(preco):
            print(f"🔎 Atualizando: {nome_oficial} (ID: {item_id})")
            set_status_item(item_id, False)
            atualizar_preco(item_id, preco)
            atualizar_item_completo(item_id, nome_oficial, descricao, imagem, peso)
        else:
            print(f"❌ Inativando (sem preço): {item_id}")
            set_status_item(item_id, True)
    except Exception as e:
        print(f"⚠️ Erro ao processar produto {item_id}: {e}")

def sincronizar():
    print("\n📦 Lendo produtos_shopee.csv…")
    df_ids = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    df_ids.columns = df_ids.columns.str.strip()
    
    # Normalização para garantir o match
    df_ids['chave'] = df_ids['Nome do Produto'].apply(normalizar_texto)

    print("📊 Carregando dados completos do Supabase (paginado)...")
    df_silver = carregar_todos_do_supabase()
    df_silver['chave'] = df_silver['nome_original'].apply(normalizar_texto) # Ajuste 'nome_original' para a coluna correta

    df_final = df_ids.merge(df_silver, on="chave", how="left")

    print(f"🔗 Merge realizado: {len(df_final)} produtos no escopo.")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(processar_produto, row) for _, row in df_final.iterrows()]
        for future in as_completed(futures):
            future.result()

    print("🏁 Sincronização concluída!")

if __name__ == "__main__":
    sincronizar()