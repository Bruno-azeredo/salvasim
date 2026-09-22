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
    if isinstance(valor, (int, float)):
        return float(valor)
    
    val_str = str(valor).strip()
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
    
    # 🔍 Lê apenas os dados do dia atual da Bronze para evitar reprocessar o histórico antigo
    query_bronze = f"""
        SELECT * FROM `{PROJECT_ID}.{DATASET_BRONZE}.produtos_atacadao`
        WHERE DATE(data_extracao) = CURRENT_DATE()
    """
    df = client.query(query_bronze).to_dataframe()

    # Caso a extração de hoje ainda não tenha dados ou a data venha em formato diferente, 
    # podemos pegar a última data disponível na Bronze como fallback:
    if df.empty:
        print("⚠️ Nenhum registro encontrado para hoje na Bronze. Buscando a data mais recente disponível...")
        query_fallback = f"""
            SELECT * FROM `{PROJECT_ID}.{DATASET_BRONZE}.produtos_atacadao`
            WHERE DATE(data_extracao) = (
                SELECT MAX(DATE(data_extracao)) 
                FROM `{PROJECT_ID}.{DATASET_BRONZE}.produtos_atacadao`
            )
        """
        df = client.query(query_fallback).to_dataframe()

    if df.empty:
        print("❌ Nenhum registro encontrado na Bronze.")
        return

    # 🔍 DIAGNÓSTICO DETALHADO NO LOG
    print("🔎 Colunas disponíveis na Bronze:", df.columns.tolist())
    if "preco" in df.columns:
        print("🔎 Amostra dos 5 primeiros valores brutos da coluna 'preco':")
        for idx, val in enumerate(df["preco"].head(5)):
            print(f"   [{idx}] Tipo: {type(val)} | Valor Bruto: repr({repr(val)}) | Limpo: {limpar_preco(val)}")
    else:
        print("❌ ERRO CRÍTICO: A coluna 'preco' NÃO existe na tabela da Bronze!")
        return

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

    # Remove nulos críticos
    df_fato = df_fato.dropna(subset=["id_produto", "preco"])

    # 🛑 EVITA DUPLICIDADE: Remove duplicatas no DataFrame do mesmo dia por id_produto
    df_fato["data_dia"] = df_fato["data_extracao"].dt.date
    df_fato = df_fato.drop_duplicates(subset=["id_produto", "data_dia"], keep="first")
    df_fato = df_fato.drop(columns=["data_dia"])

    table_id = f"{PROJECT_ID}.{DATASET_SILVER}.{TABELA_SILVER}"
    
    # 🧹 Limpeza preventiva: remove registros anteriores do mesmo dia no BigQuery antes do Append
    if not df_fato.empty:
        data_execucao = df_fato["data_extracao"].dt.date.iloc[0]
        delete_query = f"""
            DELETE FROM `{table_id}`
            WHERE DATE(data_extracao) = '{data_execucao}'
        """
        try:
            client.query(delete_query).result()
            print(f"🧹 Registros anteriores da data {data_execucao} limpos no BigQuery.")
        except Exception:
            pass # Ignora se a tabela ainda não existir na primeira carga

    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND"
    )

    print(f"☁️ Enviando {len(df_fato)} registros únicos do dia para a tabela Fato no BigQuery...")
    job = client.load_table_from_dataframe(df_fato, table_id, job_config=job_config)
    job.result()

    print(f"✅ Fato de preços atualizada com sucesso no BigQuery sem duplicatas!")

if __name__ == "__main__":
    run()