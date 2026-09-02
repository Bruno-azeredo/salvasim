import os
import glob
import pandas as pd
from supabase import create_client, Client

SUPABASE_URL = 'https://rceoisrcjtiglzoqsmis.supabase.co' #os.environ.get("SUPABASE_URL")
SUPABASE_KEY = 'sb_publishable_asd19Q9I_glQMetXennqvQ_9Nexpn-O' #os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def inserir_historico_parquet(diretorio_parquet):
    # Busca todos os arquivos .parquet na pasta ou subpastas
    arquivos = glob.glob(os.path.join(diretorio_parquet, "**", "*.parquet"), recursive=True)
    
    if not arquivos:
        print("❌ Nenhum arquivo Parquet encontrado no diretório especificado.")
        return

    for arquivo in arquivos:
        print(f"📂 Processando arquivo: {arquivo}")
        try:
            df = pd.read_parquet(arquivo)
            
            if df.empty:
                print(f"⚠️ O arquivo {arquivo} está vazio. Pulando...")
                continue

            # Opcional: caso o nome do arquivo seja a data (ex: '2026-07-16.parquet') e precise ajustar a coluna
            nome_base = os.path.splitext(os.path.basename(arquivo))[0]
            if "data_extracao" not in df.columns:
                df["data_extracao"] = nome_base

            # Padroniza a data para string no formato aceito pelo banco
            if "data_extracao" in df.columns:
                df["data_extracao"] = pd.to_datetime(df["data_extracao"], errors="coerce").dt.strftime('%Y-%m-%d %H:%M:%S')

            # Substitui valores nulos por None para compatibilidade com o JSON do Supabase
            df = df.where(pd.notnull(df), None)

            registros = df.to_dict(orient="records")

            # Insere em lotes de 500 registros para evitar limites de payload da API
            batch_size = 500
            total_registros = len(registros)
            
            for i in range(0, total_registros, batch_size):
                lote = registros[i:i + batch_size]
                supabase.table("produtos_atacadao").insert(lote).execute()
                print(f"  -> Inseridos {min(i + batch_size, total_registros)}/{total_registros} registros...")

        except Exception as e:
            print(f"❌ Erro ao processar o arquivo {arquivo}: {e}")

    print("🏁 Importação do histórico Parquet concluída com sucesso!")

if __name__ == "__main__":
    # Substitua pelo caminho real da pasta onde estão salvos os arquivos parquet estruturados por data
    caminho_pasta = "D:/Projeto/data-platform-ecommerce/data/raw/atacadao"
    inserir_historico_parquet(caminho_pasta)