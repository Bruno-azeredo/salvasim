import os
import numpy as np
import pandas as pd
from google.cloud import bigquery
from supabase import create_client

# Configuração dos Clientes (BigQuery e Supabase)
PROJECT_ID = "economiza-itap"
DATASET_ID = "gold"

client_bq = bigquery.Client(project=PROJECT_ID)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def consolidar_ofertas_bigquery_para_supabase():
    print("1. A buscar os IDs de ofertas_dia no Supabase (apenas para filtro)...")
    res_ofertas = supabase.table("ofertas_dia").select("id_produto").execute()
    ofertas_df = pd.DataFrame(res_ofertas.data)

    if ofertas_df.empty:
        print("Nenhuma oferta encontrada em ofertas_dia.")
        return

    # Extrair os IDs únicos de produtos em oferta
    ids_ofertas = ofertas_df["id_produto"].dropna().unique().tolist()
    print(f"Total de produtos em oferta detetados para filtro: {len(ids_ofertas)}")

    # Formatar os IDs para a query SQL do BigQuery
    ids_formatados = ", ".join([f"'{i}'" for i in ids_ofertas])

    print("2. A consultar todos os dados da tabela histórica no BigQuery filtrando pelos IDs...")
    
    query = f"""
        SELECT *
        FROM `{PROJECT_ID}.{DATASET_ID}.g_historico_precos_consolidado`
        WHERE id_produto IN ({ids_formatados})
    """
    
    # Executa a query no BigQuery e converte para DataFrame do Pandas
    gold_df = client_bq.query(query).to_dataframe()

    if gold_df.empty:
        print("Nenhum registo correspondente encontrado na tabela do BigQuery.")
        return

    print(f"3. A preparar {len(gold_df)} registos vindos do BigQuery...")
    
    # Converte colunas de data/timestamp para string (evita erro de serialização JSON)
    for col in gold_df.select_dtypes(include=['datetime64[ns]', 'datetime64', 'datetimetz']).columns:
        gold_df[col] = gold_df[col].dt.strftime('%Y-%m-%d %H:%M:%S')

    # Substitui NaN e infinitos por None (compatível com JSON do Supabase)
    gold_df = gold_df.replace({np.nan: None, float('inf'): None, float('-inf'): None})

    # Converte o DataFrame da Gold diretamente para formato dicionário
    dados_para_enviar = gold_df.to_dict(orient="records")

    print(f"4. A atualizar a tabela 'historico_ofertas' no Supabase...")
    
    # Como o volume pode ser alto (5774 registos), é seguro fazer por lotes se necessário, mas o upsert direto costuma aceitar bem. 
    # Caso queiras enviar em chunks para evitar limites de payload:
    chunk_size = 1000
    for i in range(0, len(dados_para_enviar), chunk_size):
        chunk = dados_para_enviar[i:i + chunk_size]
        supabase.table("historico_ofertas").upsert(chunk).execute()
    
    print("Sincronização BigQuery -> Supabase concluída com sucesso!")

if __name__ == "__main__":
    consolidar_ofertas_bigquery_para_supabase()