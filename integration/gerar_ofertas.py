import os
import pandas as pd
from supabase import create_client, Client

# Configurações do Supabase via Variáveis de Ambiente do GitHub Actions
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def run():
    print("🚀 Buscando as 5 melhores ofertas no Supabase...")

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

    # Ordena e calcula métricas
    df = df.sort_values(by=["link", "data_extracao"])
    df["menor_preco"] = df.groupby("link")["preco"].transform("min")
    df["preco_medio"] = df.groupby("link")["preco"].transform("mean")
    
    # Pega a última coleta de cada produto
    ultima_coleta = df.sort_values("data_extracao").groupby("link").tail(1).copy()
    
    # Calcula score de oportunidade (desconto percentual)
    ultima_coleta["score"] = ((ultima_coleta["preco_medio"] - ultima_coleta["preco"]) / ultima_coleta["preco_medio"]) * 100
    
    # Seleciona as 5 melhores ofertas
    top_5 = ultima_coleta.sort_values(by="score", ascending=False).head(5)

    if top_5.empty:
        print("❌ Não foi possível calcular o ranking das ofertas.")
        return

    print(f"\n🔥 Top 5 ofertas selecionadas! Gerando prompts detalhados:\n" + "="*50)

    pos = 1
    for _, produto in top_5.iterrows():
        nome_produto = produto.get("nome", "Produto")
        preco_produto = produto.get("preco", 0.0)
        preco_medio = produto.get("preco_medio", 0.0)
        
        # Monta o prompt rico para a criação manual da imagem
        prompt_gerado = (
            f"Flyer publicitário profissional de supermercado no estilo 3D vibrante, "
            f"com fundo azul dinâmico, elementos de porcentagem e ícones de comércio. "
            f"Em destaque central, exiba o produto: {nome_produto}. "
            f"Inclua letreiros chamativos com o preço promocional de R$ {preco_produto:.2f} "
            f"(comparado ao preço médio anterior de R$ {preco_medio:.2f}). "
            f"Design moderno, cores azul e vermelho, iluminação de estúdio, alta qualidade comercial."
        )
        
        print(f"\n[PROMPT {pos}] - Produto: {nome_produto}")
        print(prompt_gerado)
        print("-" * 50)
        pos += 1

    print("\n🏁 Processo de geração de prompts concluído com sucesso!")

if __name__ == "__main__":
    run()