import pandas as pd
import os
from datetime import datetime

# =========================
# REGRAS DE KIT
# =========================

def definir_kit(preco):
    if preco < 10:
        return pd.Series({
            "vender_como_kit": True,
            "quantidade_kit": 4
        })

    elif preco < 20:
        return pd.Series({
            "vender_como_kit": True,
            "quantidade_kit": 2
        })

    return pd.Series({
        "vender_como_kit": False,
        "quantidade_kit": 1
    })

# =========================
# PIPELINE
# =========================

def run():
    print("🚀 Atualizando dimensão de produtos...")

    # 📥 lê silver
    df = pd.read_parquet("data/silver.parquet")

    # 🧠 produtos únicos
    df_unique = df[
        ["id", "nome_produto", "preco_custo"]
    ].drop_duplicates("id")

    # 📁 caminho
    path = "data/dim/products.parquet"

    # 📥 se já existe
    if os.path.exists(path):
        df_base = pd.read_parquet(path)
    else:
        df_base = pd.DataFrame(columns=[
            "id",
            "nome_produto",
            "descricao",
            "refrigerado",
            "vender_como_kit",
            "quantidade_kit",
            "data_criacao",
            "data_atualizacao"
        ])

    # =========================
    # COMPATIBILIDADE
    # =========================

    colunas_obrigatorias = [
        "descricao",
        "refrigerado",
        "vender_como_kit",
        "quantidade_kit",
        "data_criacao",
        "data_atualizacao"
    ]

    for col in colunas_obrigatorias:
        if col not in df_base.columns:
            df_base[col] = None

    df_base["vender_como_kit"] = (
        df_base["vender_como_kit"]
        .fillna(False)
        .astype(bool)
    )

    df_base["quantidade_kit"] = (
        df_base["quantidade_kit"]
        .fillna(1)
        .astype(int)
    )

    # =========================
    # NOVOS PRODUTOS
    # =========================

    novos = df_unique[
        ~df_unique["id"].isin(df_base["id"])
    ].copy()

    print(f"🆕 Novos produtos: {len(novos)}")

    if len(novos) > 0:
        novos["descricao"] = None
        novos["refrigerado"] = False

        # 🎁 define kit apenas na criação (usando result_type="expand" para separar as colunas corretamente)
        kit_info = novos["preco_custo"].apply(definir_kit)

        novos["vender_como_kit"] = kit_info["vender_como_kit"]
        novos["quantidade_kit"] = kit_info["quantidade_kit"]

        novos["data_criacao"] = datetime.now()
        novos["data_atualizacao"] = None

        # remove coluna temporária
        novos = novos.drop(columns=["preco_custo"])

    # =========================
    # CONSOLIDA
    # =========================

    df_final = pd.concat(
        [df_base, novos],
        ignore_index=True
    )

    # =========================
    # SALVA
    # =========================

    os.makedirs("data/dim", exist_ok=True)

    df_final.to_parquet(
        path,
        index=False
    )

    # =========================
    # LOGS
    # =========================

    print(
        f"✅ Dimensão atualizada! "
        f"Total de produtos: {len(df_final)}"
    )

    total_kits = int(
        df_final["vender_como_kit"].sum()
    )

    print(
        f"🎁 Produtos configurados como kit: "
        f"{total_kits}"
    )

    print(
        f"📦 Produtos unitários: "
        f"{len(df_final) - total_kits}"
    )

    print("\n📊 Distribuição dos kits:")

    print(
        df_final["quantidade_kit"]
        .value_counts()
        .sort_index()
    )

if __name__ == "__main__":
    run()