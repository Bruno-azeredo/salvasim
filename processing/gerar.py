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

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def gerar_assinatura(path):
    timestamp = int(time.time())
    base_string = f"{PARTNER_ID}{path}{timestamp}"
    sign = hmac.new(PARTNER_KEY.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return timestamp, sign

code = "516876765950595251537268734e736e"
token_path = "/api/v2/auth/token/get"
t_ts, t_sign = gerar_assinatura(token_path)

token_url = f"{BASE_URL}{token_path}?partner_id={PARTNER_ID}&timestamp={t_ts}&sign={t_sign}"

payload = {
    "code": code,
    "partner_id": PARTNER_ID,
    "shop_id": SHOP_ID
}

print("🔄 Solicitando token à Shopee...", flush=True)
r = requests.post(token_url, json=payload)
data = r.json()

if data.get("error"):
    print(f"❌ Erro ao gerar token: {data}")
else:
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    expire_at = time.time() + data["expire_in"] - 60

    # Atualiza ou insere no Supabase na linha id = 1
    # Certifique-se de que a linha id = 1 existe na sua tabela (conforme orientamos anteriormente)
    supabase.table("shopee_token").upsert({
        "id": 1,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expire_at": expire_at
    }).execute()

    print("✅ Sucesso! Token gerado e salvo no Supabase com sucesso.")