import os
import pandas as pd
from supabase import create_client
from auth import pegar_token
import time
import hashlib
import hmac
import requests

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
            print(f"RESPOSTA DA SHOPEE: {r.text}")
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

def chamar_api_shopee(path, payload, access_token):
    url_base = "https://partner.shopeemobile.com"
    timestamp, sign = gerar_assinatura(path, access_token)
    # Garante que o access_token está sendo passado corretamente na URL
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

def testar_por_nome(nome_busca):
    print(f"🔍 Buscando dados para: {nome_busca}")
    
    # 1. Pega o token novo e válido logo no início
    token = pegar_token()
    if not token:
        print("❌ Falha ao obter o access_token.")
        return
    print("🔑 Token obtido com sucesso!")

    # 2. Busca na Silver
    response = supabase.table("silver_products").select("*").execute()
    df_silver = pd.DataFrame(response.data)
    
    produto_silver = df_silver[df_silver['nome_produto'].str.contains(nome_busca, case=False, na=False)]
    if produto_silver.empty:
        print("❌ Produto não encontrado na Silver (Supabase).")
        return

    dados = produto_silver.iloc[0]
    print(f"✅ Encontrado na Silver: {dados['nome_produto']} | Preço: {dados['preco_venda']}")

    # 3. Busca o ID no CSV
    df_ids = pd.read_csv(CSV_PATH)
    match_csv = df_ids[df_ids['Nome do Produto'].str.contains(nome_busca, case=False, na=False)]
    
    if match_csv.empty:
        print("❌ Produto não encontrado no arquivo CSV local da Shopee.")
        return
        
    item_id = int(match_csv.iloc[0]['ID do Produto'])
    print(f"🎯 ID encontrado na Shopee: {item_id}")

    # 4. Executa a atualização usando o token válido
    print("🚀 Enviando atualização para a Shopee...")
    
    set_status_item(item_id, False, token)
    atualizar_preco(item_id, dados['preco_venda'], token)
    
    # Tratamento seguro para pegar a imagem independentemente de maiúsculas/minúsculas
    coluna_imagem = next((col for col in dados.index if col.lower() in ['imagem', 'image', 'url_imagem', 'img']), None)
    valor_imagem = dados[coluna_imagem] if coluna_imagem else ""

    atualizar_item_completo(
        item_id, 
        dados['nome_produto'], 
        dados['descricao'], 
        valor_imagem, 
        dados['peso'], 
        token
    )
    print("🏁 Teste concluído com sucesso!")

if __name__ == "__main__":
    testar_por_nome("Sabonete Lux Orquídea Negra 6x85g")