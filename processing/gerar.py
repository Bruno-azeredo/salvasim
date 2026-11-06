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

# 1. Passo 1: Mostra o link para você autorizar no navegador
path = "/api/v2/shop/auth_partner"
timestamp, sign = gerar_assinatura(path)
# ATENÇÃO: Substitua 'https://sua-redirect-url.com' pela URL de redirecionamento cadastrada no seu app na Shopee Open Platform
redirect_url = "https://sua-redirect-url.com" 

url_auth = f"{BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={timestamp}&sign={sign}&redirect={redirect_url}"

print("\n👉 Abra este link no seu navegador, faça login e autorize a loja:")
print(url_auth)
print("\n")

# 2. Passo 2: Cole aqui o código 'code' que veio na URL de redirecionamento
code = input("Cole o código (code) retornado pela URL da Shopee: ").strip()

# 3. Troca o code pelos tokens definitivos
token_path = "/api/v2/auth/token/get"
t_ts, t_sign = gerar_assinatura(token_path)

token_url = f"{BASE_URL}{token_path}?partner_id={PARTNER_ID}&timestamp={t_ts}&sign={t_sign}"

payload = {
    "code": code,
    "partner_id": PARTNER_ID,
    "shop_id": SHOP_ID
}

r = requests.post(token_url, json=payload)
data = r.json()

if data.get("error"):
    print(f"❌ Erro ao gerar token: {data}")
else:
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    expire_at = time.time() + data["expire_in"] - 60

    # Salva os tokens reais no Supabase na linha id = 1
    supabase.table("shopee_token").update({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expire_at": expire_at
    }).eq("id", 1).execute()

    print("✅ Sucesso! Token gerado e salvo no Supabase com sucesso.")