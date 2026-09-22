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
    print("🔥 Calculando as melhores ofertas do dia no BigQuery...")

    # 1. Conectar ao BigQuery
    client_bq = bigquery.Client(project=PROJECT_ID)
    
    # Query analítica que identifica as maiores quedas de preço do dia atual comparadas com a coleta anterior
    query = f"""
        WITH precos_recentes AS (
            SELECT 
                id_produto,
                url_produto,
                preco AS preco_atual,
                data_extracao,
                LAG(preco) OVER(PARTITION BY id_produto ORDER BY data_extracao ASC) AS preco_anterior
            FROM `{PROJECT_ID}.silver.s_fat_precos`
        )
        SELECT 
            id_produto,
            url_produto,
            preco_atual,
            preco_anterior,
            ROUND(((preco_anterior - preco_atual) / preco_anterior) * 100, 2) AS percentual_desconto,
            CAST(data_extracao AS STRING) AS data_extracao
        FROM precos_recentes
        WHERE DATE(data_extracao) = CURRENT_DATE()
          AND preco_anterior IS NOT NULL 
          AND preco_atual < preco_anterior
        ORDER BY percentual_desconto DESC
        LIMIT 30;
    """

    df = client_bq.query(query).to_dataframe()

    if df.empty:
        print("⚠️ Nenhuma oferta de destaque encontrada hoje.")
        return

    print(f"📊 {len(df)} ofertas encontradas. Sincronizando com o Supabase...")

    # 2. Conectar ao Supabase (usando a chave de serviço para evitar bloqueios de RLS)
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Erro: As variáveis de ambiente do Supabase não estão configuradas.")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 3. Limpa a tabela de ofertas do dia anterior para atualizar com o ranking fresco
    try:
        supabase.table("ofertas_dia").delete().neq("id_produto", "0").execute()
    except Exception as e:
        print(f"ℹ️ Nota ao limpar tabela antiga (pode ser ignorado se estiver vazia): {e}")

    # 4. Trata dados e insere as novas ofertas do dia
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

    response = supabase.table("ofertas_dia").insert(registros).execute()

    print("✅ Tabela `ofertas_dia` atualizada com sucesso no Supabase!")

if __name__ == "__main__":
    run()