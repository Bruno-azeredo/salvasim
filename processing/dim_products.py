import pandas as pd
import os
from datetime import datetime
from supabase import create_client

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

    # 📥 Lê a camada silver local (ou do Supabase, dependendo de onde o silver salva)
    # Se o silver.py ainda salvar o silver.parquet localmente, mantemos a leitura:
    if os.path.exists("data/silver.parquet"):
        df_silver = pd.read_parquet("data/silver.parquet")
    else:
        print("❌ Arquivo data/silver.parquet não encontrado. Execute o silver.py primeiro.")
        return

    # 🧠 Produtos únicos da extração atual
    df_unique = df_silver[
        ["id", "nome_produto", "preco_custo"]
    ].drop_duplicates("id")

    # 📥 Busca a dimensão atual diretamente do Supabase
    response = supabase.table("dim_products").select("*").execute()
    dados_base = response.data

    if dados_base:
        df_base = pd.DataFrame(dados_base)
    else:
        df_base = pd.DataFrame(columns=[
            "id",
            "nome_produto",
            "descricao",
            "refrigerado",
            "vender_como_kit",
            "quantidade_kit",
            "data_criacao",
            "data_atualizacao"
        ])

    # =========================
    # COMPATIBILIDADE / TIPAGEM
    # =========================
    if len(df_base) > 0:
        df_base["vender_como_kit"] = df_base["vender_como_kit"].fillna(False).astype(bool)
        df_base["quantidade_kit"] = df_base["quantidade_kit"].fillna(1).astype(int)

    # =========================
    # IDENTIFICAR NOVOS PRODUTOS
    # =========================
    if len(df_base) > 0:
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

        # Prepara o formato para envio ao Supabase (remove colunas extras)
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
        
        registros_para_salvar = df_novos_prontos.to_dict(orient="records")

    # =========================
    # SALVAR NO SUPABASE (UPSERT)
    # =========================
    if len(registros_para_salvar) > 0:
        # O upsert insere se não existir (baseado na chave primária 'id' da tabela do Supabase)
        supabase.table("dim_products").upsert(registros_para_salvar).execute()
        print(f"✅ {len(registros_para_salvar)} novos produtos salvos no Supabase!")
    else:
        print("ℹ️ Nenhum produto novo para adicionar à dimensão.")

    # =========================
    # LOGS FINAIS
    # =========================
    # Busca a tabela atualizada para exibir as métricas corretas
    response_final = supabase.table("dim_products").select("*").execute()
    df_final = pd.DataFrame(response_final.data)

    print(f"\n📊 Total geral de produtos na dimensão (Supabase): {len(df_final)}")
    total_kits = int(df_final["vender_como_kit"].sum()) if not df_final.empty else 0
    print(f"🎁 Produtos configurados como kit: {total_kits}")
    print(f"📦 Produtos unitários: {len(df_final) - total_kits}")

if __name__ == "__main__":
    run()