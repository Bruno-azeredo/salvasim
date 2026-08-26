import os
import io
import requests
import pandas as pd
from datetime import datetime
from supabase import create_client
from PIL import Image, ImageDraw, ImageFont

# =========================
# CONFIGURAÇÕES DE CONEXÃO
# =========================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# FUNÇÃO DE GERAÇÃO DA ARTE
# =========================
def criar_arte_oferta(produto, ranking_pos):
    # Dimensões da arte (formato story/vertical ideal para redes sociais)
    largura, altura = 1080, 1350
    
    # Criando fundo com gradiente/cor sólida azul moderna (tema Atacadão/Economiza)
    img = Image.new("RGB", (largura, altura), color="#1E3A8A")
    draw = ImageDraw.Draw(img)
    
    # Tentativa de carregar uma fonte padrão do sistema, com fallback para padrão do PIL
    try:
        font_titulo = ImageFont.truetype("arial.ttf", 48)
        font_preco = ImageFont.truetype("arialbd.ttf", 64)
        font_destaque = ImageFont.truetype("arialbd.ttf", 80)
        font_pequena = ImageFont.truetype("arial.ttf", 32)
    except IOError:
        font_titulo = font_preco = font_destaque = font_pequena = ImageFont.load_default()

    # --- CABEÇALHO ---
    draw.rectangle([(0, 0), (largura, 180)], fill="#1E40AF")
    draw.text((50, 50), "ECONOMIZA ITAPECERICA", fill="#FFFFFF", font=font_titulo)
    draw.text((50, 110), f"Oferta Destaque #{ranking_pos} - Disponível no Atacadão!", fill="#93C5FD", font=font_pequena)

    # --- CAIXA DE CONTEÚDO PRINCIPAL ---
    draw.rounded_rectangle([(50, 220), (largura - 50, 1150)], radius=30, fill="#FFFFFF")

    # Nome do Produto
    nome_produto = produto.get("nome_produto", "Produto Atacadão")
    # Quebra simples de linha para o nome se for muito longo
    draw.text((90, 280), nome_produto[:40], fill="#0F172A", font=font_titulo)
    if len(nome_produto) > 40:
        draw.text((90, 340), nome_produto[40:80], fill="#0F172A", font=font_titulo)

    # --- PREÇOS E DESCONTO ---
    preco_atual = produto.get("preco", 0.0)
    preco_medio = produto.get("preco_medio", preco_atual * 1.2) # Fallback se não houver médio
    economia = max(0.0, preco_medio - preco_atual)
    
    if preco_medio > 0:
        pct_off = int(((preco_medio - preco_atual) / preco_medio) * 100)
    else:
        pct_off = 0

    # Preço Médio (Riscado)
    draw.text((90, 480), f"Preço Médio: R$ {preco_medio:.2f}", fill="#64748B", font=font_pequena)
    
    # Caixa Vermelha de "POR APENAS"
    draw.rounded_rectangle([(90, 560), (largura - 90, 740)], radius=20, fill="#DC2626")
    draw.text((130, 580), "POR APENAS", fill="#FEF08A", font=font_pequena)
    draw.text((130, 630), f"R$ {preco_atual:.2f}".replace(".", ","), fill="#FFFFFF", font=font_destaque)

    # Bloco de Economia e Desconto
    draw.rounded_rectangle([(90, 800), (480, 950)], radius=15, fill="#EFF6FF")
    draw.text((120, 825), f"{pct_off}% OFF", fill="#1D4ED8", font=font_preco)

    draw.rounded_rectangle([(520, 800), (largura - 90, 950)], radius=15, fill="#F0FDF4")
    draw.text((550, 825), f"Economize R$ {economia:.2f}".replace(".", ","), fill="#15803D", font=font_pequena)

    # --- BOTÃO RODAPÉ ---
    draw.rounded_rectangle([(90, 1020), (largura - 90, 1110)], radius=25, fill="#16A34A")
    draw.text((250, 1045), "🛒 QUERO COMPRAR", fill="#FFFFFF", font=font_titulo)

    # Salvando a imagem gerada
    os.makedirs("ofertas_geradas", exist_ok=True)
    nome_arquivo = f"ofertas_geradas/oferta_{ranking_pos}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    img.save(nome_arquivo)
    print(f"🖼️ Imagem gerada com sucesso: {nome_arquivo}")
    return nome_arquivo

# =========================
# PIPELINE PRINCIPAL
# =========================
def run():
    print("🚀 Buscando as 5 melhores ofertas no Supabase...")

    # 1. Busca dados da tabela de histórico/monitoramento
    response = supabase.table("produtos_atacadao").select("*").execute()
    dados = response.data

    if not dados:
        print("❌ Nenhum dado encontrado na tabela produtos_atacadao.")
        return

    df = pd.DataFrame(dados)

    if df.empty or "preco" not in df.columns:
        print("❌ A tabela está vazia ou não possui a coluna 'preco'.")
        return

    # Função de limpeza robusta para evitar erro ao converter para float
    def limpar_preco(val):
        if pd.isna(val) or val == "" or val is None:
            return 0.0
        val_str = str(val).replace("R$", "").replace(" ", "").strip()
        if not val_str:
            return 0.0
        # Troca ponto de milhar por vazio e vírgula decimal por ponto
        val_str = val_str.replace(".", "").replace(",", ".")
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    df["preco"] = df["preco"].apply(limpar_preco)

    # Remove produtos com preço zero ou inválido
    df = df[df["preco"] > 0]

    if df.empty:
        print("❌ Nenhum produto com preço válido foi encontrado após a limpeza.")
        return

    # Ordena e calcula métricas idênticas à aplicação Streamlit
    df = df.sort_values(by=["link", "data_extracao"])
    df["menor_preco"] = df.groupby("link")["preco"].transform("min")
    df["preco_medio"] = df.groupby("link")["preco"].transform("mean")
    
    # Pega a última coleta de cada produto
    ultima_coleta = df.sort_values("data_extracao").groupby("link").tail(1).copy()
    
    # Calcula score simples de oportunidade (quanto mais abaixo da média, melhor)
    ultima_coleta["score"] = ((ultima_coleta["preco_medio"] - ultima_coleta["preco"]) / ultima_coleta["preco_medio"]) * 100
    
    # Seleciona as 5 melhores ofertas (maior score / maior desconto percentual)
    top_5 = ultima_coleta.sort_values(by="score", ascending=False).head(5)

    if top_5.empty:
        print("❌ Não foi possível calcular o ranking das ofertas.")
        return

    print(f"🔥 Top 5 ofertas selecionadas! Gerando artes promocionais...")

    pos = 1
    for _, produto in top_5.iterrows():
        criar_arte_oferta(produto, pos)
        pos += 1

    print("🏁 Todas as imagens promocionais foram geradas na pasta 'ofertas_geradas'!")

if __name__ == "__main__":
    run()