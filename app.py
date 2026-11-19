"""Painel: radar de atenção a bancos na Wikipédia (pageviews da Wikimedia)."""
import sqlite3

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import analise as an

st.set_page_config(page_title="Radar de atenção · bancos", page_icon=":material/monitoring:", layout="wide")

# Legendas e links com contraste de leitura (o cinza padrão fica abaixo de 4,5:1) e texto
# corrido com no máximo ~75 caracteres por linha. Tabelas e gráficos não são afetados.
st.markdown("""<style>
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * { color: #a9b2ae !important; opacity: 1 !important; }
[data-testid="stCaptionContainer"] a, [data-testid="stMarkdownContainer"] a { color: #6fd0c0 !important; opacity: 1 !important; }
[data-testid="stMarkdownContainer"] p, [data-testid="stCaptionContainer"] p { max-width: 62ch; text-wrap: pretty; }
:focus-visible { outline: 2px solid #3FB5A2 !important; outline-offset: 2px; }
</style>""", unsafe_allow_html=True)
# O Streamlit marca toda página como inglês; leitor de tela precisa saber que é pt-BR (WCAG 3.1.1).
components.html("<script>window.parent.document.documentElement.lang = 'pt-BR'</script>", height=0)

# Uma cor por grupo no app inteiro. Vermelho fica de fora: aqui ele leria como alerta.
CORES = {"Digital": "#3FB5A2", "Tradicional": "#6E95E6"}
STATUS_FUNDO = {"acima do normal": "rgba(63,181,162,.28)", "abaixo do normal": "rgba(224,162,58,.28)"}
LIMITE_PASSOS_SQL = 20_000_000  # passos internos do SQLite antes de interromper (~1 s)
LIMITE_LINHAS_SQL = 1_000
NUM = "localized"  # separador de milhar conforme o idioma do navegador


@st.cache_data
def carregar():
    sem, dia = an.consultar(an.SQL_SEMANAL), an.consultar(an.SQL_DIARIO)
    dia["data"] = pd.to_datetime(dia["data"])
    return sem, dia


@st.cache_data
def picos_de(grupos):
    """Picos dos grupos escolhidos; o cálculo leva ~0,7 s, então só roda quando o filtro muda."""
    dia = carregar()[1]
    return an.picos(dia[dia["grupo"].isin(grupos)])


def br(v, casas=0):
    return f"{v:,.{casas}f}".replace(",", "x").replace(".", ",").replace("x", ".")


def lista(nomes):
    nomes = list(nomes)
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def grafico(fig, altura=360):
    fig.update_layout(height=altura, margin=dict(t=10, b=10, l=10, r=10),
                      legend=dict(orientation="h", y=-0.15, title=None))
    st.plotly_chart(fig, width="stretch")


semanal, diario = carregar()
semanas = sorted(semanal["semana"].unique())

def rotulo_semana(s):
    ini = pd.to_datetime(s)
    return f"{ini:%d/%m} a {ini + pd.Timedelta(days=6):%d/%m/%Y}"


st.title("Radar de atenção: bancos")
st.markdown("Quando um pico de atenção merece ação, e quando é só oscilação?")
st.caption(
    f"Acessos diários aos verbetes de {semanal['banco'].nunique()} bancos, digitais e tradicionais, na Wikipédia "
    f"em português, de {diario['data'].min():%d/%m/%Y} a "
    f"{diario['data'].max():%d/%m/%Y}. Atualizado toda segunda. Fonte: Wikimedia Pageviews API "
    "(dados abertos, CC0), só acessos humanos.")

with st.sidebar:
    semana = st.selectbox("Semana", semanas[::-1], format_func=rotulo_semana)
    grupos = st.multiselect("Grupos", list(CORES), default=list(CORES))
    st.caption("Agrupamento deste projeto, não uma classificação oficial.")

if not grupos:
    st.info("Escolha ao menos um grupo na barra lateral para ver o painel.")
    st.stop()

sem = semanal[semanal["grupo"].isin(grupos)]
radar = an.radar_semana(sem, semana)
fim_semana = pd.to_datetime(semana) + pd.Timedelta(days=6)

aba1, aba2, aba3, aba4 = st.tabs(["Radar da semana", "Picos de acesso", "Digitais x tradicionais (teste t)", "SQL"])

# --- Radar --------------------------------------------------------------------
with aba1:
    if radar.empty:
        st.info("Esta semana ainda não tem 8 semanas de histórico antes dela para definir o normal. "
                "Escolha uma semana mais recente.")
    else:
        total = sem.loc[sem["semana"] == semana, "views"].sum()
        hist_total = sem[sem["semana"] < semana].groupby("semana")["views"].sum().tail(26)
        bt = an.faixa_normal(hist_total, total)
        acima = radar[radar["status"] == "acima do normal"].sort_values("vs_mediana_pct", ascending=False)
        abaixo = radar[radar["status"] == "abaixo do normal"].sort_values("vs_mediana_pct")
        frases = [f"Semana de {pd.to_datetime(semana):%d/%m} a {fim_semana:%d/%m/%Y}: "
                  f"**{br(total)} acessos** nos grupos escolhidos"]
        if bt:
            frases[0] += (f", {br(abs(bt['vs_mediana_pct']))}% {'acima' if bt['vs_mediana_pct'] >= 0 else 'abaixo'} "
                          f"da mediana das 26 semanas anteriores ({bt['status']}).")
        else:
            frases[0] += "."
        frases.append(f"Acima do normal: {lista(acima['banco'])}." if len(acima)
                      else "Nenhum banco ficou acima do normal.")
        frases.append(f"Abaixo do normal: {lista(abaixo['banco'])}." if len(abaixo)
                      else "Nenhum ficou abaixo.")
        st.markdown(" ".join(frases))

        tab = radar.assign(mediana=radar["mediana"].round()).sort_values("vs_mediana_pct", ascending=False)[
            ["banco", "grupo", "status", "valor", "mediana", "vs_mediana_pct"]]
        st.dataframe(
            tab.style.map(lambda s: f"background-color: {STATUS_FUNDO.get(s, 'transparent')}", subset=["status"]),
            hide_index=True, width="stretch",
            column_config={
                "banco": "Banco", "grupo": "Grupo", "status": "Leitura",
                "valor": st.column_config.NumberColumn("Acessos na semana", format=NUM),
                "mediana": st.column_config.NumberColumn("Mediana 26 sem.", format=NUM),
                "vs_mediana_pct": st.column_config.NumberColumn("vs mediana", format="%+.0f%%"),
            })
        st.caption("O normal de cada banco é a faixa das 26 semanas anteriores (mediana e intervalo "
                   "interquartil). Fica acima do normal quem passa de Q3 + 1,5 × IQR, o critério do boxplot.")

        banco = st.selectbox("Série semanal de um banco", tab["banco"])
        g = sem[sem["banco"] == banco].sort_values("semana").copy()
        g = g.join(an.faixa_rolante(g["views"]))
        cor = CORES[g["grupo"].iloc[0]]
        fig = go.Figure([
            go.Scatter(x=g["semana"], y=g["q3"], line=dict(width=0), showlegend=False, hoverinfo="skip"),
            go.Scatter(x=g["semana"], y=g["q1"], fill="tonexty", line=dict(width=0),
                       fillcolor="rgba(128,128,128,.22)", name="Faixa usual (Q1 a Q3)", hoverinfo="skip"),
            go.Scatter(x=g["semana"], y=g["lim_sup"], line=dict(dash="dot", color="gray", width=1),
                       name="Limite do normal", hovertemplate="%{y:,.0f}<extra>Limite</extra>"),
            go.Scatter(x=g["semana"], y=g["views"], line=dict(color=cor, width=2), name="Acessos na semana",
                       hovertemplate="%{x|%d/%m/%Y}: %{y:,.0f}<extra></extra>"),
        ])
        fig.add_vline(x=semana, line_color="gray", line_width=1, line_dash="dash")
        fig.update_layout(separators=",.", hovermode="x unified")
        grafico(fig, 380)

# --- Picos --------------------------------------------------------------------
with aba2:
    pk = picos_de(tuple(grupos))
    if pk.empty:
        st.info("Nenhum dia atípico nos grupos escolhidos.")
    else:
        maior = pk.iloc[0]
        na_semana = pk[(pk["data"] >= pd.to_datetime(semana)) & (pk["data"] <= fim_semana)]
        resumo = (f"Maior salto do período: **{maior['banco']}** em {maior['data']:%d/%m/%Y}, "
                  f"com {br(maior['vezes_base'], 1)} vezes os acessos de um dia típico. ")
        if len(na_semana):
            dias = na_semana.sort_values("data")
            resumo += (f"Na semana de {rotulo_semana(semana)}: "
                       + lista(f"{r.banco} ({r.data:%d/%m}, {br(r.vezes_base, 1)} vezes)" for r in dias.itertuples())
                       + ".")
        else:
            resumo += f"Na semana de {rotulo_semana(semana)}, nenhum banco teve um dia fora do padrão."
        st.markdown(resumo)
        with st.expander("Como calculei"):
            st.markdown(
                "Um pico é um dia em que o banco teve muito mais acessos que o próprio padrão "
                "dos 90 dias anteriores. A régua é a mediana desses dias, e a distância é medida pelo "
                "desvio absoluto mediano (MAD), em escala logarítmica, com corte em 3,5. Mediana e MAD "
                "não se deixam distorcer por um único dia viral, como média e desvio padrão se deixariam.\n\n"
                "Pico de um dia que não tira a semana da faixa (aba Radar) costuma ser oscilação: "
                "uma notícia que passa. Quando a semana inteira sai do normal, a atenção mudou de "
                "patamar, e aí vale investigar o motivo.")
        top = st.slider("Quantos picos mostrar", 5, 50, 15)
        st.dataframe(
            pk.head(top).round({"base": 0, "vezes_base": 1})[["data", "banco", "grupo", "views", "base", "vezes_base"]],
            hide_index=True, width="stretch",
            column_config={
                "data": st.column_config.DateColumn("Dia", format="DD/MM/YYYY"),
                "banco": "Banco", "grupo": "Grupo",
                "views": st.column_config.NumberColumn("Acessos no dia", format=NUM),
                "base": st.column_config.NumberColumn("Dia típico", format=NUM, help="Mediana dos 90 dias anteriores"),
                "vezes_base": st.column_config.NumberColumn("Vezes o dia típico", format=NUM),
            })
        st.caption(f"{br(len(pk))} dias atípicos no período, somando os bancos filtrados. O dado mostra "
                   "quando os acessos saltaram; o porquê (notícia, campanha, instabilidade) pede checagem em notícias.")
        fig = px.scatter(pk, x="data", y="vezes_base", color="grupo", hover_name="banco", log_y=True,
                         color_discrete_map=CORES, category_orders={"grupo": list(CORES)},
                         labels={"data": "", "vezes_base": "Vezes o dia típico (log)", "grupo": "Grupo"},
                         hover_data={"data": "|%d/%m/%Y", "vezes_base": ":.1f", "grupo": False})
        fig.add_vrect(x0=pd.to_datetime(semana), x1=fim_semana + pd.Timedelta(days=1),
                      fillcolor="gray", opacity=.25, line_width=0,
                      annotation_text="semana escolhida", annotation_position="top left")
        fig.update_layout(separators=",.")
        grafico(fig)

# --- Welch --------------------------------------------------------------------
with aba3:
    st.markdown("Bancos digitais têm mais acessos que os tradicionais, ou a diferença cabe no acaso?")
    ga, gb = list(CORES)
    r = None
    if len(grupos) < 2:
        st.info("Para comparar, deixe os dois grupos marcados na barra lateral.")
    else:
        janela = st.slider("Janela (semanas)", 4, 52, 12)
        r = an.welch(semanal, ga, gb, janela)
        if r is None:
            st.info(f"Amostra insuficiente: são precisos ao menos {an.MIN_BANCOS} bancos por grupo.")
    if r:
        mais, menos = (ga, gb) if r["razao"] >= 1 else (gb, ga)
        razao = max(r["razao"], 1 / r["razao"])
        veredito = ("A diferença é estatisticamente significante (p < 0,05)." if r["significante"]
                    else "Com essa amostra, não dá para afirmar que a diferença não é acaso (p ≥ 0,05).")
        st.markdown(
            f"Na média geométrica, um banco do grupo **{mais}** teve **{br(razao, 1)} vezes** os acessos "
            f"semanais de um banco do grupo **{menos}** nas últimas {r['semanas']} semanas. {veredito}")
        st.caption(f"Base: {r['n_a']} bancos digitais e {r['n_b']} tradicionais. Com grupos tão pequenos, o "
                   "teste só enxerga diferenças grandes: quando ele não acha diferença, quer dizer \"não "
                   "deu para ver\", não \"são iguais\". Acesso ao verbete mede curiosidade, não clientes.")
        with st.expander("Como calculei"):
            st.markdown(
                "Cada banco vira um ponto: a média do log dos acessos semanais na janela "
                "escolhida. Assim, 12 semanas do mesmo banco não contam como 12 casos independentes. "
                "O teste t de Welch compara os dois grupos sem supor que eles variem do mesmo jeito.\n\n"
                f"p-valor **{br(r['p'], 3)}** (abaixo de 0,05, a diferença dificilmente é acaso) · "
                f"t de Welch **{br(r['t'], 2)}** · tamanho do efeito, d de Cohen, **{br(r['d'], 2)}** "
                "(a partir de 0,8 em módulo, a diferença é considerada grande)")
        ult = sorted(semanal["semana"].unique())[-janela:]
        pts = (semanal[semanal["semana"].isin(ult)]
               .assign(log=lambda d: np.log10(d["views"].clip(lower=1)))
               .groupby(["grupo", "banco"])["log"].mean().reset_index()
               .assign(views=lambda d: 10 ** d["log"]))
        fig = px.box(pts, x="grupo", y="views", color="grupo", points="all", hover_name="banco",
                     log_y=True, color_discrete_map=CORES, category_orders={"grupo": [ga, gb]},
                     labels={"grupo": "", "views": "Acessos semanais (média geométrica, log)"},
                     hover_data={"grupo": False, "views": ":,.0f"})
        fig.update_layout(showlegend=False, separators=",.")
        grafico(fig)

# --- SQL ----------------------------------------------------------------------
with aba4:
    st.markdown("Os dados ficam num banco SQLite com duas tabelas, `bancos` e `pageviews`. "
                "A agregação semanal do painel sai desta consulta:")
    st.code(an.SQL_SEMANAL.strip(), language="sql")
    st.caption("A consulta enxerga o banco inteiro: os filtros da barra lateral não se aplicam aqui.")
    q = st.text_area("Escreva outra consulta (o banco abre só para leitura)",
                     "SELECT b.grupo, COUNT(DISTINCT b.artigo) AS bancos, SUM(p.views) AS views\n"
                     "FROM pageviews p JOIN bancos b USING (artigo)\n"
                     "WHERE p.data >= date((SELECT MAX(data) FROM pageviews), '-29 days')\n"
                     "GROUP BY b.grupo\nORDER BY views DESC",
                     height=140)
    if st.button("Rodar consulta", type="primary"):
        try:
            with sqlite3.connect(f"file:{an.DB.as_posix()}?mode=ro", uri=True) as con:
                # O app é um processo só para todos os visitantes: consulta pesada é interrompida,
                # ATTACH (que criaria arquivo no servidor) é negado e só as primeiras linhas aparecem.
                con.set_progress_handler(lambda: 1, LIMITE_PASSOS_SQL)
                con.set_authorizer(lambda acao, *_: sqlite3.SQLITE_DENY if acao == sqlite3.SQLITE_ATTACH
                                   else sqlite3.SQLITE_OK)
                cur = con.execute(q)
                linhas = cur.fetchmany(LIMITE_LINHAS_SQL + 1)
                res = pd.DataFrame(linhas[:LIMITE_LINHAS_SQL], columns=[c[0] for c in cur.description or []])
            st.dataframe(res, hide_index=True, width="stretch")
            if len(linhas) > LIMITE_LINHAS_SQL:
                st.caption(f"Mostrando as primeiras {br(LIMITE_LINHAS_SQL)} linhas.")
        except Exception as e:  # erro de SQL do visitante: mostra em vez de quebrar o app
            st.error(f"A consulta não rodou: {e}. Confira os nomes das tabelas e colunas acima.")

st.divider()
st.caption("Projeto de portfólio de Lucas Tapajós · [código no GitHub](https://github.com/lucastapajos-max/radar-atencao-bancos) · "
           "metodologia descrita no README.")
