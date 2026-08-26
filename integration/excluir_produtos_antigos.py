import os
import time
import hmac
import hashlib
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

from auth import pegar_token

# ==================================================
# CONFIG
# ==================================================
PARTNER_ID = 2014045
PARTNER_KEY = "shpk55617356626c5347767977714e586e4c4f557075544e546e42784a757967"
SHOP_ID = 1588032704
BASE_URL = "https://partner.shopeemobile.com"

CSV_PATH = "integration/produtos_shopee.csv"
ACCESS_TOKEN = pegar_token()

def sign_api(path):
    global ACCESS_TOKEN
    ACCESS_TOKEN = pegar_token()
    ts = int(time.time())
    base = f"{PARTNER_ID}{path}{ts}{ACCESS_TOKEN}{SHOP_ID}"
    sign = hmac.new(PARTNER_KEY.encode(), base.encode(), hashlib.sha256).hexdigest()
    return ts, sign

def consultar_detalhes_item(item_id):
    """Consulta o status e informações do produto na Shopee"""
    path = "/api/v2/product/get_item_base_info"
    ts, sign = sign_api(path)
    url = f"{BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={ts}&sign={sign}&access_token={ACCESS_TOKEN}&shop_id={SHOP_ID}&item_id_list={item_id}"

    try:
        r = requests.get(url, timeout=30)
        resp = r.json()
        if resp.get("error"):
            return None
        item_list = resp.get("response", {}).get("item_list", [])
        if item_list:
            return item_list[0]
    except Exception as e:
        print(f"⚠️ Erro ao consultar ID {item_id}: {e}")
    return None

def excluir_item_shopee(item_id):
    """Exclui permanentemente o anúncio da Shopee"""
    path = "/api/v2/product/delete_item"
    ts, sign = sign_api(path)
    url = f"{BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={ts}&sign={sign}&access_token={ACCESS_TOKEN}&shop_id={SHOP_ID}"

    payload = {"item_id": int(item_id)}

    try:
        r = requests.post(url, json=payload, timeout=30)
        resp = r.json()
        if resp.get("error"):
            print(f"❌ Erro ao excluir ID {item_id}: {resp.get('message')}")
            return False
        return True
    except Exception as e:
        print(f"❌ Erro de requisição ao excluir ID {item_id}: {e}")
        return False

def limpar_produtos_inativos_antigos():
    print("\n🧹 Verificando produtos inativos há mais de 1 mês para exclusão...")

    if not os.path.exists(CSV_PATH):
        print("⚠️ Arquivo de controle 'produtos_shopee.csv' não encontrado.")
        return

    df_shopee = pd.read_csv(CSV_PATH)
    df_shopee.columns = df_shopee.columns.str.strip().str.replace('\ufeff', '')

    col_id = next((c for c in ["ID do Produto", "item_id"] if c in df_shopee.columns), None)
    col_nome = next((c for c in ["Nome do Produto", "Nome Original"] if c in df_shopee.columns), None)

    if not col_id:
        print("❌ Coluna de ID não encontrada no CSV.")
        return

    agora = datetime.now(timezone.utc)
    limite_um_mes = agora - timedelta(days=30)
    
    ids_para_remover = []

    for index, row in df_shopee.iterrows():
        item_id = row[col_id]
        nome = row.get(col_nome, "Produto sem nome")

        # Consulta o estado atual do produto na Shopee
        info = consultar_detalhes_item(item_id)
        if not info:
            time.sleep(0.5)
            continue

        item_status = info.get("item_status") # Ex: "NORMAL", "UNLIST", "BANNED", etc.
        update_time = info.get("update_time") # Timestamp de quando foi modificado por último

        # Se o produto estiver inativo (UNLIST)
        if item_status == "UNLIST" and update_time:
            data_atualizacao = datetime.fromtimestamp(update_time, timezone.utc)
            
            # Se a última alteração para inativo ocorreu há mais de 30 dias
            if data_atualizacao < limite_um_mes:
                print(f"🗑️ O produto '{nome}' (ID: {item_id}) está inativo desde {data_atualizacao.strftime('%Y-%m-%d')}. Excluindo...")
                
                if excluir_item_shopee(item_id):
                    print(f"✅ Excluído com sucesso da Shopee.")
                    ids_para_remover.append(item_id)

        time.sleep(0.5) # Respeitar limite de requisições

    # Remove os itens excluídos do CSV de controle local
    if ids_para_remover:
        df_shopee = df_shopee[~df_shopee[col_id].isin(ids_para_remover)]
        df_shopee.to_csv(CSV_PATH, index=False)
        print(f"✨ {len(ids_para_remover)} produtos antigos foram removidos do CSV de controle.")
    else:
        print("✨ Nenhum produto atingiu o limite de 1 mês inativo.")

if __name__ == "__main__":
    limpar_produtos_inativos_antigos()