import os
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
    
    # Trazemos todas as colunas da tabela Gold do BigQuery para os produtos filtrados
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
    
    # Converte o DataFrame da Gold diretamente para formato dicionário
    dados_para_enviar = gold_df.to_dict(orient="records")

    print(f"4. A atualizar a tabela 'historico_ofertas' no Supabase...")
    
    # Envia os dados consolidados da Gold para a tabela final no Supabase
    supabase.table("historico_ofertas").upsert(dados_para_enviar).execute()
    
    print("Sincronização BigQuery -> Supabase concluída com sucesso!")

if __name__ == "__main__":
    consolidar_ofertas_bigquery_para_supabase()