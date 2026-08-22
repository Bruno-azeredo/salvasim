import time
import hashlib
import hmac
import requests
import os
from supabase import create_client

PARTNER_ID = 2014045
PARTNER_KEY = "shpk55617356626c5347767977714e586e4c4f557075544e546e42784a757967"
SHOP_ID = 1588032704
BASE_URL = "https://partner.shopeemobile.com"

# Conexão com o Supabase usando as variáveis de ambiente do GitHub Actions ou local
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================
# GERAR ASSINATURA
# ============================
def gerar_assinatura(path):
    timestamp = int(time.time())
    base_string = f"{PARTNER_ID}{path}{timestamp}"

    sign = hmac.new(
        PARTNER_KEY.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return timestamp, sign

# ============================
# PEGAR TOKEN DO SUPABASE
# ============================
def pegar_token():
    response = supabase.table("shopee_token").select("access_token, refresh_token, expire_at").limit(1).execute()
    
    if not response.data:
        raise Exception("Token não encontrado na tabela 'shopee_token' do Supabase")

    row = response.data[0]
    access_token = row["access_token"]
    refresh_token = row["refresh_token"]
    expire_at = row["expire_at"]

    # Se expirou, renova
    if time.time() > expire_at:
        return renovar_token(refresh_token)

    return access_token

# ============================
# RENOVAR TOKEN
# ============================
def renovar_token(refresh_token):
    path = "/api/v2/auth/access_token/get"
    timestamp, sign = gerar_assinatura(path)

    url = (
        f"{BASE_URL}{path}"
        f"?partner_id={PARTNER_ID}"
        f"&timestamp={timestamp}"
        f"&sign={sign}"
    )

    payload = {
        "refresh_token": refresh_token,
        "partner_id": PARTNER_ID,
        "shop_id": SHOP_ID
    }

    r = requests.post(url, json=payload)
    data = r.json()

    if data.get("error"):
        raise Exception(f"Erro ao renovar token: {data}")

    novo_access = data["access_token"]
    novo_refresh = data["refresh_token"]
    expire_at = time.time() + data["expire_in"] - 60  # margem de segurança

    # Atualiza no Supabase
    supabase.table("shopee_token").update({
        "access_token": novo_access,
        "refresh_token": novo_refresh,
        "expire_at": expire_at
    }).eq("id", 1).execute()  # Ajuste o filtro 'id' conforme sua tabela

    print("🔄 Token renovado automaticamente no Supabase")

    return novo_access