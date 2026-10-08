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
    print("📈 Calculando as maiores altas de preços do mês no BigQuery...")

    # 1. Conectar ao BigQuery
    client_bq = bigquery.Client(project=PROJECT_ID)
    
    # Query analítica que identifica produtos ativos e compara o preço atual com a média do mês anterior (focando em aumentos)
    query = f"""
        WITH ultima_carga AS (
            SELECT MAX(DATE(data_extracao)) AS max_data
            FROM `{PROJECT_ID}.silver.s_fat_precos`
        ),
        produtos_ativos AS (
            SELECT DISTINCT id_produto
            FROM `{PROJECT_ID}.silver.s_fat_precos`, ultima_carga
            WHERE DATE(data_extracao) = max_data
        ),
        precos_por_mes AS (
            SELECT 
                f.id_produto,
                f.url_produto,
                EXTRACT(YEAR FROM f.data_extracao) AS ano,
                EXTRACT(MONTH FROM f.data_extracao) AS mes,
                AVG(f.preco) AS preco_medio_mes
            FROM `{PROJECT_ID}.silver.s_fat_precos` f
            INNER JOIN produtos_ativos a ON f.id_produto = a.id_produto
            GROUP BY f.id_produto, f.url_produto, ano, mes
        ),
        comparacao_mensal AS (
            SELECT 
                atual.id_produto,
                atual.url_produto,
                atual.preco_medio_mes AS preco_atual,
                anterior.preco_medio_mes AS preco_anterior,
                LAG(atual.preco_medio_mes) OVER(PARTITION BY atual.id_produto ORDER BY atual.ano ASC, atual.mes ASC) AS preco_lag
            FROM precos_por_mes atual
            LEFT JOIN precos_por_mes anterior 
                ON atual.id_produto = anterior.id_produto 
                AND (
                    (atual.mes = 1 AND anterior.mes = 12 AND anterior.ano = atual.ano + 1)
                    OR (atual.mes > 1 AND anterior.mes = atual.mes - 1 AND anterior.ano = atual.ano)
                )
        )
        SELECT 
            id_produto,
            url_produto,
            preco_atual,
            COALESCE(preco_anterior, preco_lag) AS preco_anterior,
            ROUND(((preco_atual - COALESCE(preco_anterior, preco_lag)) / COALESCE(preco_anterior, preco_lag)) * 100, 2) AS percentual_alta,
            CAST(CURRENT_TIMESTAMP() AS STRING) AS data_atualizacao
        FROM comparacao_mensal
        WHERE preco_anterior IS NOT NULL 
          AND preco_atual > preco_anterior
        ORDER BY percentual_alta DESC
        LIMIT 200;
    """

    df = client_bq.query(query).to_dataframe()

    if df.empty:
        print("⚠️ Nenhuma alta de preço mensal encontrada para produtos ativos.")
        return

    # 🛑 Garante unicidade por id_produto
    df = df.drop_duplicates(subset=["id_produto"], keep="first")

    print(f"📊 {len(df)} produtos com alta de preço encontrados. Sincronizando com o Supabase...")

    # 2. Conectar ao Supabase
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Erro: As variáveis de ambiente do Supabase não estão configuradas.")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 🧹 3. Limpa completamente a tabela de altas mensais antigas antes de carregar as novas
    try:
        supabase.table("altas_mes").delete().neq("id_produto", "EXCLUIR_TUDO_INEXISTENTE").execute()
        print("🗑️ Tabela `altas_mes` limpa com sucesso no Supabase.")
    except Exception as e:
        print(f"⚠️ Aviso ao tentar limpar a tabela altas_mes: {e}")

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

    # 5. Insere os novos dados na tabela limpa do Supabase
    try:
        response = supabase.table("altas_mes").insert(registros).execute()
        print("✅ Tabela `altas_mes` atualizada com sucesso no Supabase!")
    except Exception as e:
        print(f"❌ Erro ao inserir altas mensais no Supabase: {e}")
        raise e

if __name__ == "__main__":
    run()