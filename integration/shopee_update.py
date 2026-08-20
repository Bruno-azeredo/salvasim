import os
import time
import hashlib
import hmac
import requests
import pandas as pd
from supabase import create_client
from auth import pegar_token
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================
# CONFIGURAÇÕES
# ============================
PARTNER_ID = 2014045
PARTNER_KEY = "shpk55617356626c5347767977714e586e4c4f557075544e546e42784a757967"
SHOP_ID = 1588032704
CSV_PATH = "integration/produtos_shopee.csv"

# Conexão com o Supabase usando as variáveis de ambiente
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================
# UTILS
# ============================
def request_com_retry(url, payload, tentativas=3):
    for i in range(tentativas):
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                return r
            time.sleep(1) # Espera um pouco se der erro
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

# ============================
# FUNÇÕES DE API
# ============================
def chamar_api_shopee(path, payload, access_token):
    url_base = "https://partner.shopeemobile.com"
    timestamp, sign = gerar_assinatura(path, access_token)
    url = f"{url_base}{path}?partner_id={PARTNER_ID}&timestamp={timestamp}&sign={sign}&access_token={access_token}&shop_id={SHOP_ID}"
    return request_com_retry(url, payload)

def atualizar_preco(item_id, preco, access_token):
    path = "/api/v2/product/update_price"
    payload = {"item_id": int(item_id), "price_list": [{"model_id": 0, "original_price": float(preco)}]}
    r = chamar_api_shopee(path, payload, access_token)
    if r: print(f"💰 Preço atualizado ({item_id}) → {preco}")

def atualizar_item_completo(item_id, nome, desc, img, peso, access_token):
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
    r = chamar_api_shopee(path, payload, access_token)
    if r: print(f"🧠 Item atualizado ({item_id})")

def set_status_item(item_id, unlist, access_token):
    path = "/api/v2/product/unlist_item"
    payload = {"item_list": [{"item_id": int(item_id), "unlist": unlist}]}
    chamar_api_shopee(path, payload, access_token)

# ============================
# LÓGICA PRINCIPAL
# ============================
def processar_produto(row, access_token):
    item_id = int(row["ID do Produto"])
    preco = row["Preco"]
    
    if pd.notna(preco):
        set_status_item(item_id, False, access_token)
        atualizar_preco(item_id, preco, access_token)
        atualizar_item_completo(
            item_id, row["Nome do Produto Novo"], row["Descricao"], 
            row["Imagem"], row["Peso"], access_token
        )
    else:
        set_status_item(item_id, True, access_token)
        print(f"❌ Inativado: {item_id}")

def run():
    print("🚀 Iniciando sincronização...")
    
    # 1. Carregar Dados direto do Supabase (Tabela silver_products)
    try:
        response = supabase.table("silver_products").select("*").execute()
        df_silver = pd.DataFrame(response.data)
        if df_silver.empty:
            print("⚠️ A tabela silver_products está vazia no Supabase.")
            return
    except Exception as e:
        print(f"❌ Erro ao buscar dados do Supabase: {e}")
        raise e

    # Carregar IDs do CSV local
    df_ids = pd.read_csv(CSV_PATH)
    df_ids.columns = df_ids.columns.str.strip().str.replace('\ufeff', '')

    # 2. Mapeamento exato com base nas colunas reais da sua imagem
    mapa_renomeacao = {
        "nome_original": "Nome Original",
        "nome_produto": "Nome do Produto Novo",
        "preco_venda": "Preco",
        "descricao": "Descricao",
        "Imagem": "Imagem",
        "peso": "Peso"
    }
    
    df_silver = df_silver.rename(columns=mapa_renomeacao)

    # Verifica se a coluna "Nome Original" existe antes de prosseguir
    if "Nome Original" not in df_silver.columns:
        print(f"❌ A coluna 'Nome Original' não foi encontrada. Colunas disponíveis: {list(df_silver.columns)}")
        return

    # 3. Merge
    df_final = df_ids.merge(df_silver, left_on="Nome do Produto", right_on="Nome Original", how="left")
    
    # ADICIONE ESTE PRINT PARA VERIFICAR OS DADOS
    print(df_final[["Nome do Produto", "Preco"]].head(10), flush=True)
    print(f"Total de linhas no df_final: {len(df_final)}", flush=True)
    print(f"Quantos preços válidos encontrados: {df_final['Preco'].notna().sum()}", flush=True)
    # 4. Execução Concorrente
    token = pegar_token()
    with ThreadPoolExecutor(max_workers=3) as executor: # Seguro para rate limit
        futures = [executor.submit(processar_produto, row, token) for _, row in df_final.iterrows()]
        for future in as_completed(futures):
            future.result()

    print("🏁 Sincronização concluída!")

if __name__ == "__main__":
    run()