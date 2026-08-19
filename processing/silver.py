import glob
import os
from pathlib import Path
import duckdb
import pandas as pd
from supabase import create_client

# =====================================================
# CONFIGURAÇÕES
# =====================================================

RAW_PATH = "data/raw/atacadao/*/data.parquet"

# Caminhos locais caso queira manter backup em parquet
SILVER_PATH = Path("D:/Projeto/monitor-preco/dashboard-monitor-preco/data/silver")
GOLD_PATH = Path("D:/Projeto/monitor-preco/dashboard-monitor-preco/data/gold")

SILVER_PATH.mkdir(parents=True, exist_ok=True)
GOLD_PATH.mkdir(parents=True, exist_ok=True)

# Configuração do Supabase (buscando das variáveis de ambiente / secrets)
SUPABASE_URL = os.getenv("SUPABASE_URL", "SUA_URL_AQUI")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "SUA_KEY_AQUI")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# =====================================================
# BUSCA E VALIDA ARQUIVOS PARQUET
# =====================================================

arquivos = glob.glob(RAW_PATH)

if not arquivos:
    raise Exception("Nenhum arquivo parquet encontrado.")

arquivos_validos = []
print("Validando arquivos parquet...")

for arq in sorted(arquivos):
    try:
        if os.path.getsize(arq) < 3000:
            print(f"Ignorado (arquivo corrompido/pequeno): {arq}")
            continue

        arq_duck = arq.replace("\\", "/")
        duckdb.sql(f"SELECT 1 FROM read_parquet('{arq_duck}') LIMIT 1")
        arquivos_validos.append(arq_duck)

    except Exception as e:
        print(f"Ignorado erro: {arq} - {e}")

print(f"\nArquivos válidos identificados: {len(arquivos_validos)}")


# =====================================================
# CARREGA DADOS (DUCKDB -> PANDAS)
# =====================================================

con = duckdb.connect()

historico = con.execute(
    "SELECT * FROM read_parquet(?)", [arquivos_validos]
).df()

print(f"Registros carregados: {len(historico):,}")


# =====================================================
# LIMPEZA E TRATAMENTO
# =====================================================

historico["data_extracao"] = pd.to_datetime(historico["data_extracao"])

# Limpeza e conversão de preço
historico["preco"] = (
    historico["preco"]
    .astype(str)
    .str.replace("R$", "", regex=False)
    .str.replace("\xa0", "", regex=False)
    .str.replace(" ", "", regex=False)
    .str.replace(".", "", regex=False)
    .str.replace(",", ".", regex=False)
)

historico["preco"] = pd.to_numeric(historico["preco"], errors="coerce")

# Remove registros sem preço e duplicatas no mesmo timestamp
historico = historico[historico["preco"].notna()]
historico = historico.drop_duplicates(subset=["link", "data_extracao"])


# =====================================================
# ORDENAÇÃO E COMPARAÇÃO DE PREÇOS HISTÓRICOS
# =====================================================

historico = historico.sort_values(["link", "data_extracao"])

historico["preco_anterior"] = historico.groupby("link")["preco"].shift()
historico["data_anterior"] = historico.groupby("link")["data_extracao"].shift()

# Trata comparação de preço e variações
historico["mudou_preco"] = (
    (historico["preco"] != historico["preco_anterior"])
    & (historico["preco_anterior"].notna())
)

historico["variacao_pct"] = (
    (historico["preco"] - historico["preco_anterior"]) / historico["preco_anterior"]
) * 100

historico["variacao_pct"] = historico["variacao_pct"].round(2)


# =====================================================
# MÉTRICAS HISTÓRICAS
# =====================================================

metricas = (
    historico.groupby("link")
    .agg(
        menor_preco=("preco", "min"),
        maior_preco=("preco", "max"),
        preco_medio=("preco", "mean"),
        total_dias=("preco", "count"),
        imagem_url=("imagem_url", "first")
    )
    .reset_index()
)

monitor = historico.merge(metricas, on="link", how="left")

monitor["abaixo_media_pct"] = (
    (monitor["preco"] - monitor["preco_medio"]) / monitor["preco_medio"]
) * 100

monitor["abaixo_media_pct"] = monitor["abaixo_media_pct"].round(2)


# =====================================================
# FILTRAR O PREÇO MAIS RECENTE POR PRODUTO (SILVER)
# =====================================================

monitor["data_extracao"] = pd.to_datetime(monitor["data_extracao"])
idx_mais_recente = monitor.groupby("link")["data_extracao"].idxmax()
silver_final = monitor.loc[idx_mais_recente].copy()


# =====================================================
# SNAPSHOT (ÚLTIMA EXTRAÇÃO GERAL POR PRODUTO)
# =====================================================

ultimas_datas = monitor.groupby("link")["data_extracao"].transform("max")
snapshot = monitor[monitor["data_extracao"] == ultimas_datas].copy()

ultima_data_geral = monitor["data_extracao"].max()


# =====================================================
# REGRAS DE NEGÓCIO (ALERTAS, OPORTUNIDADES E RANKING)
# =====================================================

# Alertas com mudança de preço >= 5%
alertas = snapshot[
    (snapshot["mudou_preco"]) & (snapshot["variacao_pct"].abs() >= 5)
].copy()

alertas["tipo"] = alertas["variacao_pct"].apply(
    lambda x: "queda" if x < 0 else "alta"
)

# Oportunidades: preço atual no menor preço histórico
oportunidades = snapshot[snapshot["preco"] == snapshot["menor_preco"]].copy()

# Ranking de Oportunidades
ranking = snapshot.copy()
ranking["score"] = (ranking["variacao_pct"] * -1) + (ranking["abaixo_media_pct"] * -1)
ranking = ranking.sort_values("score", ascending=False).head(100)


# =====================================================
# PERSISTÊNCIA DOS DADOS (LOCAL PARQUET)
# =====================================================

monitor.to_parquet(SILVER_PATH / "monitor.parquet", index=False)
snapshot.to_parquet(GOLD_PATH / "snapshot_atual.parquet", index=False)
alertas.to_parquet(GOLD_PATH / "alertas_diarios.parquet", index=False)
oportunidades.to_parquet(GOLD_PATH / "oportunidades.parquet", index=False)
ranking.to_parquet(GOLD_PATH / "ranking_oportunidades.parquet", index=False)


# =====================================================
# PERSISTÊNCIA DOS DADOS (SUPABASE VIA UPSERT)
# =====================================================

def upload_to_supabase(df, table_name):
    if df.empty:
        print(f"Tabela {table_name} vazia, pulando upload.")
        return
    
    df_clean = df.copy()
    # Converte colunas datetime para string para evitar erros no JSON da API
    for col in df_clean.select_dtypes(include=['datetime64', 'datetime']):
        df_clean[col] = df_clean[col].astype(str)
    
    data_list = df_clean.to_dict(orient="records")
    batch_size = 500
    
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i+batch_size]
        supabase.table(table_name).upsert(batch).execute()
        
    print(f"-> Sucesso ao enviar {len(data_list)} registros para a tabela: {table_name}")

print("\nEnviando dados para o Supabase...")
upload_to_supabase(silver_final, "silver_products")
upload_to_supabase(snapshot, "gold_snapshot")
upload_to_supabase(alertas, "gold_alertas")
upload_to_supabase(oportunidades, "gold_oportunidades")
upload_to_supabase(ranking, "gold_ranking")


# =====================================================
# RESUMO
# =====================================================

print("\n==============================")
print("MONITOR FINALIZADO COM SUCESSO")
print("==============================")
print(f"Produtos únicos na Silver: {silver_final['link'].nunique():,}")
print(f"Registros totais no histórico processado: {len(monitor):,}")
print(f"Última data detectada: {ultima_data_geral}")
print(f"Alertas gerados hoje: {len(alertas):,}")
print(f"Oportunidades ativas: {len(oportunidades):,}")
print(f"Ranking gerado: {len(ranking):,}")
print("==============================")