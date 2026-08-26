import os
import pandas as pd
from supabase import create_client, Client

# Configurações do Supabase via Variáveis de Ambiente do GitHub Actions
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def run():
    print("🚀 Buscando dados no Supabase para análise de queda de preço...")

    # 1. Busca dados da tabela
    response = supabase.table("produtos_atacadao").select("*").execute()
    dados = response.data

    if not dados:
        print("❌ Nenhum dado encontrado na tabela produtos_atacadao.")
        return

    df = pd.DataFrame(dados)

    if df.empty or "preco" not in df.columns:
        print("❌ A tabela está vazia ou não possui a coluna 'preco'.")
        return

    # Função de limpeza robusta para o preço
    def limpar_preco(val):
        if pd.isna(val) or val == "" or val is None:
            return 0.0
        val_str = str(val).replace("R$", "").replace(" ", "").strip()
        if not val_str:
            return 0.0
        val_str = val_str.replace(".", "").replace(",", ".")
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    df["preco"] = df["preco"].apply(limpar_preco)
    df = df[df["preco"] > 0]

    if df.empty:
        print("❌ Nenhum produto com preço válido foi encontrado após a limpeza.")
        return

    # Garante ordenação cronológica correta
    df["data_extracao"] = pd.to_datetime(df["data_extracao"], errors="coerce")
    df = df.sort_values(by=["link", "data_extracao"])

    # Calcula o preço médio histórico e o maior preço registrado por produto para servir de referência de queda
    df["preco_medio"] = df.groupby("link")["preco"].transform("mean")
    df["preco_maximo"] = df.groupby("link")["preco"].transform("max")

    # Pega estritamente a última coleta de cada produto
    ultima_coleta = df.sort_values("data_extracao").groupby("link").tail(1).copy()
    
    # Foco total em Queda de Preço:
    # 1. Diferença absoluta em dinheiro (quanto mais caiu em R$, maior a prioridade)
    # 2. Desconto percentual em relação ao preço máximo/médio
    ultima_coleta["queda_absoluta"] = ultima_coleta["preco_maximo"] - ultima_coleta["preco"]
    ultima_coleta["queda_percentual"] = ((ultima_coleta["preco_maximo"] - ultima_coleta["preco"]) / ultima_coleta["preco_maximo"]) * 100

    # Seleciona as 5 maiores quedas absolutas e percentuais
    top_5 = ultima_coleta.sort_values(by=["queda_absoluta", "queda_percentual"], ascending=False).head(5)

    if top_5.empty:
        print("❌ Não foi possível calcular o ranking de quedas.")
        return

    print(f"\n🔥 Top 5 maiores quedas de preço selecionadas! Gerando prompts:\n" + "="*50)

    pos = 1
    for _, produto in top_5.iterrows():
        nome_produto = produto.get("nome", "Produto")
        preco_atual = produto.get("preco", 0.0)
        preco_anterior = produto.get("preco_maximo", preco_atual)
        economia = produto.get("queda_absoluta", 0.0)
        
        # Monta o prompt rico focado na queda de preço
        prompt_gerado = (
            f"Flyer publicitário profissional de supermercado no estilo 3D vibrante, "
            f"com fundo azul dinâmico, elementos de porcentagem e ícones de comércio. "
            f"Em destaque central, exiba o produto: {nome_produto}. "
            f"Inclua letreiros chamativos com o preço promocional de R$ {preco_atual:.2f} "
            f"(antes custava R$ {preco_anterior:.2f}, economia de R$ {economia:.2f}). "
            f"Design moderno, cores azul e vermelho, iluminação de estúdio, alta qualidade comercial."
        )
        
        print(f"\n[QUEDA {pos}] - Produto: {nome_produto}")
        print(f"Preço Anterior: R$ {preco_anterior:.2f} | Preço Atual: R$ {preco_atual:.2f} | Economia: R$ {economia:.2f}")
        print(prompt_gerado)
        print("-" * 50)
        pos += 1

    print("\n🏁 Processo concluído com sucesso!")

if __name__ == "__main__":
    run()