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
ACCESS_TOKEN = pegar_token()

def sign_api(path):
    global ACCESS_TOKEN
    ACCESS_TOKEN = pegar_token()
    ts = int(time.time())
    base = f"{PARTNER_ID}{path}{ts}{ACCESS_TOKEN}{SHOP_ID}"
    sign = hmac.new(PARTNER_KEY.encode(), base.encode(), hashlib.sha256).hexdigest()
    return ts, sign

def buscar_todos_os_ids_loja():
    """Busca todos os IDs de produtos da loja (tanto NORMAL quanto UNLIST) usando get_item_list"""
    path = "/api/v2/product/get_item_list"
    
    todos_ids = []
    # Buscamos os principais status para garantir que pegamos tudo
    status_list = ["NORMAL", "UNLIST"]
    
    for item_status in status_list:
        offset = 0
        page_size = 50
        print(f"🔄 Buscando produtos com status {item_status}...", flush=True)
        
        while True:
            ts, sign = sign_api(path)
            url = f"{BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={ts}&sign={sign}&access_token={ACCESS_TOKEN}&shop_id={SHOP_ID}&page_size={page_size}&offset={offset}&item_status={item_status}"
            
            try:
                r = requests.get(url, timeout=20)
                resp = r.json()
                
                if resp.get("error"):
                    print(f"⚠️ Erro na busca da Shopee ({item_status}): {resp.get('message')}", flush=True)
                    break
                    
                response_data = resp.get("response", {})
                item_list = response_data.get("item", [])
                
                if not item_list:
                    break
                    
                for item in item_list:
                    item_id = item.get("item_id")
                    if item_id:
                        todos_ids.append(item_id)
                
                # Paginação da API get_item_list
                has_next_page = response_data.get("has_next_page", False)
                next_offset = response_data.get("next_offset")
                
                if not has_next_page or next_offset is None:
                    break
                    
                offset = next_offset
                time.sleep(0.2)
                
            except Exception as e:
                print(f"⚠️ Erro de conexão ao buscar itens: {e}", flush=True)
                break
                
    # Remove eventuais IDs duplicados
    return list(set(todos_ids))

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

def excluir_todos_produtos():
    print("\n⚠️ AVISO: Iniciando processo de exclusão de TODOS os produtos da loja...", flush=True)
    
    # Pega todos os IDs da loja (Ativos e Inativos)
    todos_ids = buscar_todos_os_ids_loja()
    print(f"📦 Total de produtos encontrados na loja para exclusão: {len(todos_ids)}", flush=True)

    if not todos_ids:
        print("✨ Nenhum produto encontrado na loja.", flush=True)
        return

    excluidos_count = 0

    # Percorre e exclui cada item encontrado
    for item_id in todos_ids:
        print(f"🗑️ Excluindo produto ID {item_id}...", flush=True)
        
        if excluir_item_shopee(item_id):
            print(f"✅ ID {item_id} excluído com sucesso.", flush=True)
            excluidos_count += 1
            
        time.sleep(0.3) # Pequena pausa para evitar rate limit da API

    # Limpa ou atualiza o arquivo CSV local se ele existir
    if os.path.exists(CSV_PATH):
        try:
            df_shopee = pd.read_csv(CSV_PATH)
            df_shopee.columns = df_shopee.columns.str.strip().str.replace('\ufeff', '')
            col_id = next((c for c in ["ID do Produto", "item_id"] if c in df_shopee.columns), None)
            
            if col_id:
                # Remove tudo do CSV ou apaga o arquivo
                df_shopee = df_shopee[~df_shopee[col_id].astype(str).isin(map(str, todos_ids))]
                df_shopee.to_csv(CSV_PATH, index=False)
                print(f"📁 Arquivo CSV local atualizado.", flush=True)
        except Exception as e:
            print(f"⚠️ Erro ao atualizar o CSV local: {e}", flush=True)

    print(f"\n✨ Processo finalizado! Total de produtos excluídos: {excluidos_count} de {len(todos_ids)}.", flush=True)

if __name__ == "__main__":
    confirmacao = input("Tem certeza absoluta que deseja excluir TODOS os produtos da sua loja? (digite 'sim' para confirmar): ")
    if confirmacao.lower() == 'sim':
        excluir_todos_produtos()
    else:
        print("❌ Operação cancelada pelo usuário.")