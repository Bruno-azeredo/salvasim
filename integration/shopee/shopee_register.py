import os
import time
import hmac
import hashlib
import tempfile
import requests
import pandas as pd
from supabase import create_client

from auth import pegar_token

# ==================================================
# CONFIG
# ==================================================
PARTNER_ID = 2014045
PARTNER_KEY = "shpk55617356626c5347767977714e586e4c4f557075544e546e42784a757967"
SHOP_ID = 1588032704

BASE_URL = "https://partner.shopeemobile.com"
CSV_PATH = "integration/produtos_shopee.csv"

ESTOQUE_PADRAO = 50
MARCA_PADRAO = "GENERICA"

# Supabase Config
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==================================================
# TOKEN
# ==================================================
ACCESS_TOKEN = pegar_token()

# ==================================================
# CATEGORIAS
# ==================================================
SUBCATEGORIA_CATEGORY_MAP = {
    # BEBIDAS
    "aguas": 100828,
    "cervejas": 100831,
    "champanhes-espumantes-e-sidras": 100831,
    "chas-prontos": 100825,
    "coqueteis": 100831,
    "destilados": 100831,
    "energeticos-e-isotonicos": 100827,
    "refrigerantes": 100831,
    "sucos-e-refrescos": 100829,

    # ALIMENTOS
    "acucar-e-adocantes": 100806,
    "azeites-oleos-e-vinagres": 101589,
    "farinhas": 100815,
    "graos": 101579,
    "massas-e-molhos": 100799,
    "sopas-e-cremes": 100807,

    # DOCES
    "biscoitos": 100787,
    "bomboniere": 100785,
    "chocolates": 100786,
    "confeitaria": 100785,
    "doces": 100785,
    "salgadinhos-e-snacks": 100788,

    # CONDIMENTOS
    "temperos-e-condimentos": 101586,

    # CAFÉ / CEREAIS
    "aveias-e-cereais": 100821,
    "paes-e-torradas": 100856,
    "mel-geleias-e-pates": 100820,

    # LATICÍNIOS
    "leites": 100846,

    # LIMPEZA
    "limpeza-de-banheiro": 101213,
    "limpeza-de-casa": 101213,
    "limpeza-de-cozinha": 101213,
    "limpeza-de-roupas": 101814,

    # HIGIENE
    "bebes": 100972,
    "cabelo": 100869,
    "corpo": 102003,
    "desodorantes": 102008,
    "higiene-bucal": 100440,
    "papel-higienico": 101212,
    "sabonetes": 102003,

    # DEFAULT
    "__default__": 100800
}

SUBCATEGORIAS_PERMITIDAS = [
    "aguas", "chas-prontos", "energeticos-e-isotonicos", "refrigerantes", "sucos-e-refrescos",
    "acucar-e-adocantes", "azeites-oleos-e-vinagres", "farinhas", "graos", "massas-e-molhos", "sopas-e-cremes",
    "biscoitos", "bomboniere", "chocolates", "confeitaria", "doces", "salgadinhos-e-snacks",
    "temperos-e-condimentos", "aveias-e-cereais", "mel-geleias-e-pates", "leites",
    "limpeza-de-banheiro", "limpeza-de-casa", "limpeza-de-cozinha", "limpeza-de-roupas",
    "bebes", "cabelo", "corpo", "desodorantes", "higiene-bucal", "papel-higienico"
]

def escolher_categoria_por_subcategoria(subcategoria):
    if not subcategoria:
        return SUBCATEGORIA_CATEGORY_MAP["__default__"]
    sub = str(subcategoria).strip().lower()
    return SUBCATEGORIA_CATEGORY_MAP.get(sub, SUBCATEGORIA_CATEGORY_MAP["__default__"])

# ==================================================
# ASSINATURA
# ==================================================
def sign_media(path):
    ts = int(time.time())
    base = f"{PARTNER_ID}{path}{ts}"
    sign = hmac.new(PARTNER_KEY.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()
    return ts, sign

def sign_api(path):
    global ACCESS_TOKEN
    ACCESS_TOKEN = pegar_token()
    ts = int(time.time())
    base = f"{PARTNER_ID}{path}{ts}{ACCESS_TOKEN}{SHOP_ID}"
    sign = hmac.new(PARTNER_KEY.encode(), base.encode(), hashlib.sha256).hexdigest()
    return ts, sign

# ==================================================
# DOWNLOAD E UPLOAD DE IMAGEM
# ==================================================
def baixar_imagem(url):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    tmp.write(resp.content)
    tmp.close()
    return tmp.name

def upload_imagem(url_imagem):
    try:
        caminho_local = baixar_imagem(url_imagem)
        path = "/api/v2/media_space/upload_image"
        ts, sign = sign_media(path)
        url = f"{BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={ts}&sign={sign}"

        with open(caminho_local, "rb") as f:
            r = requests.post(url, files={"image": f}, data={"scene": "normal"}, timeout=30)

        os.remove(caminho_local)
        resp = r.json()

        if resp.get("error"):
            print(f"❌ Erro upload imagem: {resp.get('message', 'Erro desconhecido')}")
            return None

        return resp["response"]["image_info"]["image_id"]
    except Exception as e:
        print(f"❌ Erro upload imagem: {e}")
        return None

# ==================================================
# CARREGAR PRODUTOS NOVOS DO SUPABASE
# ==================================================
def carregar_produtos_novos():
    print("📊 Carregando dados do Supabase (silver_products)...")
    todos_registros = []
    chunk_size = 1000
    offset = 0
    
    # Paginação para garantir que traz todos os dados do Supabase
    while True:
        response = supabase.table("silver_products").select("*").range(offset, offset + chunk_size - 1).execute()
        if not response.data: 
            break
        todos_registros.extend(response.data)
        offset += chunk_size
        
    df_silver = pd.DataFrame(todos_registros)
    
    if df_silver.empty:
        print("⚠️ A tabela 'silver_products' retornou vazia do Supabase.")
        return pd.DataFrame()

    print(f"✅ {len(df_silver)} registros carregados do Supabase.")

    # Normalizar e filtrar subcategorias permitidas
    df_silver["subcategoria"] = df_silver["subcategoria"].astype(str).str.lower().str.strip()
    df_silver = df_silver[df_silver["subcategoria"].isin(SUBCATEGORIAS_PERMITIDAS)]

    # Mapear o nome da coluna de imagem vinda do Supabase (caso venha como 'imagem' ou 'url_imagem')
    coluna_img_silver = next((col for col in df_silver.columns if col.lower() in ['imagem', 'image', 'url_imagem', 'img']), "imagem")
    df_silver["imagem_url"] = df_silver.get(coluna_img_silver, "")

    if not os.path.exists(CSV_PATH):
        print(f"⚠️ Arquivo {CSV_PATH} não encontrado. Todos os produtos filtrados serão considerados novos.")
        df_shopee = pd.DataFrame(columns=["Nome do Produto", "ID do Produto"])
    else:
        df_shopee = pd.read_csv(CSV_PATH)
        df_shopee.columns = df_shopee.columns.str.strip().str.replace('\ufeff', '')

    # Normalização para comparação (merge)
    coluna_nome_silver = next((c for c in ['nome_original', 'nome_produto', 'nome'] if c in df_silver.columns), 'nome')
    df_silver["nome_merge"] = df_silver[coluna_nome_silver].astype(str).str.lower().str.strip()
    # Padroniza a coluna principal de nome para o restante do script usar row['nome']
    df_silver["nome"] = df_silver[coluna_nome_silver]
    
    col_nome_csv = next((c for c in ["Nome do Produto", "Nome Original"] if c in df_shopee.columns), None)
    if col_nome_csv:
        df_shopee["nome_merge"] = df_shopee[col_nome_csv].astype(str).str.lower().str.strip()
    else:
        df_shopee["nome_merge"] = ""

    df_novos = df_silver[~df_silver["nome_merge"].isin(df_shopee["nome_merge"])].copy()
    print(f"🆕 Total de produtos novos para cadastrar: {len(df_novos)}")

    return df_novos

# ==================================================
# REQUEST RETRY
# ==================================================
def request_com_retry(method, url, payload=None, tentativas=3):
    for i in range(tentativas):
        try:
            if method == "POST":
                r = requests.post(url, json=payload, timeout=60)
            else:
                r = requests.get(url, params=payload, timeout=60)
            return r
        except Exception as e:
            print(f"⚠️ Tentativa {i+1} falhou: {e}")
            time.sleep(3)
    return None

# ==================================================
# CRIAR PRODUTO NA SHOPEE
# ==================================================
def criar_produto(row):
    path = "/api/v2/product/add_item"
    ts, sign = sign_api(path)
    url = f"{BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={ts}&sign={sign}&access_token={ACCESS_TOKEN}&shop_id={SHOP_ID}"

    image_id = upload_imagem(row.get("imagem_url"))
    if not image_id:
        return None

    # Validação segura do preço para evitar NaN / float inválido no JSON
    preco = row.get("preco_venda")
    if pd.isna(preco) or float(preco) <= 0:
        print("❌ Preço de venda inválido ou ausente.")
        return None
    preco = round(float(preco), 2)

    # Validação segura do peso
    peso = row.get("peso", 0.2)
    try:
        peso = float(peso)
        if pd.isna(peso) or peso < 0.1:
            peso = 0.2
    except:
        peso = 0.2

    descricao = row.get("descricao")
    if not descricao or str(descricao) == "nan":
        descricao = row["nome"]

    payload = {
        "item_name": str(row["nome"])[:120],
        "description": str(descricao)[:3000],
        "category_id": escolher_categoria_por_subcategoria(row.get("subcategoria")),
        "original_price": preco,
        "weight": peso,
        "condition": "NEW",  # Obrigatório pela API da Shopee
        "dimension": {"package_length": 10, "package_width": 10, "package_height": 10},
        "seller_stock": [{"stock": ESTOQUE_PADRAO}],
        "brand": {"brand_id": 0, "original_brand_name": MARCA_PADRAO},
        "image": {"image_id_list": [image_id] * 4},
        "logistic_info": [
            {"logistic_id": 91003, "enabled": True, "is_free": False},
            {"logistic_id": 90024, "enabled": True, "is_free": False}
        ],
        "tax_info": {
            "ncm": str(row.get("ncm", "00")),
            "same_state_cfop": "5102",
            "diff_state_cfop": "6102",
            "csosn": "102",
            "origin": "0",
            "cest": "00",
            "measure_unit": "UN"
        },
        "gtin_code": "00"
    }

    r = request_com_retry("POST", url, payload=payload)
    if not r or r.status_code != 200:
        print(f"❌ Erro na requisição HTTP para criar o produto.")
        return None

    try:
        resp = r.json()
        if resp.get("error"):
            print(f"❌ Erro retornado pela API da Shopee: {resp.get('message')}")
            return None
        return resp.get("response", {}).get("item_id")
    except Exception as e:
        print(f"❌ Erro ao decodificar resposta JSON: {e}")
        return None

# ==================================================
# SALVAR NO CSV DE CONTROLE
# ==================================================
def salvar_produto_csv(item_id, nome):
    try:
        novo = pd.DataFrame([{
            "ID do Produto": item_id,
            "Nome do Produto": nome
        }])

        if os.path.exists(CSV_PATH):
            df = pd.read_csv(CSV_PATH)
            df = pd.concat([df, novo], ignore_index=True)
        else:
            df = novo

        df.to_csv(CSV_PATH, index=False)
    except Exception as e:
        print(f"❌ Erro ao salvar no CSV: {e}")

# ==================================================
# EXECUÇÃO PRINCIPAL DO CADASTRO
# ==================================================
def cadastrar_novos_produtos():
    print("\n🚀 Iniciando rotina de cadastro de novos produtos via Supabase...")
    df_novos = carregar_produtos_novos()

    if df_novos.empty:
        print("✨ Nenhum produto novo para cadastrar.")
        return

    for _, row in df_novos.iterrows():
        nome_prod = row['nome']
        print(f"\n➕ Cadastrando: {nome_prod}")
        
        try:
            item_id = criar_produto(row)
            if item_id:
                salvar_produto_csv(item_id, nome_prod)
                print(f"✅ Sucesso! Produto criado com ID: {item_id}")
            else:
                print(f"❌ Falha ao cadastrar: {nome_prod}")
        except Exception as e:
            print(f"❌ Erro crítico no loop de cadastro: {e}")

        time.sleep(5)  # Respiro para respeitar o limite de requisições

if __name__ == "__main__":
    cadastrar_novos_produtos()
