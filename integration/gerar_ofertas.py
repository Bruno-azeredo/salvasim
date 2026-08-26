import os
import pandas as pd
from supabase import create_client, Client

# Configurações do Supabase via Variáveis de Ambiente do GitHub Actions
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def run():
    print("🚀 Buscando dados no Supabase para alinhar com o dashboard...")

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

    # Garante ordenação cronológica correta por produto e data
    df["data_extracao"] = pd.to_datetime(df["data_extracao"], errors="coerce")
    df = df.sort_values(by=["link", "data_extracao"])

    # Pega o preço anterior (o valor imediatamente antes da última coleta para o mesmo produto)
    df["preco_anterior"] = df.groupby("link")["preco"].shift(1)

    # Filtra apenas linhas que possuem um preço anterior válido para comparar
    df_validos = df.dropna(subset=["preco_anterior"]).copy()

    if df_validos.empty:
        print("❌ Não há histórico suficiente para comparar preços anteriores.")
        return

    # Pega estritamente a última coleta de cada produto
    ultima_coleta = df_validos.sort_values("data_extracao").groupby("link").tail(1).copy()
    
    # Calcula a variação exata idêntica à do dashboard
    ultima_coleta["variacao_pct"] = ((ultima_coleta["preco"] - ultima_coleta["preco_anterior"]) / ultima_coleta["preco_anterior"]) * 100

    # Ordena pelas maiores quedas percentuais
    top_5 = ultima_coleta.sort_values(by="variacao_pct", ascending=True).head(5)

    if top_5.empty:
        print("❌ Não foi possível calcular o ranking.")
        return

    print(f"\n🔥 Top 5 maiores quedas alinhadas com o Dashboard! Gerando prompts com URLs:\n" + "="*50)

    pos = 1
    for _, produto in top_5.iterrows():
        nome_produto = produto.get("nome", "Produto")
        preco_atual = produto.get("preco", 0.0)
        preco_anterior = produto.get("preco_anterior", 0.0)
        variacao = produto.get("variacao_pct", 0.0)
        
        # Pega a URL da imagem (substitua 'imagem' pelo nome real da sua coluna no banco se for diferente)
        url_imagem = produto.get("imagem", "URL não disponível")
        
        # Monta o prompt incluindo a referência da imagem
        prompt_gerado = (
            f"Flyer publicitário profissional de supermercado no estilo 3D vibrante, "
            f"com fundo azul dinâmico, elementos de porcentagem e ícones de comércio. "
            f"Em destaque central, exiba o produto: {nome_produto} (com base na referência visual da imagem: {url_imagem}). "
            f"Inclua letreiros chamativos com o preço promocional de R$ {preco_atual:.2f} "
            f"(antes custava R$ {preco_anterior:.2f}, queda de {variacao:.2f}%). "
            f"Design moderno, cores azul e vermelho, iluminação de estúdio, alta qualidade comercial."
        )
        
        print(f"\n[OFERTA {pos}] - Produto: {nome_produto}")
        print(f"Preço Anterior: R$ {preco_anterior:.2f} | Preço Atual: R$ {preco_atual:.2f} | Variação: {variacao:.2f}%")
        print(f"🖼️ URL da Imagem: {url_imagem}")
        print(prompt_gerado)
        print("-" * 50)
        pos += 1

    print("\n🏁 Processo concluído com sucesso!")

if __name__ == "__main__":
    run()