import time
import hashlib
import hmac
import requests
import os

# Configurações lidas do ambiente (GitHub Secrets)
PARTNER_ID = int(os.environ.get("SHOPEE_PARTNER_ID", 2014045))
PARTNER_KEY = os.environ.get("SHOPEE_PARTNER_KEY", "shpk55617356626c5347767977714e586e4c4f557075544e546e42784a757967")
SHOP_ID = int(os.environ.get("SHOPEE_SHOP_ID", 1588032704))

BASE_URL = "https://partner.shopeemobile.com"

# ============================
# GERAR ASSINATURA
# ============================
def gerar_assinatura(path):
    timestamp = int(time.time())
    # Nota: A assinatura da Shopee para auth/token/get geralmente não leva o access_token/shop_id
    base_string = f"{PARTNER_ID}{path}{timestamp}"
    sign = hmac.new(
        PARTNER_KEY.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return timestamp, sign

# ============================
# PEGAR TOKEN DO AMBIENTE (COM RENOVAÇÃO AUTOMÁTICA)
# ============================
def pegar_token():
    """
    Tenta renovar o token via API usando o SHOPEE_REFRESH_TOKEN 
    para garantir que sempre teremos um token válido e fresco.
    """
    try:
        print("🔄 Solicitando novo access_token via refresh_token...")
        token_novo = renovar_token_via_api()
        return token_novo
    except Exception as e:
        print(f"⚠️ Falha ao renovar via API ({e}). Tentando usar o SHOPEE_ACCESS_TOKEN estático...")
        
        # Fallback caso a renovação falhe: tenta pegar o token direto do ambiente
        token = os.environ.get("SHOPEE_ACCESS_TOKEN")
        if not token:
            raise Exception("❌ Nem o refresh_token funcionou e nem o SHOPEE_ACCESS_TOKEN foi encontrado.")
        return token

# ============================
# RENOVAR TOKEN (Adaptação para GitHub Actions)
# ============================
def renovar_token_via_api():
    """
    Nota: Em GitHub Actions, renovar o token e tentar salvar de volta 
    é complexo pois o ambiente é efêmero. O ideal é que seu token 
    tenha uma validade longa ou você use o refresh_token para obter um novo
    e atualizar manualmente no GitHub Secrets se necessário.
    """
    refresh_token = os.environ.get("SHOPEE_REFRESH_TOKEN")
    path = "/api/v2/auth/access_token/get"
    timestamp, sign = gerar_assinatura(path)

    url = f"{BASE_URL}{path}?partner_id={PARTNER_ID}&timestamp={timestamp}&sign={sign}"

    payload = {
        "refresh_token": refresh_token,
        "partner_id": PARTNER_ID,
        "shop_id": SHOP_ID
    }

    r = requests.post(url, json=payload)
    data = r.json()

    if data.get("error"):
        raise Exception(f"Erro ao renovar token: {data}")

    print("🔄 Novo token obtido com sucesso. Atualize seu GitHub Secret SHOPEE_ACCESS_TOKEN.")
    return data["access_token"]