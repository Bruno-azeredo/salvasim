import pandas as pd
import os
import time
from datetime import datetime
from supabase import create_client
from openai import OpenAI

# Inicializa o cliente OpenAI
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# =========================
# FUNÇÕES DE IA
# =========================
def gerar_descricao(nome, vender_como_kit=False, quantidade_kit=1):
    try:
        contexto = f"O cliente receberá {quantidade_kit} unidades." if vender_como_kit else "Produto vendido unitariamente."
        prompt = f"""Crie uma descrição para um anúncio da Shopee.
        Produto: "{nome}"
        IMPORTANTE:
        - {contexto}
        - Deixe isso explícito logo na primeira frase.
        - Não invente características.
        - Informe peso ou volume quando existir no nome.
        - Texto curto para e-commerce."""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Erro ao gerar descrição: {e}")
        return None

# =========================
# PIPELINE DE ENRIQUECIMENTO
# =========================
def run():
    print("🚀 Iniciando enriquecimento de produtos no Supabase...")

    url_db = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    supabase = create_client(url_db, key)

    # 1. Busca produtos que precisam de descrição (vazia ou nula)
    # Filtro: descricao é NULL
    response = supabase.table("dim_products").select("*").is_("descricao", "null").execute()
    produtos_para_enriquecer = response.data

    if not produtos_para_enriquecer:
        print("✅ Nenhum produto sem descrição encontrado!")
        return

    print(f"🆕 Encontrados {len(produtos_para_enriquecer)} produtos para gerar descrição.")

    for produto in produtos_para_enriquecer:
        nome = produto["nome_produto"]
        
        print(f"🤖 Gerando descrição para: {nome}")
        
        descricao = gerar_descricao(
            nome=nome,
            vender_como_kit=produto.get("vender_como_kit", False),
            quantidade_kit=produto.get("quantidade_kit", 1)
        )

        if descricao:
            # Atualiza no Supabase
            supabase.table("dim_products").update({
                "descricao": descricao,
                "data_atualizacao": datetime.now().isoformat()
            }).eq("id", produto["id"]).execute()
            
            print(f"✅ Descrição salva para {nome}")
        
        # Delay de segurança para não estourar limite da API
        time.sleep(1)

    print("🏁 Enriquecimento concluído!")

if __name__ == "__main__":
    run()