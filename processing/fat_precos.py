import os
import pandas as pd
from google.cloud import bigquery
import warnings

warnings.filterwarnings("ignore")

PROJECT_ID = "economiza-itap"
DATASET_BRONZE = "bronze"
DATASET_SILVER = "silver"
TABELA_SILVER = "s_fat_precos"

def run():
    print("🚀 Iniciando processamento da tabela Fato de Preços (`s_fat_precos`)...")

    client = bigquery.Client(project=PROJECT_ID)
    
    # Lê os dados da Bronze
    query_bronze = f"SELECT * FROM `{PROJECT_ID}.{DATASET_BRONZE}.produtos_atacadao`"
    df = client.query(query_bronze).to_dataframe()

    if df.empty:
        print("❌ Nenhum registro encontrado na Bronze.")
        return

    # Tratamentos básicos
    df["data_extracao"] = pd.to_datetime(df["data_extracao"])
    df["preco"] = pd.to_numeric(df["preco"], errors="coerce").fillna(0.0)
    df["preco_antigo"] = pd.to_numeric(df["preco_antigo"], errors="coerce")
    
    # Importa a função de gerar ID para manter a mesma regra da dimensão
    import hashlib
    def gerar_id(link):
        if not isinstance(link, str) or not link.strip():
            return None
        return hashlib.md5(link.encode()).hexdigest()

    df_fato = pd.DataFrame()
    df_fato["id_produto"] = df["link"].apply(gerar_id)
    df_fato["url_produto"] = df["link"].astype(str)
    df_fato["preco"] = df["preco"]
    df_fato["preco_antigo"] = df["preco_antigo"]
    df_fato["disponivel"] = df.get("disponivel", True)
    df_fato["data_extracao"] = df["data_extracao"]

    # Remove nulos críticos
    df_fato = df_fato.dropna(subset=["id_produto", "preco"])

    # Envio para o BigQuery (Append particionado por data ou Write Truncate se preferir atualizar a carga diária)
    table_id = f"{PROJECT_ID}.{DATASET_SILVER}.{TABELA_SILVER}"
    
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND" # Acumula o histórico na fato
    )

    print(f"☁️ Enviando {len(df_fato)} registros para a tabela Fato no BigQuery...")
    job = client.load_table_from_dataframe(df_fato, table_id, job_config=job_config)
    job.result()

    print(f"✅ Fato de preços atualizada com sucesso no BigQuery!")

if __name__ == "__main__":
    run()