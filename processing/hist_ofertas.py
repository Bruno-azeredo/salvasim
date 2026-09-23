import os
import pandas as pd
from google.cloud import bigquery
from supabase import create_client

# Configuração dos Clientes (BigQuery e Supabase)
# Certifica-te de que tens a variável de ambiente GOOGLE_APPLICATION_CREDENTIALS configurada para o BigQuery
PROJECT_ID = "economiza-itap"
client_bq = bigquery.Client(project=PROJECT_ID)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def consolidar_ofertas_bigquery_para_supabase():
    print("1. A buscar os IDs de ofertas_dia no Supabase...")
    res_ofertas = supabase.table("ofertas_dia").select("*").execute()
    ofertas_df = pd.DataFrame(res_ofertas.data)

    if ofertas_df.empty:
        print("Nenhuma oferta encontrada em ofertas_dia.")
        return

    # Extrair os IDs únicos de produtos em oferta
    ids_ofertas = ofertas_df["id_produto"].dropna().unique().tolist()
    print(f"Total de produtos em oferta detetados: {len(ids_ofertas)}")

    # Formatar os IDs para a query SQL do BigQuery (transformando em string separada por vírgulas)
    # Se os IDs no BigQuery forem string, envolvemo-los em aspas
    ids_formatados = ", ".join([f"'{i}'" for i in ids_ofertas])

    print("2. A consultar a tabela histórica no BigQuery filtrando apenas pelos IDs necessários...")
    # Consulta otimizada ao BigQuery para trazer apenas o histórico dos produtos que estão em oferta hoje
    query = f"""
        SELECT 
            id_produto,
            nome_produto,
            imagem_url,
            categoria,
            url_produto
        FROM `teu-projeto.teu_dataset.g_historico_precos_consolidado`
        WHERE id_produto IN ({ids_formatados})
    """
    
    # Executa a query no BigQuery e converte para DataFrame do Pandas
    gold_df = bq_client.query(query).to_dataframe()

    if gold_df.empty:
        print("Nenhum registo correspondente encontrado na tabela do BigQuery.")
        return

    print("3. A cruzar dados das ofertas com o histórico do BigQuery...")
    # Faz o merge entre as ofertas do dia (preços atuais/descontos) e os dados cadastrais/históricos do BigQuery
    consolidado_df = pd.merge(ofertas_df, gold_df, on="id_produto", how="inner")

    # Prepara os dados para formato dicionário
    dados_para_enviar = consolidado_df.to_dict(orient="records")

    print(f"4. A atualizar a tabela 'vitrine_ofertas' no Supabase com {len(dados_para_enviar)} registos...")
    
    # Envia os dados consolidados para uma tabela final no Supabase (ex: 'vitrine_ofertas')
    supabase.table("vitrine_ofertas").upsert(dados_para_enviar).execute()
    
    print("Sincronização BigQuery -> Supabase concluída com sucesso!")

if __name__ == "__main__":
    consolidar_ofertas_bigquery_para_supabase()