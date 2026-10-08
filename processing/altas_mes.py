import os
import pandas as pd
from google.cloud import bigquery
from supabase import create_client, Client
import warnings

warnings.filterwarnings("ignore")

PROJECT_ID = "economiza-itap"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def run():
    print("📈 Calculando maiores altas do mês com preços reais e atualizados...")

    client_bq = bigquery.Client(project=PROJECT_ID)
    
    query = f"""
        WITH ultima_carga_data AS (
            SELECT MAX(data_extracao) AS max_dt
            FROM `{PROJECT_ID}.silver.s_fat_precos`
        ),
        preco_mais_recente AS (
            SELECT f.id_produto, f.url_produto, f.preco AS preco_atual, f.data_extracao
            FROM `{PROJECT_ID}.silver.s_fat_precos` f
            JOIN ultima_carga_data u ON f.data_extracao = u.max_dt
        ),
        media_mes_anterior AS (
            SELECT 
                id_produto,
                AVG(preco) AS preco_medio_anterior
            FROM `{PROJECT_ID}.silver.s_fat_precos`
            WHERE EXTRACT(YEAR FROM data_extracao) = EXTRACT(YEAR FROM DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH))
              AND EXTRACT(MONTH FROM data_extracao) = EXTRACT(MONTH FROM DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH))
            GROUP BY id_produto
        )
        SELECT 
            r.id_produto,
            r.url_produto,
            r.preco_atual,
            m.preco_medio_anterior AS preco_anterior,
            ROUND(((r.preco_atual - m.preco_medio_anterior) / m.preco_medio_anterior) * 100, 2) AS percentual_alta,
            CAST(CURRENT_TIMESTAMP() AS STRING) AS data_atualizacao
        FROM preco_mais_recente r
        JOIN media_mes_anterior m ON r.id_produto = m.id_produto
        WHERE r.preco_atual > m.preco_medio_anterior
        ORDER BY percentual_alta DESC
        LIMIT 200;
    """

    df = client_bq.query(query).to_dataframe()
    if df.empty:
        print("⚠️ Nenhuma alta mensal encontrada.")
        return

    df = df.drop_duplicates(subset=["id_produto"], keep="first")

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    supabase.table("altas_mes").delete().neq("id_produto", "EXCLUIR_TUDO_INEXISTENTE").execute()

    df = df.where(pd.notnull(df), None)
    registros = [{k: (v.item() if hasattr(v, "item") else v) for k, v in reg.items() if not pd.isna(v)} for reg in df.to_dict(orient="records")]
    
    supabase.table("altas_mes").insert(registros).execute()
    print("✅ Tabela `altas_mes` atualizada com preços reais!")

if __name__ == "__main__":
    run()