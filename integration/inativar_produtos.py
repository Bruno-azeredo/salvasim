import os
import time
import hmac
import hashlib
import requests
import pandas as pd

from auth import pegar_token

# ==================================================
# CONFIG
# ==================================================
PARTNER_ID = 2014045
PARTNER_KEY = "shpk55617356626c5347767977714e586e4c4f557075544e546e42784a757967"
SHOP_ID = 1588032704
BASE_URL = "https://partner.shopeemobile.com"

CSV_PATH = "integration/produtos_shopee.csv"
TXT_PATH = "integration/produtos_ausentes.txt"

ACCESS_TOKEN = pegar_token()

def sign_api(path):
    global ACCESS_TOKEN
    ACCESS_TOKEN = pegar_token()
    ts = int(time.time())
    base = f"{PARTNER_ID}{path}{ts}{ACCESS_TOKEN}{SHOP_ID}"
    sign = hmac.new(PARTNER_KEY.encode(), base.encode(), hashlib.sha256).hexdigest()
    return ts, sign

def inativar_item_shopee(item_id):
    path = "/api/v2/product/update_item"
    ts, sign = sign_api(path)
    url = f"{BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={ts}&sign={sign}&access_token={ACCESS_TOKEN}&shop_id={SHOP_ID}"

    # Payload para alterar o status do produto para UNLIST (Inativo/Oculto)
    payload = {
        "item_id": int(item_id),
        "item_status": "UNLIST"
    }

    try:
        r = requests.post(url, json=payload, timeout=30)
        resp = r.json()
        if resp.get("error"):
            print(f"❌ Erro ao inativar ID {item_id}: {resp.get('message')}")
            return False
        return True
    except Exception as e:
        print(f"❌ Erro de requisição ao inativar ID {item_id}: {e}")
        return False

def processar_ausentes():
    print("\n🔍 Verificando arquivo de produtos ausentes...")
    
    if not os.path.exists(TXT_PATH):
        print("✨ Arquivo 'produtos_ausentes.txt' não encontrado. Nenhuma ação necessária.")
        return

    if not os.path.exists(CSV_PATH):
        print("⚠️ Arquivo de controle 'produtos_shopee.csv' não encontrado.")
        return

    # Lê os produtos que você colocou no txt
    with open(TXT_PATH, "r", encoding="utf-8") as f:
        ausentes = [line.strip().lower() for line in f if line.strip()]

    if not ausentes:
        print("✨ O arquivo 'produtos_ausentes.txt' está vazio.")
        return

    df_shopee = pd.read_csv(CSV_PATH)
    df_shopee.columns = df_shopee.columns.str.strip().str.replace('\ufeff', '')

    # Identifica as colunas corretas do CSV
    col_id = next((c for c in ["ID do Produto", "item_id"] if c in df_shopee.columns), None)
    col_nome = next((c for c in ["Nome do Produto", "Nome Original"] if c in df_shopee.columns), None)

    if not col_id or not col_nome:
        print("❌ Erro: Colunas de ID ou Nome não encontradas no CSV de controle.")
        return

    sucessos = 0
    for nome_procurado in ausentes:
        # Busca aproximada ou exata no CSV
        match = df_shopee[df_shopee[col_nome].astype(str).str.lower().str.strip() == nome_procurado]
        
        if match.empty:
            print(f"⚠️ Produto não encontrado no CSV de controle: '{nome_procurado}'")
            continue

        item_id = match.iloc[0][col_id]
        print(f"🛑 Inativando na Shopee -> Produto: {nome_procurado} (ID: {item_id})")

        if inativar_item_shopee(item_id):
            print(f"✅ Sucesso ao inativar: {nome_procurado}")
            sucessos += 1
        
        time.sleep(1)

    # Opcional: Limpar o arquivo txt após processar com sucesso para não reprocessar amanhã
    if sucessos > 0:
        with open(TXT_PATH, "w", encoding="utf-8") as f:
            f.write("") # Limpa o conteúdo do arquivo
        print(f"🧹 Arquivo '{TXT_PATH}' limpo após a sincronização.")

if __name__ == "__main__":
    processar_ausentes()