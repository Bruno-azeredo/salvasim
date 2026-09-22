import os
import pandas as pd
from google.cloud import bigquery
import warnings

warnings.filterwarnings("ignore")

# =========================
# CONFIGURAÇÕES
# =========================
PROJECT_ID = "economiza-itap"
DATASET_SILVER = "silver"
TABELA_SILVER = "s_fat_precos"
DATASET_GOLD = "gold"
TABELA_GOLD = "g_historico_precos_consolidado"

def run():
    print("🚀 Iniciando processamento e consolidação do histórico (Camada Gold)...")

    client = bigquery.Client(project=PROJECT_ID)

    # 1. Garantir que o dataset Gold existe
    dataset_gold_ref = bigquery.Dataset(f"{PROJECT_ID}.{DATASET_GOLD}")
    dataset_gold_ref.location = "US-CENTRAL1"  # Ajuste para a região do seu BigQuery se necessário
    client.create_dataset(dataset_gold_ref, exists_ok=True)

    table_gold_id = f"{PROJECT_ID}.{DATASET_GOLD}.{TABELA_GOLD}"

    # 2. Query SQL para calcular as faixas de histórico diretamente no BigQuery
    # - Até 30 dias: Mantém o dia exato (frequência diária)
    # - De 30 a 120 dias: Agrupa por faixas (30, 45, 60, 75, 90, 105, 120) tirando a média do período
 # 2. Query SQL corrigida para lidar com o histórico diário vs faixas agrupadas
    query_consolidacao = f"""
        WITH historico_com_idade AS (
            SELECT 
                id_produto,
                url_produto,
                preco,
                preco_antigo,
                data_extracao,
                DATE_DIFF(CURRENT_DATE(), DATE(data_extracao), DAY) AS dias_atras
            FROM `{PROJECT_ID}.{DATASET_SILVER}.{TABELA_SILVER}`
            WHERE data_extracao IS NOT NULL
        ),
        -- 1. Parte recente (<= 30 dias): Mantém a granularidade diária exata
        recente AS (
            SELECT 
                id_produto,
                url_produto,
                ROUND(AVG(preco), 2) AS preco,
                ROUND(AVG(preco_antigo), 2) AS preco_antigo,
                data_extracao,
                0 AS faixa_dias
            FROM historico_com_idade
            WHERE dias_atras <= 30
            GROUP BY id_produto, url_produto, data_extracao
        ),
        -- 2. Parte antiga (> 30 e <= 120 dias): Agrupa pelas faixas maiores
        antigo AS (
            SELECT 
                id_produto,
                url_produto,
                ROUND(AVG(preco), 2) AS preco,
                ROUND(AVG(preco_antigo), 2) AS preco_antigo,
                MAX(data_extracao) AS data_extracao,
                CASE 
                    WHEN dias_atras <= 45 THEN 45
                    WHEN dias_atras <= 60 THEN 60
                    WHEN dias_atras <= 75 THEN 75
                    WHEN dias_atras <= 90 THEN 90
                    WHEN dias_atras <= 105 THEN 105
                    ELSE 120
                END AS faixa_dias
            FROM historico_com_idade
            WHERE dias_atras > 30 AND dias_atras <= 120
            GROUP BY id_produto, url_produto, faixa_dias
        )
        SELECT * FROM recente
        UNION ALL
        SELECT * FROM antigo
    """

    print("⚙️ Executando agregação e consolidação no BigQuery...")
    
    # Configuramos para sobrescrever (WRITE_TRUNCATE) a tabela Gold com o consolidado atualizado
    job_config = bigquery.QueryJobConfig(
        destination=table_gold_id,
        write_disposition="WRITE_TRUNCATE"
    )

    query_job = client.query(query_consolidacao, job_config=job_config)
    query_job.result()  # Aguarda a conclusão da query

    # Consulta para verificar quantos registros foram gerados
    count_query = f"SELECT COUNT(*) as total FROM `{table_gold_id}`"
    total_rows = client.query(count_query).to_dataframe()["total"].iloc[0]

    print(f"✅ Sucesso! Tabela `{TABELA_GOLD}` atualizada com {total_rows} registros consolidados.")

if __name__ == "__main__":
    run()