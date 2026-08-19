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
    print("🚀 Atualizando dimensão de produtos no Supabase...")

    url_db = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url_db or not key:
        print("❌ Credenciais do Supabase não encontradas nas variáveis de ambiente.")
        return

    supabase = create_client(url_db, key)

    # 📥 Lê a camada silver diretamente do Supabase (substituindo o arquivo local)
    print("📥 Buscando dados da tabela `silver_products` no Supabase...")
    df_silver = fetch_all_from_supabase(supabase, "silver_products")

    if df_silver.empty:
        print("❌ Nenhum registro encontrado na tabela `silver_products`. Execute o silver.py primeiro.")
        return

    # 🧠 Produtos únicos da extração atual
    df_unique = df_silver[
        ["id", "nome_produto", "preco_custo"]
    ].drop_duplicates("id")

    # 📥 Busca a dimensão atual diretamente do Supabase
    df_base = fetch_all_from_supabase(supabase, "dim_products")

    # =========================
    # COMPATIBILIDADE / TIPAGEM
    # =========================
    if not df_base.empty:
        df_base["vender_como_kit"] = df_base["vender_como_kit"].fillna(False).astype(bool)
        df_base["quantidade_kit"] = df_base["quantidade_kit"].fillna(1).astype(int)

    # =========================
    # IDENTIFICAR NOVOS PRODUTOS
    # =========================
    if not df_base.empty:
        ids_existentes = set(df_base["id"])
        novos = df_unique[~df_unique["id"].isin(ids_existentes)].copy()
    else:
        novos = df_unique.copy()

    print(f"🆕 Novos produtos encontrados: {len(novos)}")

    registros_para_salvar = []

    if len(novos) > 0:
        novos["descricao"] = None
        novos["refrigerado"] = False

        # 🎁 Define kit apenas na criação
        kit_info = novos["preco_custo"].apply(definir_kit)
        novos["vender_como_kit"] = kit_info["vender_como_kit"]
        novos["quantidade_kit"] = kit_info["quantidade_kit"]
        
        data_atual = datetime.now().isoformat()
        novos["data_criacao"] = data_atual
        novos["data_atualizacao"] = None

        # Prepara o formato para envio ao Supabase
        df_novos_prontos = pd.DataFrame({
            "id": novos["id"],
            "nome_produto": novos["nome_produto"],
            "descricao": novos["descricao"],
            "refrigerado": novos["refrigerado"],
            "vender_como_kit": novos["vender_como_kit"],
            "quantidade_kit": novos["quantidade_kit"],
            "data_criacao": novos["data_criacao"],
            "data_atualizacao": novos["data_atualizacao"]
        })
        
        # Limpeza estrita de tipos para evitar erros de JSON
        for _, row in df_novos_prontos.iterrows():
            clean_row = {}
            for k, v in row.items():
                if pd.isna(v) or (isinstance(v, float) and (v == float('inf') or v == float('-inf'))):
                    clean_row[k] = None
                elif hasattr(v, "item"):
                    clean_row[k] = v.item()
                else:
                    clean_row[k] = v
            registros_para_salvar.append(clean_row)

    # =========================
    # SALVAR NO SUPABASE (UPSERT)
    # =========================
    if len(registros_para_salvar) > 0:
        batch_size = 500
        for i in range(0, len(registros_para_salvar), batch_size):
            batch = registros_para_salvar[i:i+batch_size]
            supabase.table("dim_products").upsert(batch).execute()
        print(f"✅ {len(registros_para_salvar)} novos produtos salvos no Supabase!")
    else:
        print("ℹ️ Nenhum produto novo para adicionar à dimensão.")

    # =========================
    # LOGS FINAIS
    # =========================
    df_final = fetch_all_from_supabase(supabase, "dim_products")

    print(f"\n📊 Total geral de produtos na dimensão (Supabase): {len(df_final)}")
    total_kits = int(df_final["vender_como_kit"].sum()) if not df_final.empty else 0
    print(f"🎁 Produtos configurados como kit: {total_kits}")
    print(f"📦 Produtos unitários: {len(df_final) - total_kits}")

if __name__ == "__main__":
    run()