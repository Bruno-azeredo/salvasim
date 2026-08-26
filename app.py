import streamlit as pd_st # Usaremos st padrão
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client

# =====================================================
# CONFIGURAÇÃO DA PÁGINA
# =====================================================
st.set_page_config(
    page_title="Monitor de Preços | E-commerce Intelligence",
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
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.0rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
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
# CARREGAMENTO COM CACHE E PAGINAÇÃO (SUPABASE > 1000 LINHAS)
# =====================================================
@st.cache_data(ttl=600)
def load_data():
    data = {}
    
    def fetch_all_rows(table_name):
        """Busca todas as linhas de uma tabela do Supabase paginando de 1000 em 1000"""
        rows = []
        limit = 1000
        offset = 0
        while True:
            try:
                res = supabase.table(table_name).select("*").range(offset, offset + limit - 1).execute()
                if not res.data:
                    break
                rows.extend(res.data)
                if len(res.data) < limit:
                    break
                offset += limit
            except Exception as e:
                print(f"Erro ao buscar {table_name}: {e}")
                break
        return rows

    # Carrega cada tabela usando a paginação para burlar o limite de 1000
    try:
        data["ranking"] = pd.DataFrame(fetch_all_rows("gold_ranking"))
    except Exception:
        data["ranking"] = pd.DataFrame()

    try:
        data["oportunidades"] = pd.DataFrame(fetch_all_rows("gold_oportunidades"))
    except Exception:
        data["oportunidades"] = pd.DataFrame()

    try:
        data["alertas"] = pd.DataFrame(fetch_all_rows("gold_alertas"))
    except Exception:
        data["alertas"] = pd.DataFrame()

    try:
        data["monitor"] = pd.DataFrame(fetch_all_rows("produtos_atacadao"))
    except Exception:
        data["monitor"] = pd.DataFrame()

    # Conversão de datas e limpeza de colunas numéricas em todos os dataframes
    cols_numericas = ["preco", "preco_anterior", "preco_medio", "menor_preco", "variacao_pct", "abaixo_media_pct", "score"]
    
    for key in data:
        if not data[key].empty:
            if "data_extracao" in data[key].columns:
                data[key]["data_extracao"] = pd.to_datetime(data[key]["data_extracao"])
            
            # Limpa e converte colunas numéricas caso existam no dataframe
            for col in cols_numericas:
                if col in data[key].columns:
                    data[key][col] = (
                        data[key][col]
                        .astype(str)
                        .str.replace("R$", "", regex=False)
                        .str.replace(" ", "", regex=False)
                        .str.replace(".", "", regex=False)
                        .str.replace(",", ".", regex=False)
                    )
                    data[key][col] = pd.to_numeric(data[key][col], errors="coerce")

    return data

data = load_data()

# =====================================================
# NORMALIZAÇÃO DE COLUNAS (NOME DO PRODUTO E CATEGORIA)
# =====================================================
for key in ["ranking", "oportunidades", "alertas", "monitor"]:
    if not data[key].empty:
        # Normalização do Nome do Produto
        if "nome_produto" in data[key].columns:
            pass
        elif "nome" in data[key].columns:
            data[key]["nome_produto"] = data[key]["nome"]
        elif "titulo" in data[key].columns:
            data[key]["nome_produto"] = data[key]["titulo"]
        elif "produto" in data[key].columns:
            data[key]["nome_produto"] = data[key]["produto"]
        else:
            data[key]["nome_produto"] = data[key]["link"]

        # Normalização da Categoria
        cat_cols = ["categoria", "category", "departamento", "grupo", "cat"]
        found_cat = False
        for col in cat_cols:
            if col in data[key].columns:
                data[key]["categoria"] = data[key][col].fillna("Sem Categoria")
                found_cat = True
                break
        if not found_cat:
            data[key]["categoria"] = "Geral"

# =====================================================
# SIDEBAR / NAVEGAÇÃO
# =====================================================
st.sidebar.image("https://img.icons8.com/color/96/shopping-cart-loaded.png", width=64)
st.sidebar.title("Intelligence B2B")
st.sidebar.caption("Atacadão Price Tracker")

opcao_menu = st.sidebar.radio(
    "Navegação",
    [
        "📊 Visão Geral",
        "🏆 Ranking de Oportunidades",
        "🚨 Alertas do Dia",
        "📈 Histórico do Produto"
    ],
    index=1
)

# -----------------------------------------------------
# FILTRO DE CATEGORIA NA SIDEBAR
# -----------------------------------------------------
todas_categorias = set()
for key in ["ranking", "oportunidades", "alertas", "monitor"]:
    if not data[key].empty and "categoria" in data[key].columns:
        todas_categorias.update(data[key]["categoria"].unique())

lista_categorias = sorted(list(todas_categorias))

st.sidebar.markdown("---")
st.sidebar.markdown("### 🏷️ Filtros de Busca")

if lista_categorias:
    categorias_selecionadas = st.sidebar.multiselect(
        "Filtrar por Categoria:",
        options=lista_categorias,
        default=lista_categorias
    )
else:
    categorias_selecionadas = []

# Função helper para filtrar dataframes por categoria selecionada
def filtrar_por_categoria(df):
    if df.empty or "categoria" not in df.columns or not categorias_selecionadas:
        return df
    return df[df["categoria"].isin(categorias_selecionadas)]

# Aplicando os filtros globais
df_ranking_filtered = filtrar_por_categoria(data["ranking"])
df_oportunidades_filtered = filtrar_por_categoria(data["oportunidades"])
df_alertas_filtered = filtrar_por_categoria(data["alertas"])
df_monitor_filtered = filtrar_por_categoria(data["monitor"])

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Informações da Base")
if not df_monitor_filtered.empty:
    st.sidebar.text(f"Produtos: {df_monitor_filtered['link'].nunique():,}")
    st.sidebar.text(f"Histórico: {len(df_monitor_filtered):,} reg")
    max_data = df_monitor_filtered["data_extracao"].max()
    st.sidebar.text(f"Última Carga:\n{max_data.strftime('%d/%m/%Y %H:%M')}")
else:
    st.sidebar.warning("Nenhum dado encontrado para os filtros selecionados.")


# =====================================================
# PÁGINA 1: VISÃO GERAL
# =====================================================
if opcao_menu == "📊 Visão Geral":
    st.markdown('<div class="main-title">Visão Geral de Precificação</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Métricas consolidadas do último ciclo de monitoramento</div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)

    total_prods = df_monitor_filtered["link"].nunique() if not df_monitor_filtered.empty else 0
    total_oportunidades = len(df_oportunidades_filtered) if not df_oportunidades_filtered.empty else 0
    total_alertas = len(df_alertas_filtered) if not df_alertas_filtered.empty else 0
    quedas_hoje = len(df_alertas_filtered[df_alertas_filtered["variacao_pct"] < 0]) if not df_alertas_filtered.empty and "variacao_pct" in df_alertas_filtered.columns else 0

    col1.metric("Produtos Monitorados", f"{total_prods:,}")
    col2.metric("Oportunidades (Menor Preço)", f"{total_oportunidades:,}")
    col3.metric("Alertas Relevantes (≥5%)", f"{total_alertas:,}")
    col4.metric("Quedas de Preço Hoje", f"{quedas_hoje:,}", delta_color="inverse")

    st.markdown("---")

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("🎯 Distribuição dos Scores de Oportunidades")
        if not df_ranking_filtered.empty and "score" in df_ranking_filtered.columns:
            fig_score = px.histogram(
                df_ranking_filtered,
                x="score",
                nbins=20,
                title="Distribuição do Score",
                color_discrete_sequence=["#2563EB"]
            )
            fig_score.update_layout(xaxis_title="Score de Oportunidade", yaxis_title="Quantidade")
            st.plotly_chart(fig_score, use_container_width=True)
        else:
            st.info("Sem dados para exibir para essa seleção.")

    with col_right:
        st.subheader("📉 Top 5 Maiores Quedas do Dia")
        if not df_alertas_filtered.empty and "variacao_pct" in df_alertas_filtered.columns:
            top_quedas = df_alertas_filtered.sort_values("variacao_pct").head(5)
            cols_exibicao = ["nome_produto", "categoria", "preco", "preco_anterior", "variacao_pct"]
            cols_disponiveis = [c for c in cols_exibicao if c in top_quedas.columns]
            st.dataframe(
                top_quedas[cols_disponiveis].rename(columns={
                    "nome_produto": "Produto",
                    "categoria": "Categoria",
                    "preco": "Preço Atual (R$)",
                    "preco_anterior": "Preço Anter. (R$)",
                    "variacao_pct": "Variação (%)"
                }),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Sem alertas de queda para a seleção atual.")


# =====================================================
# PÁGINA 2: RANKING DE OPORTUNIDADES
# =====================================================
elif opcao_menu == "🏆 Ranking de Oportunidades":
    st.markdown('<div class="main-title">🏆 Ranking de Oportunidades</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Produtos ordenados pelo Score de Oportunidade</div>', unsafe_allow_html=True)

    df_rank = df_ranking_filtered.copy()

    if df_rank.empty:
        st.warning("Nenhum produto encontrado para o filtro aplicado.")
    else:
        col_f1, col_f2 = st.columns([2, 2])
        with col_f1:
            busca = st.text_input("🔍 Pesquisar por nome do produto:", "")
        with col_f2:
            apenas_menor = st.checkbox("Exibir apenas produtos no menor preço histórico", value=False)

        if busca:
            df_rank = df_rank[df_rank["nome_produto"].str.contains(busca, case=False, na=False)]
        
        if apenas_menor and "preco" in df_rank.columns and "menor_preco" in df_rank.columns:
            df_rank = df_rank[df_rank["preco"] == df_rank["menor_preco"]]

        st.caption(f"Exibindo {len(df_rank)} produtos de um total de {len(df_ranking_filtered)} no filtro atual.")

        colunas_desejadas = ["nome_produto", "categoria", "preco", "menor_preco", "preco_medio", "variacao_pct", "abaixo_media_pct", "score", "link"]
        colunas_existentes = [c for c in colunas_desejadas if c in df_rank.columns]
        df_display = df_rank[colunas_existentes].copy()

        renomear = {
            "nome_produto": "Produto", "categoria": "Categoria", "preco": "Preço Atual (R$)",
            "menor_preco": "Menor Preço (R$)", "preco_medio": "Preço Médio (R$)",
            "variacao_pct": "Var. Última Coleta (%)", "abaixo_media_pct": "vs Média (%)",
            "score": "Score", "link": "Link / URL"
        }
        df_display = df_display.rename(columns=renomear)

        st.dataframe(
            df_display,
            use_container_width=True,
            height=600,
            hide_index=True
        )


# =====================================================
# PÁGINA 3: ALERTAS DO DIA
# =====================================================
elif opcao_menu == "🚨 Alertas do Dia":
    st.markdown('<div class="main-title">🚨 Alertas Diários de Preço</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Produtos que sofreram variação de preço igual ou superior a 5%</div>', unsafe_allow_html=True)

    df_alertas = df_alertas_filtered.copy()

    if df_alertas.empty:
        st.info("Nenhum alerta significativo registrado para os filtros atuais.")
    else:
        tipo_filtro = st.radio("Filtrar por Tipo:", ["Todos", "Queda 📉", "Alta 📈"], horizontal=True)

        if tipo_filtro == "Queda 📉" and "variacao_pct" in df_alertas.columns:
            df_alertas = df_alertas[df_alertas["variacao_pct"] < 0]
        elif tipo_filtro == "Alta 📈" and "variacao_pct" in df_alertas.columns:
            df_alertas = df_alertas[df_alertas["variacao_pct"] > 0]

        colunas_desejadas = ["nome_produto", "categoria", "preco", "preco_anterior", "variacao_pct", "tipo", "link"]
        colunas_existentes = [c for c in colunas_desejadas if c in df_alertas.columns]

        st.dataframe(
            df_alertas[colunas_existentes].rename(columns={
                "nome_produto": "Produto", "categoria": "Categoria", "preco": "Preço Atual (R$)",
                "preco_anterior": "Preço Anterior (R$)", "variacao_pct": "Variação (%)",
                "tipo": "Tipo de Alerta", "link": "Link"
            }),
            use_container_width=True,
            hide_index=True
        )


# =====================================================
# PÁGINA 4: HISTÓRICO DO PRODUTO
# =====================================================
elif opcao_menu == "📈 Histórico do Produto":
    st.markdown('<div class="main-title">📈 Histórico e Evolução de Preços</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Selecione um produto para acompanhar seu histórico temporal</div>', unsafe_allow_html=True)

    df_monitor = df_monitor_filtered.copy()

    if df_monitor.empty:
        st.error("Nenhum produto disponível com os filtros atuais.")
    else:
        produtos_unicos = df_monitor[["link", "nome_produto"]].drop_duplicates().sort_values("nome_produto")
        opcoes = dict(zip(produtos_unicos["nome_produto"], produtos_unicos["link"]))
        
        produto_selecionado_nome = st.selectbox(
            "Pesquise ou selecione um produto:",
            options=list(opcoes.keys()),
            index=0
        )

        link_selecionado = opcoes[produto_selecionado_nome]
        df_prod = df_monitor[df_monitor["link"] == link_selecionado].sort_values("data_extracao")

        st.markdown("---")

        p_atual = df_prod["preco"].iloc[-1] if not df_prod.empty else 0
        p_menor = df_prod["preco"].min() if not df_prod.empty else 0
        p_medio = df_prod["preco"].mean() if not df_prod.empty else 0
        p_maior = df_prod["preco"].max() if not df_prod.empty else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Preço Atual", f"R$ {p_atual:.2f}")
        c2.metric("Menor Preço Histórico", f"R$ {p_menor:.2f}")
        c3.metric("Preço Médio Histórico", f"R$ {p_medio:.2f}")
        c4.metric("Maior Preço Histórico", f"R$ {p_maior:.2f}")

        st.markdown("<br>", unsafe_allow_html=True)

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
            annotation_text=f"Preço Médio: R$ {p_medio:.2f}",
            annotation_position="bottom right"
        )

        fig.add_hline(
            y=p_menor,
            line_dash="dot",
            line_color="#10B981",
            annotation_text=f"Mínimo: R$ {p_menor:.2f}",
            annotation_position="top right"
        )

        fig.update_layout(
            title=f"Evolução de Preços - {produto_selecionado_nome}",
            xaxis_title="Data de Extração",
            yaxis_title="Preço (R$)",
            hovermode="x unified",
            template="plotly_white",
            height=500
        )

        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📋 Ver tabela detalhada do histórico de coletas"):
            cols_hist = [c for c in ["data_extracao", "preco", "preco_anterior", "variacao_pct"] if c in df_prod.columns]
            st.dataframe(
                df_prod[cols_hist].rename(columns={
                    "data_extracao": "Data/Hora Extração",
                    "preco": "Preço (R$)",
                    "preco_anterior": "Preço Anterior (R$)",
                    "variacao_pct": "Variação (%)"
                }),
                use_container_width=True,
                hide_index=True
            )