import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client
import re
import os

# =====================================================
# CONFIGURAÇÃO DA PÁGINA
# =====================================================
st.set_page_config(
    page_title="Monitor de Preços | Atacadão Itapecerica",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS personalizada
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.0rem;
        color: #94A3B8;
        margin-bottom: 1.5rem;
    }
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

# =====================================================
# CONFIGURAÇÃO DO SUPABASE
# =====================================================
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# =====================================================
# CARREGAMENTO E PROCESSAMENTO DOS DADOS (COM PAGINAÇÃO)
# =====================================================
@st.cache_data(ttl=600)
def load_and_process_data():
    rows = []
    limit = 1000
    offset = 0
    while True:
        try:
            res = supabase.table("produtos_atacadao").select("*").range(offset, offset + limit - 1).execute()
            if not res.data:
                break
            rows.extend(res.data)
            if len(res.data) < limit:
                break
            offset += limit
        except Exception as e:
            print(f"Erro ao buscar produtos_atacadao: {e}")
            break

    df = pd.DataFrame(rows)
    
    if df.empty:
        return df

    # Conversão de data
    if "data_extracao" in df.columns:
        df["data_extracao"] = pd.to_datetime(df["data_extracao"], errors="coerce")

    # Limpeza robusta da coluna de preço (Text -> Float)
    if "preco" in df.columns:
        def limpar_num(val):
            if pd.isna(val):
                return None
            val_str = str(val)
            match = re.search(r'([\d\.]+,\d{2})', val_str)
            if match:
                num_str = match.group(1).replace(".", "").replace(",", ".")
                try:
                    return float(num_str)
                except ValueError:
                    pass
            clean_str = (
                val_str.replace("R$", "")
                .replace(" ", "")
                .replace(".", "")
                .replace(",", ".")
            )
            try:
                return float(clean_str)
            except ValueError:
                return None

        df["preco"] = df["preco"].apply(limpar_num)

    # Normalização de Nome de Produto
    if "nome_produto" not in df.columns:
        for alt in ["nome", "titulo", "produto", "descricao"]:
            if alt in df.columns:
                df["nome_produto"] = df[alt]
                break
        if "nome_produto" not in df.columns and "link" in df.columns:
            df["nome_produto"] = df["link"]

    # Normalização de Categoria
    if "categoria" not in df.columns:
        found_cat = False
        for col in ["category", "departamento", "grupo", "cat", "secao"]:
            if col in df.columns:
                df["categoria"] = df[col].fillna("Sem Categoria")
                found_cat = True
                break
        if not found_cat:
            df["categoria"] = "Geral"

    # Ordenação por data para calcular histórico corretamente
    df = df.sort_values(by=["link", "data_extracao"])

    # Cálculo dinâmico por produto (Menor preço, preço médio, variação, etc.)
    if "link" in df.columns and "preco" in df.columns:
        df["menor_preco"] = df.groupby("link")["preco"].transform("min")
        df["preco_medio"] = df.groupby("link")["preco"].transform("mean")
        df["preco_max"] = df.groupby("link")["preco"].transform("max")
        df["preco_anterior"] = df.groupby("link")["preco"].shift(1)
        
        # Variação percentual em relação à coleta anterior
        df["variacao_pct"] = ((df["preco"] - df["preco_anterior"]) / df["preco_anterior"]) * 100
        
        # Distância percentual em relação à média histórica
        df["abaixo_media_pct"] = ((df["preco_medio"] - df["preco"]) / df["preco_medio"]) * 100
        
        def calcular_score(row):
            p = row["preco"]
            p_min = row["menor_preco"]
            p_max = row["preco_max"]
            if pd.isna(p) or pd.isna(p_min) or p_max == p_min:
                return 50.0
            score = 100 * (1 - (p - p_min) / (p_max - p_min + 0.0001))
            return max(0.0, min(100.0, score))

        df["score"] = df.apply(calcular_score, axis=1)

    return df

df_monitor = load_and_process_data()

# =====================================================
# SIDEBAR / NAVEGAÇÃO
# =====================================================
st.sidebar.image("https://img.icons8.com/color/96/shopping-cart-loaded.png", width=64)
st.sidebar.title("Atacadão Itapecerica")
st.sidebar.caption("Monitor de Inteligência de Preços")

opcao_menu = st.sidebar.radio(
    "Navegação",
    [
        "📊 Visão Geral",
        "🏆 Ranking de Oportunidades",
        "🚨 Alertas do Dia",
        "📈 Histórico do Produto"
    ],
    index=0 
)

# Filtro global: Apenas produtos da data atual
st.sidebar.markdown("---")
st.sidebar.markdown("### 📅 Filtro Temporal")
apenas_data_atual = st.sidebar.checkbox("Considerar apenas produtos da data atual (Hoje)", value=False)

# Filtro de Categoria
todas_categorias = sorted(df_monitor["categoria"].dropna().unique().tolist()) if not df_monitor.empty and "categoria" in df_monitor.columns else []

st.sidebar.markdown("---")
st.sidebar.markdown("### 🏷️ Filtros de Busca")

if todas_categorias:
    categorias_selecionadas = st.sidebar.multiselect(
        "Filtrar por Categoria:",
        options=todas_categorias,
        default=todas_categorias
    )
else:
    categorias_selecionadas = []

# Função unificada de filtragem aplicada em todas as telas
def filtrar_dados(df):
    if df.empty:
        return df
    
    df_f = df.copy()
    
    # 1. Filtro por data atual, se ativado
    if apenas_data_atual and "data_extracao" in df_f.columns:
        hoje = pd.Timestamp.today().normalize()
        df_f["data_apenas"] = df_f["data_extracao"].dt.normalize()
        df_f = df_f[df_f["data_apenas"] == hoje]
        
    # 2. Filtro por categoria
    if "categoria" in df_f.columns and categorias_selecionadas:
        df_f = df_f[df_f["categoria"].isin(categorias_selecionadas)]
        
    return df_f

df_filtered = filtrar_dados(df_monitor)

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Status da Base")
if not df_monitor.empty:
    st.sidebar.text(f"Total de Registros: {len(df_monitor):,}")
    st.sidebar.text(f"Produtos Únicos: {df_monitor['link'].nunique():,}")
else:
    st.sidebar.warning("Base vazia.")


# =====================================================
# PÁGINA 1: VISÃO GERAL
# =====================================================
if opcao_menu == "📊 Visão Geral":
    st.markdown('<div class="main-title">Visão Geral de Precificação</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Atacadão Itapecerica da Serra - Métricas calculadas em tempo real</div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)

    total_prods = df_filtered["link"].nunique() if not df_filtered.empty and "link" in df_filtered.columns else 0
    
    oportunidades_df = pd.DataFrame()
    alertas_df = pd.DataFrame()
    
    if not df_filtered.empty:
        ultima_coleta = df_filtered.sort_values("data_extracao").groupby("link").tail(1)
        oportunidades_df = ultima_coleta[ultima_coleta["preco"] <= ultima_coleta["menor_preco"] * 1.01]
        alertas_df = ultima_coleta[ultima_coleta["variacao_pct"].abs() >= 5]
        quedas_hoje = len(alertas_df[alertas_df["variacao_pct"] < 0])
    else:
        quedas_hoje = 0

    col1.metric("Produtos Monitorados", f"{total_prods:,}")
    col2.metric("Oportunidades (Menor Preço)", f"{len(oportunidades_df):,}")
    col3.metric("Alertas Relevantes (≥5%)", f"{len(alertas_df):,}")
    col4.metric("Quedas de Preço Recentes", f"{quedas_hoje:,}")

    st.markdown("---")

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("🎯 Distribuição dos Scores de Oportunidades")
        if not df_filtered.empty and "score" in df_filtered.columns:
            fig_score = px.histogram(
                ultima_coleta,
                x="score",
                nbins=20,
                title="Distribuição do Score dos Produtos",
                color_discrete_sequence=["#2563EB"]
            )
            fig_score.update_layout(xaxis_title="Score", yaxis_title="Quantidade", template="plotly_dark")
            st.plotly_chart(fig_score, use_container_width=True)
        else:
            st.info("Sem dados suficientes para exibir o gráfico.")

    with col_right:
        st.subheader("📉 Top 5 Maiores Quedas Recentes")
        if not alertas_df.empty and "variacao_pct" in alertas_df.columns:
            top_quedas = alertas_df.sort_values("variacao_pct").head(5)
            cols_exibicao = ["nome_produto", "categoria", "preco", "preco_anterior", "variacao_pct"]
            cols_disponiveis = [c for c in cols_exibicao if c in top_quedas.columns]
            st.dataframe(
                top_quedas[cols_disponiveis].rename(columns={
                    "nome_produto": "Produto",
                    "categoria": "Categoria",
                    "preco": "Preço Atual",
                    "preco_anterior": "Preço Anterior",
                    "variacao_pct": "Variação (%)"
                }), 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.info("Nenhuma queda de preço significativa identificada.")


# =====================================================
# PÁGINA 2: RANKING DE OPORTUNIDADES
# =====================================================
elif opcao_menu == "🏆 Ranking de Oportunidades":
    st.markdown('<div class="main-title">🏆 Ranking de Oportunidades</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Produtos ordenados pelo Score de Oportunidade calculado</div>', unsafe_allow_html=True)

    if df_filtered.empty:
        st.warning("Nenhum produto encontrado com os filtros atuais.")
    else:
        df_rank = df_filtered.sort_values("data_extracao").groupby("link").tail(1).sort_values(by="score", ascending=False)

        col_f1, col_f2 = st.columns([2, 2])
        with col_f1:
            busca = st.text_input("🔍 Pesquisar por nome do produto:", "")
        with col_f2:
            apenas_menor = st.checkbox("Exibir apenas produtos no menor preço histórico", value=False)

        if busca and "nome_produto" in df_rank.columns:
            df_rank = df_rank[df_rank["nome_produto"].str.contains(busca, case=False, na=False)]
        
        if apenas_menor and "preco" in df_rank.columns and "menor_preco" in df_rank.columns:
            df_rank = df_rank[df_rank["preco"] == df_rank["menor_preco"]]

        cols_desejadas = ["nome_produto", "categoria", "preco", "menor_preco", "preco_medio", "variacao_pct", "score", "link"]
        cols_existentes = [c for c in cols_desejadas if c in df_rank.columns]
        
        df_display = df_rank[cols_existentes].rename(columns={
            "nome_produto": "Produto",
            "categoria": "Categoria",
            "preco": "Preço Atual",
            "menor_preco": "Menor Preço",
            "preco_medio": "Preço Médio",
            "variacao_pct": "Variação (%)",
            "score": "Score",
            "link": "Link"
        })

        st.dataframe(df_display, use_container_width=True, height=600, hide_index=True)


# =====================================================
# PÁGINA 3: ALERTAS DO DIA
# =====================================================
elif opcao_menu == "🚨 Alertas do Dia":
    st.markdown('<div class="main-title">🚨 Alertas Diários de Preço</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Variações de preço iguais ou superiores a 5%</div>', unsafe_allow_html=True)

    if df_filtered.empty:
        st.info("Nenhum dado disponível com os filtros atuais.")
    else:
        ultima_coleta = df_filtered.sort_values("data_extracao").groupby("link").tail(1).copy()
        df_alertas = ultima_coleta[ultima_coleta["variacao_pct"].abs() >= 5].copy()

        if df_alertas.empty:
            st.info("Nenhum alerta de variação expressiva (≥ 5%) encontrado.")
        else:
            tipo_filtro = st.radio("Filtrar por Tipo:", ["Todos", "Queda 📉", "Alta 📈"], horizontal=True)

            if tipo_filtro == "Queda 📉":
                df_alertas = df_alertas[df_alertas["variacao_pct"] < 0]
            elif tipo_filtro == "Alta 📈":
                df_alertas = df_alertas[df_alertas["variacao_pct"] > 0]

            cols_existentes = [c for c in ["nome_produto", "categoria", "preco", "preco_anterior", "variacao_pct", "data_extracao", "link"] if c in df_alertas.columns]
            
            df_display = df_alertas[cols_existentes].rename(columns={
                "nome_produto": "Produto",
                "categoria": "Categoria",
                "preco": "Preço Atual",
                "preco_anterior": "Preço Anterior",
                "variacao_pct": "Variação (%)",
                "data_extracao": "Data/Hora Extração",
                "link": "Link"
            })
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)


# =====================================================
# PÁGINA 4: HISTÓRICO DO PRODUTO
# =====================================================
elif opcao_menu == "📈 Histórico do Produto":
    st.markdown('<div class="main-title">📈 Histórico e Evolução de Preços</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Selecione um produto para acompanhar seu histórico temporal completo</div>', unsafe_allow_html=True)

    if df_filtered.empty:
        st.error("Nenhum produto disponível com os filtros atuais.")
    else:
        link_col = "link" if "link" in df_filtered.columns else df_filtered.columns[0]
        produtos_unicos = df_filtered[[link_col, "nome_produto"]].drop_duplicates().sort_values("nome_produto")
        opcoes = dict(zip(produtos_unicos["nome_produto"], produtos_unicos[link_col]))
        
        produto_selecionado_nome = st.selectbox(
            "Pesquise ou selecione um produto:",
            options=list(opcoes.keys()),
            index=0
        )

        link_selecionado = opcoes[produto_selecionado_nome]
        df_prod = df_filtered[df_filtered[link_col] == link_selecionado].sort_values("data_extracao")

        st.markdown("---")

        p_atual = df_prod["preco"].iloc[-1] if not df_prod.empty and "preco" in df_prod.columns else 0
        p_menor = df_prod["preco"].min() if not df_prod.empty and "preco" in df_prod.columns else 0
        p_medio = df_prod["preco"].mean() if not df_prod.empty and "preco" in df_prod.columns else 0
        p_maior = df_prod["preco"].max() if not df_prod.empty and "preco" in df_prod.columns else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Preço Atual", f"R$ {p_atual:.2f}")
        c2.metric("Menor Preço Histórico", f"R$ {p_menor:.2f}")
        c3.metric("Preço Médio Histórico", f"R$ {p_medio:.2f}")
        c4.metric("Maior Preço Histórico", f"R$ {p_maior:.2f}")

        st.markdown("<br>", unsafe_allow_html=True)

        if not df_prod.empty and "data_extracao" in df_prod.columns and "preco" in df_prod.columns:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_prod["data_extracao"],
                y=df_prod["preco"],
                mode="lines+markers",
                name="Preço Coletado (R$)",
                line=dict(color="#2563EB", width=3),
                marker=dict(size=6)
            ))
            
            fig.add_hline(
                y=p_medio,
                line_dash="dash",
                line_color="#F59E0B",
                annotation_text=f"Média: R$ {p_medio:.2f}",
                annotation_position="bottom right"
            )

            fig.update_layout(
                title=f"Evolução de Preços - {produto_selecionado_nome}",
                xaxis_title="Data de Extração",
                yaxis_title="Preço (R$)",
                hovermode="x unified",
                template="plotly_dark",
                height=500
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("📋 Ver tabela detalhada do histórico de coletas"):
                cols_hist = [c for c in ["data_extracao", "preco", "preco_anterior", "variacao_pct"] if c in df_prod.columns]
                st.dataframe(
                    df_prod[cols_hist].rename(columns={
                        "data_extracao": "Data/Hora Extração",
                        "preco": "Preço",
                        "preco_anterior": "Preço Anterior",
                        "variacao_pct": "Variação (%)"
                    }),
                    use_container_width=True,
                    hide_index=True
                )