import os
import pandas as pd
from supabase import create_client
from auth import pegar_token
import time
import hashlib
import hmac
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================
# CONFIG
# ============================
PARTNER_ID = 2014045
PARTNER_KEY = "shpk55617356626c5347767977714e586e4c4f557075544e546e42784a757967"
SHOP_ID = 1588032704
CSV_PATH = "integration/produtos_shopee.csv"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================
# REQUEST COM RETRY
# ============================
def request_com_retry(url, payload, tentativas=3):
    for i in range(tentativas):
        try:
            r = requests.post(url, json=payload, timeout=30)
            return r
        except Exception as e:
            print(f"⚠️ erro tentativa {i+1}: {e}")
            time.sleep(1)

    print("❌ falhou após várias tentativas")
    return None

# ============================
# CARREGAR DADOS DO SUPABASE (PAGINADO)
# ============================
def carregar_dados_atuais():
    print("📊 Carregando dados do Supabase (silver_products)...")
    todos_registros = []
    chunk_size = 1000
    offset = 0
    while True:
        response = supabase.table("silver_products").select("*").range(offset, offset + chunk_size - 1).execute()
        if not response.data: 
            break
        todos_registros.extend(response.data)
        offset += chunk_size
    
    df = pd.DataFrame(todos_registros)
    print(f"✅ {len(df)} registros carregados do Supabase")
    return df

# ============================
# PREPARAR DADOS
# ============================
def preparar_dados(df_silver):
    print("🧠 Aplicando regras de negócio...")

    df = df_silver.copy()

    df["refrigerado"] = df.get("refrigerado", False)
    df["descricao"] = df.get("descricao", "")
    
    coluna_img_silver = next((col for col in df.columns if col.lower() in ['imagem', 'image', 'url_imagem', 'img']), "imagem")
    df["imagem_url"] = df.get(coluna_img_silver, "")
    df["peso"] = df.get("peso", 0.1)

    df["vendavel"] = df["refrigerado"] == False

    df_update = df[df["vendavel"]].copy()

    colunas_disponiveis = [c for c in ["nome_original", "nome_produto", "preco_venda", "descricao", coluna_img_silver, "peso"] if c in df_update.columns]
    df_update = df_update[colunas_disponiveis]

    rename_dict = {
        "nome_original": "Nome Original",
        "nome_produto": "Nome do Produto Novo",
        "preco_venda": "Preco",
        "descricao": "Descricao",
        coluna_img_silver: "Imagem",
        "peso": "Peso"
    }
    df_update.rename(columns=rename_dict, inplace=True)

    print(f"🛒 Produtos vendáveis: {len(df_update)}")
    return df_update

# ============================
# ASSINATURA
# ============================
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
# ATUALIZAR PREÇO (COM RETORNO EXPLÍCITO)
# ============================
# Mantenha o token fora das funções de atualização para não sobrecarregar a API
# Obtenha uma vez na sincronização e passe o valor.

def atualizar_preco(item_id, preco, access_token):
    path = "/api/v2/product/update_price"
    url_base = "https://partner.shopeemobile.com"
    timestamp, sign = gerar_assinatura(path, access_token)
    
    url = f"{url_base}{path}?partner_id={PARTNER_ID}&timestamp={timestamp}&sign={sign}&access_token={access_token}&shop_id={SHOP_ID}"

    payload = {
        "item_id": int(item_id),
        "price_list": [{"model_id": 0, "original_price": float(preco)}]
    }

    try:
        # Aumente o timeout para ambientes de nuvem (o GitHub pode ser mais lento que local)
        r = requests.post(url, json=payload, timeout=60)
        # Se a API responder algo, printamos
        print(f"💰 {item_id} -> Status: {r.status_code} | Resposta: {r.text}")
    except Exception as e:
        print(f"❌ Erro na requisição para {item_id}: {str(e)}")
# ============================
# ATUALIZAR ITEM COMPLETO
# ============================
def atualizar_item_completo(item_id, nome_produto, descricao, imagem, peso, access_token):
    access_token = pegar_token()
    path = "/api/v2/product/update_item"
    url_base = "https://partner.shopeemobile.com"

    timestamp, sign = gerar_assinatura(path, access_token)

    url = (
        f"{url_base}{path}"
        f"?partner_id={PARTNER_ID}"
        f"&timestamp={timestamp}"
        f"&sign={sign}"
        f"&access_token={access_token}"
        f"&shop_id={SHOP_ID}"
    )

    payload = {
        "item_id": int(item_id),
        "item_name": str(nome_produto)[:120],
        "description": str(descricao)[:3000],
        "weight": float(peso) if pd.notna(peso) and peso > 0 else 0.1,
        "logistic_info": [
            {"logistic_id": 91003, "enabled": True},
            {"logistic_id": 90024, "enabled": True},
            {"logistic_id": 91006, "enabled": True}
        ]
    }

    if imagem and pd.notna(imagem):
        payload["images"] = {
            "image_url_list": [str(imagem)]
        }

    r = request_com_retry(url, payload)
    if r:
        print(f"🧠 [API RETORNO] Item Completo ID {item_id} | Status: {r.status_code} | Resposta: {r.text}")

# ============================
# INATIVAR
# ============================
def inativar_produto(item_id, access_token):
    access_token = pegar_token()
    path = "/api/v2/product/unlist_item"
    url_base = "https://partner.shopeemobile.com"

    timestamp, sign = gerar_assinatura(path, access_token)

    url = (
        f"{url_base}{path}"
        f"?partner_id={PARTNER_ID}"
        f"&timestamp={timestamp}"
        f"&sign={sign}"
        f"&access_token={access_token}"
        f"&shop_id={SHOP_ID}"
    )

    payload = {
        "item_list": [{"item_id": int(item_id), "unlist": True}]
    }

    r = request_com_retry(url, payload)
    if r:
        print(f"❌ [API RETORNO] Inativar ID {item_id} | Status: {r.status_code} | Resposta: {r.text}")

# ============================
# ATIVAR
# ============================
def ativar_produto(item_id, access_token):
    access_token = pegar_token()
    path = "/api/v2/product/unlist_item"
    url_base = "https://partner.shopeemobile.com"

    timestamp, sign = gerar_assinatura(path, access_token)

    url = (
        f"{url_base}{path}"
        f"?partner_id={PARTNER_ID}"
        f"&timestamp={timestamp}"
        f"&sign={sign}"
        f"&access_token={access_token}"
        f"&shop_id={SHOP_ID}"
    )

    payload = {
        "item_list": [
            {
                "item_id": int(item_id),
                "unlist": False
            }
        ]
    }

    r = request_com_retry(url, payload)
    if r:
        print(f"✅ [API RETORNO] Ativar ID {item_id} | Status: {r.status_code} | Resposta: {r.text}")

# ============================
# PROCESSAR PRODUTO INDIVIDUAL
# ============================
def processar_produto(row, access_token):
    try:
        id_col = next((c for c in ['ID do Produto', 'id_produto', 'item_id', 'ID'] if c in row and pd.notna(row[c])), None)
        if not id_col:
            print(f"⚠️ Erro: Coluna de ID não encontrada na linha: {row}")
            return
            
        item_id = int(row[id_col])
        nome = row.get("Nome do Produto", "Desconhecido")
        nome_novo = row.get("Nome do Produto Novo", nome)
        preco = row.get("Preco")
        descricao = row.get("Descricao", "")
        imagem = row.get("Imagem", "")
        peso = row.get("Peso", 0.1)

        print(f"\n🔎 Processando: {nome} (ID: {item_id}) | Preço: {preco}")

        if pd.notna(preco):
            ativar_produto(item_id, access_token)
            atualizar_preco(item_id, preco, access_token)
            atualizar_item_completo(item_id, nome_novo, descricao, imagem, peso, access_token)
        else:
            print(f"⚠️ Produto {item_id} sem preço mapeado.")
            inativar_produto(item_id, access_token)
            
    except Exception as e:
        print(f"❌ Erro crítico ao processar linha: {e}")

# ============================
# SINCRONIZAÇÃO
# ============================
def sincronizar():
    print("\n📦 Lendo produtos_shopee.csv…")
    if not os.path.exists(CSV_PATH):
        print(f"❌ Erro crítico: Arquivo {CSV_PATH} não encontrado!")
        return
        
    df_ids = pd.read_csv(CSV_PATH, encoding="utf-8-sig")

    df_ids.columns = (
        df_ids.columns
        .str.strip()
        .str.replace('\ufeff', '')
    )

    print(f"➡ {len(df_ids)} produtos carregados do CSV.")

    df_silver = carregar_dados_atuais()
    if df_silver.empty:
        print("❌ A tabela 'silver_products' retornou vazia do Supabase!")
        return

    df_update = preparar_dados(df_silver)

    if "Nome do Produto" in df_ids.columns and "Nome Original" in df_update.columns:
        df_ids["_match_key"] = df_ids["Nome do Produto"].astype(str).str.strip().str.lower()
        df_update["_match_key"] = df_update["Nome Original"].astype(str).str.strip().str.lower()
        
        df_final = pd.merge(
            df_ids,
            df_update.drop(columns=["Nome Original"]),
            left_on="_match_key",
            right_on="_match_key",
            how="left"
        ).drop(columns=["_match_key"])
    else:
        df_final = df_ids.merge(df_update, left_on="Nome do Produto", right_on="Nome Original", how="left")

    total_encontrados = df_final['Preco'].notna().sum()
    total_sem_preco = len(df_final) - total_encontrados
    print(f"\n🔗 ----------------------------------------")
    print(f"🔗 Total de produtos no CSV: {len(df_final)}")
    print(f"🔗 Produtos encontrados na base (com preço): {total_encontrados}")
    print(f"🔗 Produtos sem preço (serão inativados): {total_sem_preco}")
    print(f"🔗 ----------------------------------------\n")

    access_token = pegar_token()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(processar_produto, row, access_token) for _, row in df_final.iterrows()]
        for future in as_completed(futures):
            future.result()

    print("🏁 Sincronização concluída com sucesso!")

def run():
    sincronizar()

if __name__ == "__main__":
    run()