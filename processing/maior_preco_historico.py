import os
import pandas as pd
from google.cloud import bigquery
from supabase import create_client, Client
import warnings

warnings.filterwarnings("ignore")

# =========================
# CONFIGURAÇÕES
# =========================
PROJECT_ID = "economiza-itap"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def run():
    print("🏔️ Calculando o maior preço histórico (ATH) por produto no BigQuery...")

    # 1. Conectar ao BigQuery
    client_bq = bigquery.Client(project=PROJECT_ID)
    
    # Query analítica que identifica a última carga e calcula o pico máximo histórico
    query = f"""
        WITH ultima_carga_data AS (
            -- Pega a data/hora exata da extração mais recente
            SELECT MAX(data_extracao) AS max_dt
            FROM `{PROJECT_ID}.silver.s_fat_precos`
        ),
        preco_mais_recente AS (
            -- Pega o preço atual exato da última carga para produtos ativos
            SELECT 
                f.id_produto, 
                f.url_produto, 
                f.preco AS preco_atual, 
                f.data_extracao
            FROM `{PROJECT_ID}.silver.s_fat_precos` f
            JOIN ultima_carga_data u ON f.data_extracao = u.max_dt
        ),
        maior_preco_historico AS (
            -- Calcula o maior preço já registado para cada produto em todo o histórico
            SELECT 
                id_produto,
                MAX(preco) AS maior_preco_registrado,
                MAX(data_extracao) AS data_maior_preco
            FROM `{PROJECT_ID}.silver.s_fat_precos`
            GROUP BY id_produto
        )
        SELECT 
            r.id_produto,
            r.url_produto,
            r.preco_atual,
            m.maior_preco_registrado AS preco_maximo_historico,
            ROUND(((m.maior_preco_registrado - r.preco_atual) / m.maior_preco_registrado) * 100, 2) AS percentual_desconto_historico,
            CAST(CURRENT_TIMESTAMP() AS STRING) AS data_atualizacao
        FROM preco_mais_recente r
        JOIN maior_preco_historico m ON r.id_produto = m.id_produto
        WHERE m.maior_preco_registrado > r.preco_atual  -- Traz apenas produtos que estão abaixo do seu pico histórico
        ORDER BY percentual_desconto_historico DESC
        LIMIT 500;
    """

    df = client_bq.query(query).to_dataframe()

    if df.empty:
        print("⚠️ Nenhum produto encontrado abaixo do preço máximo histórico.")
        return

    # 🛑 Garante unicidade por id_produto
    df = df.drop_duplicates(subset=["id_produto"], keep="first")

    print(f"📊 {len(df)} produtos comparados com o pico histórico. Sincronizando com o Supabase...")

    # 2. Conectar ao Supabase
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Erro: As variáveis de ambiente do Supabase não estão configuradas.")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 🧹 3. Limpa a tabela de serving no Supabase antes de inserir os dados atualizados
    try:
        supabase.table("maior_preco_historico").delete().neq("id_produto", "EXCLUIR_TUDO_INEXISTENTE").execute()
        print("🗑️ Tabela `maior_preco_historico` limpa com sucesso no Supabase.")
    except Exception as e:
        print(f"⚠️ Aviso ao tentar limpar a tabela maior_preco_historico: {e}")

    # 4. Trata dados para o formato aceito pelo JSON/Supabase
    df = df.where(pd.notnull(df), None)
    
    registros = []
    for reg in df.to_dict(orient="records"):
        clean_reg = {}
        for k, v in reg.items():
            if pd.isna(v):
                clean_reg[k] = None
            elif hasattr(v, "item"):
                clean_reg[k] = v.item()
            else:
                clean_reg[k] = v
        registros.append(clean_reg)

    # 5. Insere os novos dados na tabela do Supabase
    try:
        response = supabase.table("maior_preco_historico").insert(registros).execute()
        print("✅ Tabela `maior_preco_historico` atualizada com sucesso no Supabase!")
    except Exception as e:
        print(f"❌ Erro ao inserir dados no Supabase: {e}")
        raise e

if __name__ == "__main__":
    run()