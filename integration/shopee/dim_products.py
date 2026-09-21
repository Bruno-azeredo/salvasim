import os
import re
from datetime import datetime
import hashlib
import pandas as pd
from google.cloud import bigquery
from supabase import create_client, Client
import warnings

warnings.filterwarnings("ignore")

# =========================
# CONFIGURAÇÕES DO GCP E SUPABASE
# =========================
PROJECT_ID = "economiza-itap"
DATASET_BRONZE = "bronze"
DATASET_SILVER = "silver"
TABELA_SILVER = "s_dim_prod"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# =========================
# FUNÇÕES AUXILIARES
# =========================
def gerar_id(link):
    if not isinstance(link, str) or not link.strip():
        return None
    return hashlib.md5(link.encode()).hexdigest()

def fetch_all_from_supabase(supabase_client, table_name):
    """Busca todos os registros de uma tabela do Supabase com paginação"""
    all_data = []
    page_size = 1000
    start = 0
    while True:
        response = supabase_client.table(table_name).select("*").range(start, start + page_size - 1).execute()
        if not response.data:
            break
        all_data.extend(response.data)
        if len(response.data) < page_size:
            break
        start += page_size
    return pd.DataFrame(all_data)

# =========================
# PIPELINE PRINCIPAL
# =========================
def run():
    print("🚀 Iniciando processamento da dimensão de produtos (BigQuery)...")

    # 1. Carregar dados RAW direto da tabela Bronze no BigQuery
    client = bigquery.Client(project=PROJECT_ID)
    query_bronze = f"SELECT * FROM `{PROJECT_ID}.{DATASET_BRONZE}.produtos_atacadao`"
    
    df = client.query(query_bronze).to_dataframe()

    if df.empty:
        print("❌ Nenhum registro encontrado na tabela Bronze do BigQuery.")
        return

    print(f"📊 Registros RAW obtidos da Bronze: {len(df)}")

    # 2. Tratamentos iniciais
    df["data_extracao"] = pd.to_datetime(df["data_extracao"])
    df["imagem_url"] = df["imagem_url"].fillna("")
    df["link"] = df["link"].fillna("")
    df["nome"] = df["nome"].fillna("")

    # Remover linhas sem link válido
    df = df[df["link"] != ""].copy()

    # 3. Considerar sempre a última aparição do produto (por link)
    print("🔍 Filtrando a última aparição de cada produto...")
    df = df.sort_values(by="data_extracao", ascending=False)
    df_recente = df.drop_duplicates(subset=["link"], keep="first").copy()
    print(f"📦 Produtos distintos encontrados: {len(df_recente)}")

    # 4. Montagem do DataFrame Final para a Dimensão
    df_final = pd.DataFrame()
    df_final["id_produto"] = df_recente["link"].apply(gerar_id)
    df_final["nome_produto"] = df_recente["nome"].astype(str)
    df_final["imagem_url"] = df_recente["imagem_url"].astype(str)
    df_final["url_produto"] = df_recente["link"].astype(str)
    
    # Forçar explicitamente a coluna descricao como object/string contendo None
    df_final["descricao"] = [None] * len(df_final)
    
    df_final["categoria"] = df_recente.get("categoria", "").astype(str)
    df_final["subcategoria"] = df_recente.get("subcategoria", "").astype(str)
    df_final["created_at"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    df_final = df_final.drop_duplicates(subset=["id_produto"])

    # 5. Envio para a tabela Silver no BigQuery via SQL puro (Evita qualquer LoadJobConfig legado)
    print(f"☁️ Enviando dimensão tratada para a tabela `{DATASET_SILVER}.{TABELA_SILVER}` no BigQuery via SQL...")
    
    table_id = f"{PROJECT_ID}.{DATASET_SILVER}.{TABELA_SILVER}"
    
    # Recria a tabela limpa
    client.query(f"DROP TABLE IF EXISTS `{table_id}`;").result()
    
    create_table_sql = f"""
        CREATE TABLE `{table_id}` (
            id_produto STRING,
            nome_produto STRING,
            imagem_url STRING,
            url_produto STRING,
            descricao STRING,
            categoria STRING,
            subcategoria STRING,
            created_at TIMESTAMP
        );
    """
    client.query(create_table_sql).result()

    # Insere os dados em lotes via SQL para evitar estouro de tamanho de query
    batch_size = 500
    total_rows = len(df_final)
    
    for i in range(0, total_rows, batch_size):
        batch_df = df_final.iloc[i:i + batch_size]
        values_list = []
        
        for _, row in batch_df.iterrows():
            # Tratamento seguro de strings para evitar quebras de SQL
            id_p = str(row["id_produto"]) if pd.notnull(row["id_produto"]) else ""
            nome = str(row["nome_produto"]).replace("'", "\\'") if pd.notnull(row["nome_produto"]) else ""
            img = str(row["imagem_url"]).replace("'", "\\'") if pd.notnull(row["imagem_url"]) else ""
            url = str(row["url_produto"]).replace("'", "\\'") if pd.notnull(row["url_produto"]) else ""
            cat = str(row["categoria"]).replace("'", "\\'") if pd.notnull(row["categoria"]) else ""
            subcat = str(row["subcategoria"]).replace("'", "\\'") if pd.notnull(row["subcategoria"]) else ""
            c_at = str(row["created_at"])
            
            val_str = f"('{id_p}', '{nome}', '{img}', '{url}', NULL, '{cat}', '{subcat}', TIMESTAMP('{c_at}'))"
            values_list.append(val_str)
            
        if values_list:
            insert_sql = f"""
                INSERT INTO `{table_id}` 
                (id_produto, nome_produto, imagem_url, url_produto, descricao, categoria, subcategoria, created_at)
                VALUES {', '.join(values_list)};
            """
            client.query(insert_sql).result()

    print(f"✅ Sucesso! {total_rows} produtos inseridos na tabela `{TABELA_SILVER}` via SQL.")
    # =========================
    # 6. SINCRONIZAÇÃO COM O SUPABASE
    # =========================
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ Credenciais do Supabase não encontradas. Sincronização ignorada.")
        return

    print("🔄 Iniciando sincronização com o Supabase...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Prepara os registros convertendo para dicionários limpos
    df_sync = df_final.where(pd.notnull(df_final), None)
    registros = df_sync.to_dict(orient="records")

    dados_limpos = []
    for reg in registros:
        clean_reg = {}
        for k, v in reg.items():
            if pd.isna(v):
                clean_reg[k] = None
            elif hasattr(v, "item"):
                clean_reg[k] = v.item()
            else:
                clean_reg[k] = v
        dados_limpos.append(clean_reg)

    # Envio em lotes (Upsert baseado em url_produto ou id_produto)
    batch_size = 500
    for i in range(0, len(dados_limpos), batch_size):
        batch = dados_limpos[i:i + batch_size]
        supabase.table("produtos").upsert(batch, on_conflict="url_produto").execute()

    print(f"✅ Sincronização com o Supabase concluída com sucesso! ({len(dados_limpos)} registos)")

if __name__ == "__main__":
    run()