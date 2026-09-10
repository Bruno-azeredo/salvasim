import os
import re
from datetime import datetime
import hashlib
import pandas as pd
from supabase import create_client

# =========================
# CONFIGURAÇÕES DO SUPABASE
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("As variáveis de ambiente SUPABASE_URL e SUPABASE_KEY não foram configuradas.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# FUNÇÕES AUXILIARES
# =========================
def fetch_all_from_supabase(table_name):
    """Busca todos os registros de uma tabela do Supabase com paginação"""
    all_data = []
    page_size = 1000
    start = 0
    while True:
        response = supabase.table(table_name).select("*").range(start, start + page_size - 1).execute()
        if not response.data:
            break
        all_data.extend(response.data)
        if len(response.data) < page_size:
            break
        start += page_size
    return pd.DataFrame(all_data)

def limpar_preco(preco):
    if pd.isna(preco):
        return 0.0
    preco_str = str(preco).replace("R$", "").replace(",", ".")
    preco_str = re.sub(r"[^\d\.]", "", preco_str)
    try:
        return float(preco_str)
    except:
        return 0.0

# =========================
# CÁLCULO DE OPORTUNIDADES
# =========================
def calcular_e_salvar_oportunidades(df_final):
    print("🔄 Calculando as Melhores Ofertas do Momento...")
    
    ofertas_processadas = []
    
    for _, row in df_final.iterrows():
        nome = row.get("nome_original")
        preco_atual = row.get("preco_custo")
        
        if not nome or preco_atual is None or preco_atual <= 0:
            continue

        try:
            # Busca o histórico do produto específico na tabela bruta para achar a média
            res_hist = supabase.table("produtos_atacadao").select("preco").eq("nome", nome).execute()
            historico = res_hist.data

            score = 0
            if historico and len(historico) >= 2:
                precos_hist = []
                for h in historico:
                    p_val = limpar_preco(h.get("preco"))
                    if p_val > 0:
                        precos_hist.append(p_val)
                
                if precos_hist:
                    media_historica = sum(precos_hist) / len(precos_hist)
                    if preco_atual < media_historica:
                        dif_percentual = ((media_historica - preco_atual) / media_historica) * 100
                        score = min(int(dif_percentual * 5), 100)

            # Filtra apenas quem tem um score relevante (ex: >= 60)
            if score >= 60:
                ofertas_processadas.append({
                    "id": row["id"],
                    "nome_produto": row["nome_produto"],
                    "preco_atual": preco_atual,
                    "menor_preco": row.get("menor_preco"),
                    "link": row.get("link"),
                    "imagem": row.get("imagem"),
                    "opportunity_score": score,
                    "classificacao": "Destaque",
                    "atualizado_em": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
        except Exception as e:
            continue

    if ofertas_processadas:
        print("🗑️ Limpando registros antigos da tabela `melhores_ofertas_dia`...")
        try:
            # Apaga todos os registros existentes na tabela para garantir a sobrescrita completa
            supabase.table("melhores_ofertas_dia").delete().neq("id", "0").execute()
        except Exception as e:
            print(f"⚠️ Erro ao limpar a tabela (pode estar vazia): {e}")

        print(f"☁️ Salvando {len(ofertas_processadas)} novas melhores ofertas na tabela `melhores_ofertas_dia`...")
        batch_size = 500
        for i in range(0, len(ofertas_processadas), batch_size):
            batch = ofertas_processadas[i:i+batch_size]
            supabase.table("melhores_ofertas_dia").upsert(batch).execute()
        print("✅ Melhores ofertas do dia salvas e atualizadas com sucesso!")
    else:
        print("⚠️ Nenhuma oferta atingiu o score mínimo de destaque nesta execução.")

def run():
    print("🚀 Iniciando cálculo de oportunidades via Supabase...")
    
    # Busca os dados já tratados na tabela `silver_products`
    df_final = fetch_all_from_supabase("silver_products")
    
    if df_final.empty:
        print("❌ Nenhum registro encontrado na tabela `silver_products`.")
        return

    calcular_e_salvar_oportunidades(df_final)

if __name__ == "__main__":
    run()