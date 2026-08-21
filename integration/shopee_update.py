import os
import pandas as pd
from supabase import create_client
from auth import pegar_token
# Importando as funções do seu script original
from integration.shopee_update import (
    atualizar_preco, atualizar_item_completo, set_status_item, 
    CSV_PATH, SUPABASE_URL, SUPABASE_KEY
)

def atualizar_produto_pelo_nome(nome_busca):
    print(f"🔍 Buscando dados para: {nome_busca}")
    
    # 1. Busca na Silver
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    response = supabase.table("silver_products").select("*").execute()
    df_silver = pd.DataFrame(response.data)
    
    # Filtra linha exata (usando o nome do produto)
    produto_silver = df_silver[df_silver['nome_produto'].str.contains(nome_busca, case=False, na=False)]
    
    if produto_silver.empty:
        print("❌ Produto não encontrado na Silver (Supabase).")
        return

    dados = produto_silver.iloc[0]
    print(f"✅ Encontrado na Silver: {dados['nome_produto']}")

    # 2. Busca o ID no CSV (para saber qual produto é na Shopee)
    df_ids = pd.read_csv(CSV_PATH)
    # Filtra o ID correspondente ao nome no CSV
    match_csv = df_ids[df_ids['Nome do Produto'].str.contains(nome_busca, case=False, na=False)]
    
    if match_csv.empty:
        print("❌ Produto não encontrado no seu arquivo CSV local da Shopee.")
        return
        
    item_id = int(match_csv.iloc[0]['ID do Produto'])
    print(f"🎯 ID encontrado na Shopee: {item_id}")

    # 3. Executa a atualização
    token = pegar_token()
    print("🚀 Iniciando atualização via API Shopee...")
    
    set_status_item(item_id, False, token)
    atualizar_preco(item_id, dados['preco_venda'], token)
    atualizar_item_completo(
        item_id, 
        dados['nome_produto'], 
        dados['descricao'], 
        dados['Imagem'], 
        dados['peso'], 
        token
    )
    print("🏁 Atualização concluída!")

if __name__ == "__main__":
    atualizar_produto_pelo_nome("Sabonete Lux Orquídea Negra 6x85g")