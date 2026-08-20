import pandas as pd
import os
from datetime import datetime
from supabase import create_client

# =========================
# FUNÇÃO AUXILIAR DE PAGINAÇÃO
# =========================
def fetch_all_from_supabase(supabase_client, table_name):
    """Busca todos os registros de uma tabela do Supabase com paginação"""
    all_data = []
    page_size = 1000
    start = 0
    while True:
        response = supabase_client.table(table_name).select("*").range(start, start + page_size - 1).execute()
        if not response.data:
            break
        all_data.extend(response.data)
        if len(response.data) < page_size:
            break
        start += page_size
    return pd.DataFrame(all_data)

# =========================
# REGRAS DE KIT
# =========================
def definir_kit(preco):
    if preco < 10:
        return pd.Series({
            "vender_como_kit": True,
            "quantidade_kit": 4
        })
    elif preco < 20:
        return pd.Series({
            "vender_como_kit": True,
            "quantidade_kit": 2
        })
    return pd.Series({
        "vender_como_kit": False,
        "quantidade_kit": 1
    })

# =========================
# PIPELINE
# =========================
def run():
    print("🚀 Atualizando dimensão de produtos no Supabase com base no Parquet...")

    url_db = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url_db or not key:
        print("❌ Credenciais do Supabase não encontradas nas variáveis de ambiente.")
        return

    supabase = create_client(url_db, key)

    # 1. Lê o arquivo products.parquet local para pegar as descrições personalizadas
    parquet_path = "products.parquet"
    if os.path.exists(parquet_path):
        df_parquet = pd.read_parquet(parquet_path)
        print(f"📁 Arquivo '{parquet_path}' carregado com sucesso. Registros: {len(df_parquet)}")
    else:
        print(f"⚠️ Arquivo '{parquet_path}' não encontrado. Prosseguindo sem descrições locais.")
        df_parquet = pd.DataFrame(columns=["id", "descricao"])

    # 2. Lê a camada silver diretamente do Supabase
    print("📥 Buscando dados da tabela `silver_products` no Supabase...")
    df_silver = fetch_all_from_supabase(supabase, "silver_products")

    if df_silver.empty:
        print("❌ Nenhum registro encontrado na tabela `silver_products`. Execute o silver.py primeiro.")
        return

    # Produtos únicos da extração atual
    df_unique = df_silver[
        ["id", "nome_produto", "preco_custo"]
    ].drop_duplicates("id").copy()

    # 3. Faz o merge com o DataFrame do parquet para trazer a descrição (por 'id')
    if not df_parquet.empty and "id" in df_parquet.columns and "descricao" in df_parquet.columns:
        # Garante que pegamos apenas id e descricao do parquet para evitar conflitos de colunas
        df_desc = df_parquet[["id", "descricao"]].drop_duplicates("id")
        df_unique = df_unique.merge(df_desc, on="id", how="left")
    else:
        df_unique["descricao"] = None

    # Preenche descrições nulas com None
    df_unique["descricao"] = df_unique["descricao"].where(pd.notnull(df_unique["descricao"]), None)

    # 4. Busca a dimensão atual diretamente do Supabase
    df_base = fetch_all_from_supabase(supabase, "dim_products")

    if not df_base.empty:
        df_base["vender_como_kit"] = df_base["vender_como_kit"].fillna(False).astype(bool)
        df_base["quantidade_kit"] = df_base["quantidade_kit"].fillna(1).astype(int)

    # Identifica IDs existentes na base do Supabase
    ids_existentes = set(df_base["id"]) if not df_base.empty else set()

    registros_para_salvar = []
    data_atual = datetime.now().isoformat()

    # 5. Processa cada produto (novos e atualização de descrição para existentes)
    for _, row in df_unique.iterrows():
        prod_id = row["id"]
        nome_prod = row["nome_produto"]
        preco = row["preco_custo"]
        desc_parquet = row["descricao"]

        if prod_id not in ids_existentes:
            # Produto Novo: define kit e usa a descrição do parquet (se houver)
            kit_info = definir_kit(preco)
            registro = {
                "id": prod_id,
                "nome_produto": nome_prod,
                "descricao": desc_parquet,
                "refrigerado": False,
                "vender_como_kit": kit_info["vender_como_kit"],
                "quantidade_kit": kit_info["quantidade_kit"],
                "data_criacao": data_atual,
                "data_atualizacao": None
            }
        else:
            # Produto já existe: se o parquet tiver uma descrição cadastrada, podemos atualizar
            registro = {
                "id": prod_id,
                "nome_produto": nome_prod,
                "descricao": desc_parquet if desc_parquet else None,
                "data_atualizacao": data_atual
            }
        
        registros_para_salvar.append(registro)

    # 6. Limpeza estrita de tipos e envio via UPSERT para o Supabase
    if len(registros_para_salvar) > 0:
        dados_limpos = []
        for reg in registros_para_salvar:
            clean_reg = {}
            for k, v in reg.items():
                if pd.isna(v) or (isinstance(v, float) and (v == float('inf') or v == float('-inf'))):
                    clean_reg[k] = None
                elif hasattr(v, "item"):
                    clean_reg[k] = v.item()
                else:
                    clean_reg[k] = v
            dados_limpos.append(clean_reg)

        batch_size = 500
        for i in range(0, len(dados_limpos), batch_size):
            batch = dados_limpos[i:i+batch_size]
            supabase.table("dim_products").upsert(batch).execute()
            
        print(f"✅ {len(dados_limpos)} produtos sincronizados/atualizados com sucesso no Supabase!")
    else:
        print("ℹ️ Nenhum produto para atualizar.")

    # =========================
    # LOGS FINAIS
    # =========================
    df_final = fetch_all_from_supabase(supabase, "dim_products")

    print(f"\n📊 Total geral de produtos na dimensão (Supabase): {len(df_final)}")
    total_kits = int(df_final["vender_como_kit"].sum()) if not df_final.empty and "vender_como_kit" in df_final.columns else 0
    print(f"🎁 Produtos configurados como kit: {total_kits}")
    print(f"📦 Produtos unitários: {len(df_final) - total_kits}")

if __name__ == "__main__":
    run()