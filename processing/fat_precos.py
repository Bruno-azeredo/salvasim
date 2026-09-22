import os
import pandas as pd
from google.cloud import bigquery
import hashlib
import warnings

warnings.filterwarnings("ignore")

PROJECT_ID = "economiza-itap"
DATASET_BRONZE = "bronze"
DATASET_SILVER = "silver"
TABELA_SILVER = "s_fat_precos"

def limpar_preco(valor):
    """Remove símbolos de moeda, trata pontos de milhar e converte vírgula decimal."""
    if pd.isna(valor):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    
    val_str = str(valor).strip()
    # Remove "R$", espaços, pontos de milhar e troca vírgula por ponto
    val_str = val_str.replace("R$", "").replace("r$", "").strip()
    val_str = val_str.replace(".", "").replace(",", ".")
    
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def gerar_id(link):
    if not isinstance(link, str) or not link.strip():
        return None
    return hashlib.md5(link.encode()).hexdigest()

def run():
    print("🚀 Iniciando processamento da tabela Fato de Preços (`s_fat_precos`)...")

    client = bigquery.Client(project=PROJECT_ID)
    
    # Lê os dados da Bronze
    query_bronze = f"SELECT * FROM `{PROJECT_ID}.{DATASET_BRONZE}.produtos_atacadao`"
    df = client.query(query_bronze).to_dataframe()

    if df.empty:
        print("❌ Nenhum registro encontrado na Bronze.")
        return

    # Tratamentos básicos e limpeza de preço
    df["data_extracao"] = pd.to_datetime(df["data_extracao"])
    df["preco"] = df["preco"].apply(limpar_preco)
    
    # Tratamento seguro para 'preco_antigo' caso ela exista no DataFrame da Bronze
    if "preco_antigo" in df.columns:
        df["preco_antigo"] = df["preco_antigo"].apply(limpar_preco)
    else:
        df["preco_antigo"] = None

    df_fato = pd.DataFrame()
    df_fato["id_produto"] = df["link"].apply(gerar_id)
    df_fato["url_produto"] = df["link"].astype(str)
    df_fato["preco"] = df["preco"]
    df_fato["preco_antigo"] = df["preco_antigo"]
    df_fato["disponivel"] = df.get("disponivel", True)
    df_fato["data_extracao"] = df["data_extracao"]

    # Remove nulos críticos onde o preço zerou ou o ID é inválido
    df_fato = df_fato.dropna(subset=["id_produto", "preco"])
    df_fato = df_fato[df_fato["preco"] > 0.0]

    # Envio para o BigQuery (Append acumulando o histórico)
    table_id = f"{PROJECT_ID}.{DATASET_SILVER}.{TABELA_SILVER}"
    
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND"
    )

    print(f"☁️ Enviando {len(df_fato)} registros limpos para a tabela Fato no BigQuery...")
    job = client.load_table_from_dataframe(df_fato, table_id, job_config=job_config)
    job.result()

    print(f"✅ Fato de preços atualizada com sucesso no BigQuery!")

if __name__ == "__main__":
    run()