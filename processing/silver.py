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
TABELA_SILVER = "s_inge_prod_shop"

# =========================
# CONFIG DE NEGÓCIO
# =========================
MARGEM_DESEJADA = 0.65
COMISSAO = 0.18
CUSTO_EMBALAGEM = 2.00

DESCRICAO_PADRAO = (
    "Produto original de alta qualidade, enviado com segurança e rapidez. "
    "Todos os itens são novos, bem embalados e prontos para entrega imediata."
)

# =========================
# CLASSIFICAÇÃO FISCAL
# =========================
CLASSIFICACAO_FISCAL = {
    # 🧃 BEBIDAS
    "aguas": {"NCM": "22011000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "cervejas": {"NCM": "22030000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "champanhes-espumantes-e-sidras": {"NCM": "22041000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "chas-prontos": {"NCM": "22029900", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "coqueteis": {"NCM": "22089000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "destilados": {"NCM": "22089000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "energeticos-e-isotonicos": {"NCM": "22021000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "refrigerantes": {"NCM": "22021000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "sucos-e-refrescos": {"NCM": "20099000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "cafes-chas-e-achocolatados": {"NCM": "09012100", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    # 🍫 ALIMENTOS
    "acucar-e-adocantes": {"NCM": "17019900", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "azeites-oleos-e-vinagres": {"NCM": "15091000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "biscoitos": {"NCM": "19053100", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "bomboniere": {"NCM": "17049010", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "chocolates": {"NCM": "18069000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "confeitaria": {"NCM": "19059090", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "conservas-e-enlatados": {"NCM": "20019000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "doces": {"NCM": "17049010", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "farinhas": {"NCM": "11010010", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "KG"},
    "graos": {"NCM": "10063021", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "KG"},
    "massas-e-molhos": {"NCM": "19021100", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "salgadinhos-e-snacks": {"NCM": "19059090", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "sopas-e-cremes": {"NCM": "21041011", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "temperos-e-condimentos": {"NCM": "25010020", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "aveias-e-cereais": {"NCM": "19041000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "KG"},
    "leites": {"NCM": "04012010", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "L"},
    "mel-geleias-e-pates": {"NCM": "04090000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "paes-e-torradas": {"NCM": "19059090", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    # 🧽 LIMPEZA
    "limpeza-de-banheiro": {"NCM": "34022000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "limpeza-de-casa": {"NCM": "34029000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "limpeza-de-cozinha": {"NCM": "34022000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "limpeza-de-roupas": {"NCM": "34022000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    # 🧴 HIGIENE E CUIDADOS PESSOAIS
    "bebes": {"NCM": "96190000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "cabelo": {"NCM": "33059000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "corpo": {"NCM": "33049990", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "cremes-de-barbear-e-barbeadores": {"NCM": "82121000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "desodorantes": {"NCM": "33072010", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "higiene-bucal": {"NCM": "33069000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "higiene-intima": {"NCM": "96190000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "papel-higienico": {"NCM": "48181000", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "sabonetes": {"NCM": "34011190", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"},
    "saude": {"NCM": "30049099", "CFOP_MESMO": "5102", "CFOP_OUTRO": "6102", "Origem": "0", "CSOSN": "102", "Unidade": "UN"}
}

# =========================
# FUNÇÕES AUXILIARES
# =========================
def limpar_preco(preco):
    if pd.isna(preco):
        return 0.0
    preco_str = str(preco).replace("R$", "").replace(",", ".")
    preco_str = re.sub(r"[^\d\.]", "", preco_str)
    try:
        return float(preco_str)
    except:
        return 0.0

def normalizar_nome(nome):
    if not isinstance(nome, str):
        return ""
    nome = nome.lower()
    nome = re.sub(r'[^a-z0-9 ]', '', nome)
    return nome.strip()

def calcular_preco_venda(custo):
    if custo <= 0:
        return 0
    custo_total = custo + CUSTO_EMBALAGEM
    taxa = 4.50
    preco = (custo_total * (1 + MARGEM_DESEJADA) + taxa) / (1 - COMISSAO)
    if preco <= 8:
        taxa = 2.00
        preco = (custo_total * (1 + MARGEM_DESEJADA) + taxa) / (1 - COMISSAO)
    return round(preco, 2)

def extrair_peso(nome):
    try:
        if not nome:
            return None
        nome = nome.lower()
        match = re.search(r'(\d+[.,]?\d*)\s?(kg|g|ml|l)', nome)
        if not match:
            return None
        valor = match.group(1).replace(",", ".")
        unidade = match.group(2)
        if valor == ".":
            return None
        valor = float(valor)
        if unidade == "kg":
            return valor
        elif unidade == "g":
            return valor / 1000
        elif unidade == "l":
            return valor
        elif unidade == "ml":
            return valor / 1000
        return None
    except:
        return None

def gerar_id(nome):
    return hashlib.md5(nome.encode()).hexdigest()

def preencher_classificacao(subcategoria):
    info = CLASSIFICACAO_FISCAL.get(str(subcategoria).lower(), None)
    if info:
        return pd.Series(info)
    return pd.Series({
        "NCM": "00000000",
        "CFOP_MESMO": "5102",
        "CFOP_OUTRO": "6102",
        "Unidade": "UN"
    })

# =========================
# PIPELINE PRINCIPAL
# =========================
def run():
    print("🚀 Iniciando processamento Silver via BigQuery...")

    # 1. Carregar dados RAW direto da tabela Bronze no BigQuery
    client = bigquery.Client(project=PROJECT_ID)
    query_bronze = f"SELECT * FROM `{PROJECT_ID}.{DATASET_BRONZE}.produtos_atacadao`"
    
    df = client.query(query_bronze).to_dataframe()

    if df.empty:
        print("❌ Nenhum registro encontrado na tabela Bronze do BigQuery.")
        return

    print(f"📊 Registros RAW obtidos: {len(df)}")

    # 2. Tratamento inicial
    df["preco_custo"] = df["preco"].apply(limpar_preco)
    df["nome_normalizado"] = df["nome"].apply(normalizar_nome)
    df["data_extracao"] = pd.to_datetime(df["data_extracao"])
    df["imagem_url"] = df["imagem_url"].fillna("")

    df["id"] = df["nome_normalizado"].apply(gerar_id)

    df["descricao"] = None
    df["vender_como_kit"] = False
    df["quantidade_kit"] = 1

    df["vender_como_kit"] = df["vender_como_kit"].astype(bool)
    df["quantidade_kit"] = df["quantidade_kit"].astype(int)

    # 4. Menor preço histórico por produto considerando toda a base Bronze
    df_historico = df.copy()
    menor = (
        df_historico
        .groupby("nome_normalizado")["preco_custo"]
        .min()
        .reset_index()
    )
    menor.rename(columns={"preco_custo": "MENOR_PRECO"}, inplace=True)

    # 5. Isolar apenas a última extração global
    ultima_data = df_historico["data_extracao"].max()
    print(f"📅 Última extração encontrada: {ultima_data}")

    df = df_historico[df_historico["data_extracao"] == ultima_data].copy()
    print(f"📦 Produtos na última extração: {len(df)}")

    # 6. Adicionar menor preço
    df = df.merge(menor, on="nome_normalizado", how="left")

    # 7. Enriquecimento e Regras de Kits
    df["preco_custo"] = df["preco_custo"] * df["quantidade_kit"]
    df["nome_original"] = df["nome"]

    df["nome_anuncio"] = df.apply(
        lambda row: f"KIT COM {row['quantidade_kit']} UNIDADES - {row['nome_original']}"
        if row["vender_como_kit"] else row["nome_original"],
        axis=1
    )

    df["preco_venda"] = df["preco_custo"].apply(calcular_preco_venda)
    df["peso"] = df["nome_original"].apply(extrair_peso)
    df["peso"] = df["peso"] * df["quantidade_kit"]
    
    df["descricao"] = df["descricao"].fillna(DESCRICAO_PADRAO)
    df["descricao"] = df.apply(
        lambda row: f"KIT COM {row['quantidade_kit']} UNIDADES.\n\n{row['descricao']}"
        if row["vender_como_kit"] else row["descricao"],
        axis=1
    )

    classificacao = df["subcategoria"].apply(preencher_classificacao)
    df = pd.concat([df, classificacao], axis=1)

    # 8. Montagem do DataFrame Final
    df_final = pd.DataFrame()
    df_final["id"] = df["nome_normalizado"].apply(gerar_id)
    df_final["nome_original"] = df["nome_original"]
    df_final["nome_produto"] = df["nome_anuncio"]
    df_final["descricao"] = df["descricao"]
    df_final["preco_custo"] = df["preco_custo"]
    df_final["preco_venda"] = df["preco_venda"]
    df_final["peso"] = df["peso"]
    df_final["categoria"] = df.get("categoria")
    df_final["subcategoria"] = df.get("subcategoria")
    df_final["link"] = df["link"]
    df_final["imagem"] = df["imagem_url"]
    df_final["ncm"] = df["NCM"]
    df_final["cfop_mesmo"] = df["CFOP_MESMO"]
    df_final["cfop_outro"] = df["CFOP_OUTRO"]
    df_final["unidade"] = df["Unidade"]
    df_final["data_extracao"] = df["data_extracao"].astype(str)
    df_final["data_processamento"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    df_final["menor_preco"] = df["MENOR_PRECO"]
    df_final["vender_como_kit"] = df["vender_como_kit"]
    df_final["quantidade_kit"] = df["quantidade_kit"]

    df_final = df_final.drop_duplicates(subset=["id"])

    # 9. Envio para a tabela Silver no BigQuery (`s_inge_prod_shop`)
    print(f"☁️ Enviando dados tratados para a tabela `{DATASET_SILVER}.{TABELA_SILVER}` no BigQuery...")
    
    table_id = f"{PROJECT_ID}.{DATASET_SILVER}.{TABELA_SILVER}"
    
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE" # Substitui os dados anteriores mantendo sempre a última extração limpa
    )

    job = client.load_table_from_dataframe(df_final, table_id, job_config=job_config)
    job.result()

    print(f"✅ Sucesso! {len(df_final)} registros atualizados na tabela `{TABELA_SILVER}` do BigQuery.")

if __name__ == "__main__":
    run()