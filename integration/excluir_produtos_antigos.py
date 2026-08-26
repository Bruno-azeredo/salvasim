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

def buscar_todos_itens_shopee(item_status="UNLIST"):
    """Busca todos os itens inativos (UNLIST) diretamente da Shopee com paginação completa"""
    path = "/api/v2/product/get_item_list"
    ts, sign = sign_api(path)
    
    url = f"{BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={ts}&sign={sign}&access_token={ACCESS_TOKEN}&shop_id={SHOP_ID}&page_size=50&item_status={item_status}"

    itens_inativos = []
    offset = 0
    
    print("🔄 Baixando lista completa de produtos inativos da Shopee...", flush=True)
    
    while True:
        p_url = f"{url}&offset={offset}"
        try:
            r = requests.get(p_url, timeout=20)
            resp = r.json()
            if resp.get("error"):
                print(f"⚠️ Erro ao buscar lista da Shopee: {resp.get('message')}", flush=True)
                break
                
            response_data = resp.get("response", {})
            item_list = response_data.get("item", [])
            
            if not item_list:
                break
                
            for item in item_list:
                itens_inativos.append(item.get("item_id"))
                
            # Verifica se há mais páginas
            has_next = response_data.get("has_next", False)
            if not has_next:
                break
                
            # Atualiza o offset com base no retorno ou somando 50
            next_offset = response_data.get("next_offset")
            if next_offset is not None:
                offset = next_offset
            else:
                offset += 50
                
            time.sleep(0.2)
        except Exception as e:
            print(f"⚠️ Erro de conexão ao paginar itens: {e}", flush=True)
            break
            
        # Proteção estendida para suportar mais de 2000 itens se necessário
        if offset > 5000: 
            break
            
    return itens_inativos

def consultar_detalhes_lote(item_ids):
    """Consulta detalhes de até 50 itens de uma única vez"""
    path = "/api/v2/product/get_item_base_info"
    ts, sign = sign_api(path)
    
    # Formata a lista de IDs para a query string
    ids_str = ",".join(map(str, item_ids))
    url = f"{BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={ts}&sign={sign}&access_token={ACCESS_TOKEN}&shop_id={SHOP_ID}&item_id_list={ids_str}"

    try:
        r = requests.get(url, timeout=20)
        resp = r.json()
        if resp.get("error"):
            return []
        return resp.get("response", {}).get("item_list", [])
    except Exception as e:
        print(f"⚠️ Erro ao consultar lote: {e}", flush=True)
        return []

def excluir_item_shopee(item_id):
    """Exclui permanentemente o anúncio da Shopee"""
    path = "/api/v2/product/delete_item"
    ts, sign = sign_api(path)
    url = f"{BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={ts}&sign={sign}&access_token={ACCESS_TOKEN}&shop_id={SHOP_ID}"

    payload = {"item_id": int(item_id)}

    try:
        r = requests.post(url, json=payload, timeout=15)
        resp = r.json()
        if resp.get("error"):
            print(f"❌ Erro ao excluir ID {item_id}: {resp.get('message')}", flush=True)
            return False
        return True
    except Exception as e:
        print(f"❌ Erro de requisição ao excluir ID {item_id}: {e}", flush=True)
        return False

def limpar_produtos_inativos_antigos():
    print("\n🧹 Buscando produtos inativos diretamente na Shopee...", flush=True)

    if not os.path.exists(CSV_PATH):
        print("⚠️ Arquivo de controle 'produtos_shopee.csv' não encontrado.", flush=True)
        return

    df_shopee = pd.read_csv(CSV_PATH)
    df_shopee.columns = df_shopee.columns.str.strip().str.replace('\ufeff', '')

    col_id = next((c for c in ["ID do Produto", "item_id"] if c in df_shopee.columns), None)
    col_nome = next((c for c in ["Nome do Produto", "Nome Original"] if c in df_shopee.columns), None)

    if not col_id:
        print("❌ Coluna de ID não encontrada no CSV.", flush=True)
        return

    # Pega todos os IDs que estão inativos (UNLIST) lá na Shopee de forma ultra rápida
    ids_inativos = buscar_todos_itens_shopee("UNLIST")
    print(f"📦 Total de produtos inativos encontrados na Shopee: {len(ids_inativos)}", flush=True)

    if not ids_inativos:
        print("✨ Nenhum produto inativo na Shopee.", flush=True)
        return

    agora = datetime.now(timezone.utc)
    limite_um_mes = agora - timedelta(days=30)
    ids_para_remover = []

    # Divide os IDs em blocos de 50 (limite da API da Shopee para lotes)
    for i in range(0, len(ids_inativos), 50):
        lote = ids_inativos[i:i+50]
        detalhes = consultar_detalhes_lote(lote)

        for info in detalhes:
            item_id = info.get("item_id")
            update_time = info.get("update_time")

            if update_time:
                data_atualizacao = datetime.fromtimestamp(update_time, timezone.utc)
                
                # Se está inativo há mais de 30 dias
                if data_atualizacao < limite_um_mes:
                    # Acha o nome no CSV para logar bonito
                    match = df_shopee[df_shopee[col_id].astype(str) == str(item_id)]
                    nome = match.iloc[0][col_nome] if not match.empty else f"ID {item_id}"
                    
                    print(f"🗑️ O produto '{nome}' está inativo desde {data_atualizacao.strftime('%Y-%m-%d')}. Excluindo...", flush=True)
                    
                    if excluir_item_shopee(item_id):
                        print(f"✅ Excluído com sucesso.", flush=True)
                        ids_para_remover.append(item_id)
        
        time.sleep(0.5)

    # Remove do CSV de controle local
    if ids_para_remover:
        df_shopee = df_shopee[~df_shopee[col_id].astype(str).isin(map(str, ids_para_remover))]
        df_shopee.to_csv(CSV_PATH, index=False)
        print(f"✨ {len(ids_para_remover)} produtos antigos foram excluídos e removidos do CSV.", flush=True)
    else:
        print("✨ Nenhum produto inativo atingiu o limite de 1 mês.", flush=True)

if __name__ == "__main__":
    limpar_produtos_inativos_antigos()