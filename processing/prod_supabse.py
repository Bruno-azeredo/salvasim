import os
import pandas as pd
from google.cloud import bigquery
from supabase import create_client, Client
import warnings

warnings.filterwarnings("ignore")

# =========================
# CONFIGURAÇÕES
# =========================
PROJECT_ID = "economiza-itap"
DATASET_SILVER = "silver"
TABELA_SILVER = "s_dim_prod"

# Credenciais do Supabase (devem vir de variáveis de ambiente no GitHub Actions)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def run():
    print("🚀 Iniciando sincronização da Silver (BigQuery) para o Supabase...")

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Erro: As variáveis de ambiente SUPABASE_URL e SUPABASE_KEY não estão configuradas.")
        return

    # 1. Ler a tabela s_dim_prod do BigQuery
    client_bq = bigquery.Client(project=PROJECT_ID)
    query = f"SELECT * FROM `{PROJECT_ID}.{DATASET_SILVER}.{TABELA_SILVER}`"
    
    df = client_bq.query(query).to_dataframe()

    if df.empty:
        print("⚠️ Nenhum produto encontrado na tabela s_dim_prod do BigQuery.")
        return

    print(f"📊 {len(df)} produtos obtidos do BigQuery. Conectando ao Supabase...")

    # 2. Conectar ao Supabase
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Converter o DataFrame para dicionário para envio em lote (batch upsert)
    # Substituímos valores NaN por None para o PostgreSQL aceitar como NULL
    df = df.where(pd.notnull(df), None)
    
    # Garantir que as colunas de data/uuid sejam tratadas como string/json compatível
    registros = df.to_dict(orient="records")

    # 3. Enviar em lotes para o Supabase (Upsert baseado em url_produto ou id_produto)
    print("☁️ Enviando dados para o Supabase...")
    
    tamanho_lote = 500
    for i in range(0, len(registros), tamanho_lote):
        lote = registros[i:i + tamanho_lote]
        
        response = supabase.table("produtos").upsert(
            lote, 
            on_conflict="url_produto" # Se o link já existir, atualiza as informações
        ).execute()
        
        print(f"Lote {i // tamanho_lote + 1} enviado com sucesso.")

    print(f"✅ Sincronização concluída! {len(registros)} produtos atualizados no Supabase.")

if __name__ == "__main__":
    run()