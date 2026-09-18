import os
import io
from datetime import datetime
import pandas as pd
from supabase import create_client
from google.cloud import storage

# =========================
# CONFIGURAÇÕES
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL", "SUA_SUPABASE_URL_AQUI")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "SUA_SUPABASE_KEY_AQUI")

BUCKET_NAME = "econ-itap"  # Nome do seu bucket
DESTINO_CAMINHO = "atacadao"

def exportar_supabase_particionado():
    print("🔌 Conectando ao Supabase...")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    print("📥 Buscando dados da tabela `produtos_atacadao` com paginação...")
    
    todos_dados = []
    chunk_size = 1000
    start = 0
    
    while True:
        end = start + chunk_size - 1
        response = supabase.table("produtos_atacadao").select("*").range(start, end).execute()
        
        dados_chunk = response.data
        if not dados_chunk:
            break
            
        todos_dados.extend(dados_chunk)
        print(f"📦 Baixados registros de {start} até {start + len(dados_chunk) - 1}...")
        
        if len(dados_chunk) < chunk_size:
            break
            
        start += chunk_size

    if not todos_dados:
        print("❌ Nenhum dado encontrado na tabela do Supabase.")
        return

    df = pd.DataFrame(todos_dados)
    print(f"📊 Total de registros obtidos: {len(df)}")

    if "data_extracao" not in df.columns:
        print("❌ A coluna 'data_extracao' não foi encontrada na tabela.")
        return

    # Normaliza a data para formato YYYY-MM-DD
    df["data_extracao_str"] = pd.to_datetime(df["data_extracao"]).dt.strftime("%Y-%m-%d")

    # Obtém a lista de datas distintas
    datas_distintas = df["data_extracao_str"].dropna().unique()
    
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)

    print(f"🔄 Processando e enviando arquivos particionados mantendo o padrão...")

    for data_str in datas_distintas:
        df_dia = df[df["data_extracao_str"] == data_str].copy()
        df_dia = df_dia.drop(columns=["data_extracao_str"])

        # Mantém o padrão de nome do arquivo (ex: historico_2026-09-18.parquet) dentro da pasta da data
        nome_arquivo = f"historico_{data_str}.parquet"
        caminho_completo = f"{DESTINO_CAMINHO}/data_extracao={data_str}/{nome_arquivo}"

        # Converte para Parquet em memória
        buffer = io.BytesIO()
        df_dia.to_parquet(buffer, index=False, engine="pyarrow")
        buffer.seek(0)

        print(f"☁️ Enviando {len(df_dia)} registros para gs://{BUCKET_NAME}/{caminho_completo}...")
        blob = bucket.blob(caminho_completo)
        blob.upload_from_file(buffer, content_type="application/octet-stream")

    print("✅ Exportação concluída com sucesso!")

if __name__ == "__main__":
    exportar_supabase_particionado()