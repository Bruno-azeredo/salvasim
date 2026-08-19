import pandas as pd
import re
from datetime import datetime
import hashlib
import os
from supabase import create_client

# =========================
# CONFIG
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
    "cafes-chas-e-achocolatados": {"NCM": "09012100","CFOP_MESMO": "5102","CFOP_OUTRO": "6102","Origem": "0","CSOSN": "102","Unidade": "UN"},
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
# FUNÇÕES
# =========================

def limpar_preco(preco):
    preco = str(preco).replace("R$", "").replace(",", ".")
    preco = re.sub(r"[^\d\.]", "", preco)
    return float(preco) if preco else 0.0

def normalizar_nome(nome):
    if not nome:
        return ""
    nome = str(nome).lower()
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
# PIPELINE
# =========================

def run():
    print("🚀 Iniciando processamento via Supabase...")

    url_db = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url_db or not key:
        print("❌ Credenciais do Supabase não encontradas nas variáveis de ambiente.")
        return

    supabase = create_client(url_db, key)

    # 📥 Puxa os dados direto do Supabase
    response = supabase.table("produtos_atacadao").select("*").execute()
    dados = response.data

    if not dados:
        print("❌ Nenhum dado encontrado na tabela do Supabase")
        return

    df = pd.DataFrame(dados)
    print(f"📊 Registros obtidos do Supabase: {len(df)}")

    # =========================
    # TRATAMENTO
    # =========================

    df["preco_custo"] = df["preco"].apply(limpar_preco)
    df["nome_normalizado"] = df["nome"].apply(normalizar_nome)
    df["data_extracao"] = pd.to_datetime(df["data_extracao"])
    df["imagem_url"] = df["imagem_url"].fillna("")

    # =========================
    # CARREGAR DIM E MERGE
    # =========================

    dim_path = "data/dim/products.parquet"
    if os.path.exists(dim_path):
        df_dim = pd.read_parquet(dim_path)
        df_dim["nome_normalizado"] = df_dim["nome_produto"].apply(normalizar_nome)

        df = df.merge(
            df_dim[["nome_normalizado", "descricao", "vender_como_kit", "quantidade_kit"]],
            on="nome_normalizado",
            how="left"
        )
        print("🔗 Merge com DIM realizado")
    else:
        print("⚠️ Arquivo de dimensão não encontrado. Prosseguindo sem ele.")
        df["descricao"] = None
        df["vender_como_kit"] = False
        df["quantidade_kit"] = 1

    df["vender_como_kit"] = df["vender_como_kit"].fillna(False)
    df["quantidade_kit"] = df["quantidade_kit"].fillna(1).astype(int)

    # =========================
    # MENOR PREÇO HISTÓRICO
    # =========================

    df_historico = df.copy()
    menor = (
        df_historico
        .groupby("nome_normalizado")["preco_custo"]
        .min()
        .reset_index()
    )
    menor.rename(columns={"preco_custo": "MENOR_PRECO"}, inplace=True)

    # =========================
    # SOMENTE ÚLTIMA EXTRAÇÃO
    # =========================

    ultima_data = df_historico["data_extracao"].max()
    print(f"📅 Última extração encontrada: {ultima_data}")

    df = df_historico[df_historico["data_extracao"] == ultima_data].copy()
    print(f"📦 Produtos na última extração: {len(df)}")

    # =========================
    # ADICIONAR MENOR PREÇO
    # =========================

    df = df.merge(menor, on="nome_normalizado", how="left")

    # =========================
    # ENRIQUECIMENTO E KITS
    # =========================

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

    # =========================
    # FINAL
    # =========================

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
    df_final["data_extracao"] = df["data_extracao"]
    df_final["data_processamento"] = datetime.now()
    df_final["menor_preco"] = df["MENOR_PRECO"]
    df_final["vender_como_kit"] = df["vender_como_kit"]
    df_final["quantidade_kit"] = df["quantidade_kit"]

    # Salva o arquivo final processado (ideal para o Streamlit ler direto)
    os.makedirs("data", exist_ok=True)
    df_final.to_parquet("data/silver.parquet", index=False)

    hoje = datetime.today().strftime('%Y-%m-%d')
    path = f"data/silver/data={hoje}"
    os.makedirs(path, exist_ok=True)
    df_final.to_parquet(f"{path}/part-000.parquet", index=False)
    
    print("✅ Processamento concluído e arquivos Parquet gerados com sucesso!")

if __name__ == "__main__":
    run()