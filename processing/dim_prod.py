import os
import re
from datetime import datetime
import hashlib
import pandas as pd
from google.cloud import bigquery
import warnings

warnings.filterwarnings("ignore")

# =========================
# CONFIGURAÇÕES DO GCP
# =========================
PROJECT_ID = "economiza-itap"
DATASET_BRONZE = "bronze"
DATASET_SILVER = "silver"
TABELA_SILVER = "s_dim_prod"

# =========================
# FUNÇÕES AUXILIARES
# =========================
def normalizar_nome(nome):
    if not isinstance(nome, str):
        return ""
    nome = nome.lower()
    nome = re.sub(r'[^a-z0-9 ]', '', nome)
    return nome.strip()

def gerar_id(link):
    if not isinstance(link, str) or not link.strip():
        return None
    return hashlib.md5(link.encode()).hexdigest()

def identificar_cesta_basica(nome):
    if not isinstance(nome, str):
        return False
    
    n = nome.lower()
    
    # Leite Longa Vida 1L Integral (exceto Zero)
    if 'leite' in n and '1l' in n and 'integral' in n and 'zero' not in n:
        return True
    
    # Arroz 5kg
    if 'arroz' in n and '5kg' in n:
        return True
        
    # Feijão 1kg Carioca
    if 'feijão' in n and '1kg' in n and 'carioca' in n:
        return True
        
    # Açúcar 1kg Refinado
    if 'açúcar' in n and '1kg' in n and 'refinado' in n:
        return True
        
    # Café 500g
    if 'café' in n and '500g' in n:
        return True
        
    # Óleo 900ml Soja
    if 'óleo' in n and '900' in n and 'soja' in n:
        return True
        
    # Macarrão 500g Espaguete
    if 'macarrão' in n and '500' in n and 'espaguete' in n:
        return True
        
    # Farinha de Trigo 1kg Tipo 1
    if 'farinha de trigo' in n and '1kg' in n and 'tipo 1' in n:
        return True
        
    # Fubá 500g
    if 'fubá' in n and '500' in n:
        return True
        
    # Sal 1kg Refinado
    if 'sal' in n and '1kg' in n and 'refinado' in n:
        return True
        
    return False

# =========================
# PIPELINE PRINCIPAL
# =========================
def run():
    print("🚀 Iniciando processamento da dimensão de produtos (s_dim_prod)...")

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

    # Remover linhas sem link válido para servir de chave única
    df = df[df["link"] != ""].copy()

    # 3. Considerar sempre a última aparição do produto (por link)
    print("🔍 Filtrando a última aparição de cada produto...")
    df = df.sort_values(by="data_extracao", ascending=False)
    df_recente = df.drop_duplicates(subset=["link"], keep="first").copy()
    print(f"📦 Produtos distintos encontrados: {len(df_recente)}")

    # 4. Montagem do DataFrame Final para a Dimensão
    df_final = pd.DataFrame()
    df_final["id_produto"] = df_recente["link"].apply(gerar_id)
    df_final["nome_produto"] = df_recente["nome"]
    df_final["imagem_url"] = df_recente["imagem_url"]
    df_final["url_produto"] = df_recente["link"]
    
    # Garantir explicitamente que a coluna descricao seja do tipo object/string para o BigQuery
    df_final["descricao"] = pd.Series([None] * len(df_final), dtype="string")
    
    df_final["categoria"] = df_recente.get("categoria", "")
    df_final["subcategoria"] = df_recente.get("subcategoria", "")
    
    # Aplicação da regra de Cesta Básica
    print("🛒 Classificando produtos de Cesta Básica...")
    df_final["is_cesta_basica"] = df_recente["nome"].apply(identificar_cesta_basica)

    df_final["created_at"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Garantir unicidade pelo ID gerado
    df_final = df_final.drop_duplicates(subset=["id_produto"])

    # 5. Envio para a tabela Silver no BigQuery (`s_dim_prod`)
    print(f"☁️ Enviando dimensão tratada para a tabela `{DATASET_SILVER}.{TABELA_SILVER}` no BigQuery...")
    
    table_id = f"{PROJECT_ID}.{DATASET_SILVER}.{TABELA_SILVER}"
    
    # Configuração de carga para o BigQuery
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE" # Sobrescreve a tabela com os produtos atualizados
    )

    job = client.load_table_from_dataframe(df_final, table_id, job_config=job_config)
    job.result()

    print(f"✅ Sucesso! {len(df_final)} produtos atualizados na tabela `{TABELA_SILVER}` do BigQuery.")

if __name__ == "__main__":
    run()