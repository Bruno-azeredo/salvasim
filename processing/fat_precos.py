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
    if pd.isna(valor):
        return 0.0
    
    # Se já for numérico, retorna direto
    if isinstance(valor, (int, float)):
        return float(valor)
    
    val_str = str(valor).strip()
    # Se vier vazio ou string "None"/"nan"
    if not val_str or val_str.lower() in ["none", "nan", "null"]:
        return 0.0
        
    # Remove "R$", espaços, pontos de milhar e troca vírgula decimal por ponto
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

    # 🔍 PRINT DE INSPEÇÃO: Mostra as primeiras colunas e os preços brutos vindos da Bronze
    print("🔎 Amostra de preços brutos vindos da Bronze:")
    if "preco" in df.columns:
        print(df["preco"].head(5))
    else:
        print("⚠️ ATENÇÃO: A coluna 'preco' NÃO foi encontrada na tabela da Bronze! As colunas disponíveis são:", df.columns.tolist())

    # Tratamentos básicos e limpeza de preço
    df["data_extracao"] = pd.to_datetime(df["data_extracao"])
    df["preco"] = df["preco"].apply(limpar_preco)
    
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

    # Remove nulos críticos ou preços zerados
    df_fato = df_fato.dropna(subset=["id_produto", "preco"])
    
    # IMPORTANTE: Se quiser ver se os preços limpos estão maiores que zero, comente temporariamente a linha abaixo se necessário para inspecionar
    # df_fato = df_fato[df_fato["preco"] > 0.0]

    table_id = f"{PROJECT_ID}.{DATASET_SILVER}.{TABELA_SILVER}"
    
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND"
    )

    print(f"☁️ Enviando {len(df_fato)} registros para a tabela Fato no BigQuery...")
    job = client.load_table_from_dataframe(df_fato, table_id, job_config=job_config)
    job.result()

    print(f"✅ Fato de preços atualizada com sucesso no BigQuery!")

if __name__ == "__main__":
    run()