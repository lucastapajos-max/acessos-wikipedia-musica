"""Camada analítica: SQL no SQLite, pandas e os testes estatísticos.

Três perguntas, uma função cada:
  - faixa_normal(): a semana está dentro do padrão do próprio banco? (mediana + IQR)
  - picos():        que dias fugiram muito do normal? (z-score robusto com MAD)
  - welch():        bancos digitais têm mais atenção que tradicionais? (teste t de Welch)

Princípio: amostra pequena não vira conclusão. Abaixo do mínimo, a função
devolve None e o app avisa que não dá para dizer.
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

DB = Path(__file__).parent / "data" / "atencao.db"
MIN_SEMANAS_FAIXA = 8   # semanas de histórico para definir o "normal"
MIN_DIAS_PICO = 60      # dias de histórico para julgar um pico
MIN_BANCOS = 4          # bancos por grupo para comparar grupos
JANELA_FAIXA = 26       # semanas de histórico que definem o normal
MIN_BASE_PICO = 5       # dia típico com menos acessos que isso não julga pico (verbete quase sem leitura)
LIMITE_IQR = 1.5        # fora de Q1-1,5·IQR e Q3+1,5·IQR é fora do normal (critério do boxplot)

# Semana de segunda a domingo. 'weekday 0' leva ao domingo; -6 dias volta à segunda.
SQL_SEMANAL = """
SELECT b.banco, b.grupo,
       date(p.data, 'weekday 0', '-6 days') AS semana,
       SUM(p.views) AS views
FROM pageviews p JOIN bancos b USING (artigo)
GROUP BY b.banco, b.grupo, semana
ORDER BY semana
"""

SQL_DIARIO = """
SELECT b.banco, b.grupo, p.data, p.views
FROM pageviews p JOIN bancos b USING (artigo)
ORDER BY p.data
"""


def consultar(sql, db=DB, params=()):
    with sqlite3.connect(db) as con:
        return pd.read_sql_query(sql, con, params=params)


def faixa_normal(historico, valor):
    """Mediana e IQR das semanas anteriores; limites em Q1-1,5·IQR e Q3+1,5·IQR."""
    s = pd.Series(historico, dtype=float).dropna()
    if len(s) < MIN_SEMANAS_FAIXA or valor is None or pd.isna(valor):
        return None
    q1, med, q3 = s.quantile(.25), s.median(), s.quantile(.75)
    iqr = q3 - q1
    lo, hi = q1 - LIMITE_IQR * iqr, q3 + LIMITE_IQR * iqr
    if valor > hi:
        status = "acima do normal"
    elif valor < lo:
        status = "abaixo do normal"
    else:
        status = "dentro do normal"
    return {"status": status, "valor": float(valor), "mediana": float(med),
            "q1": float(q1), "q3": float(q3), "lim_inf": float(max(lo, 0)),
            "lim_sup": float(hi), "n_semanas": len(s),
            "vs_mediana_pct": (valor - med) / med * 100 if med else None}


def faixa_rolante(views):
    """A mesma faixa de faixa_normal(), semana a semana, para desenhar no gráfico da série."""
    roll = pd.Series(views, dtype=float).rolling(JANELA_FAIXA, min_periods=MIN_SEMANAS_FAIXA)
    q1, q3 = roll.quantile(.25).shift(1), roll.quantile(.75).shift(1)
    return pd.DataFrame({"q1": q1, "q3": q3, "lim_sup": q3 + LIMITE_IQR * (q3 - q1)})


def radar_semana(semanal, semana, janela=JANELA_FAIXA):
    """Aplica a faixa_normal a cada banco na `semana`, contra as `janela` anteriores."""
    linhas = []
    for (banco, grupo), g in semanal.groupby(["banco", "grupo"]):
        atual = g.loc[g["semana"] == semana, "views"]
        hist = g.loc[g["semana"] < semana, "views"].tail(janela)
        r = faixa_normal(hist, atual.iloc[0] if len(atual) else None)
        if r:
            linhas.append({"banco": banco, "grupo": grupo, **r})
    return pd.DataFrame(linhas)


def picos(diario, z_corte=3.5, janela=90):
    """Dias com views muito acima do padrão dos `janela` dias anteriores do banco.

    Mediana e MAD em vez de média e desvio padrão: um único dia de pico infla a
    média e esconde os outros. Trabalha em log, porque a atenção cresce aos saltos.
    """
    saida = []
    for (banco, grupo), g in diario.groupby(["banco", "grupo"]):
        # A API omite dias com zero views; sem preencher, a janela de 90 linhas cobriria
        # mais de 90 dias e o dia típico sairia mais alto do que é.
        g = g.assign(data=pd.to_datetime(g["data"])).set_index("data")["views"]
        g = (g.reindex(pd.date_range(g.index.min(), g.index.max()), fill_value=0)
             .rename_axis("data").reset_index().assign(banco=banco, grupo=grupo))
        lv = np.log1p(g["views"].astype(float))
        med = lv.rolling(janela, min_periods=MIN_DIAS_PICO).median().shift(1)
        mad = lv.rolling(janela, min_periods=MIN_DIAS_PICO).apply(
            lambda x: np.median(np.abs(x - np.median(x))), raw=True).shift(1)
        z = (lv - med) / (1.4826 * mad.replace(0, np.nan))
        g = g.assign(z=z, base=np.expm1(med))
        saida.append(g[(g["z"] >= z_corte) & (g["base"] >= MIN_BASE_PICO)])
    if not saida:
        return pd.DataFrame(columns=["banco", "grupo", "data", "views", "z", "base"])
    out = pd.concat(saida)
    out["vezes_base"] = out["views"] / out["base"]
    return out.sort_values("z", ascending=False)


def welch(semanal, grupo_a, grupo_b, semanas=12):
    """Compara a atenção média de dois grupos nas últimas `semanas`.

    Unidade de análise = banco (média do log das views semanais), para não
    tratar semanas do mesmo banco como observações independentes. Welch porque
    não supõe variâncias iguais entre os grupos.
    """
    ultimas = sorted(semanal["semana"].unique())[-semanas:]
    df = semanal[semanal["semana"].isin(ultimas)].copy()
    df["log_views"] = np.log10(df["views"].clip(lower=1))
    por_banco = df.groupby(["grupo", "banco"])["log_views"].mean()
    if grupo_a not in por_banco.index or grupo_b not in por_banco.index:
        return None
    a, b = por_banco[grupo_a], por_banco[grupo_b]
    if len(a) < MIN_BANCOS or len(b) < MIN_BANCOS:
        return None
    t, p = stats.ttest_ind(a, b, equal_var=False)
    dp = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
    return {"a": grupo_a, "b": grupo_b, "n_a": len(a), "n_b": len(b),
            "media_a": 10 ** a.mean(), "media_b": 10 ** b.mean(),  # médias geométricas
            "razao": 10 ** (a.mean() - b.mean()), "t": float(t), "p": float(p),
            "d": float((a.mean() - b.mean()) / dp) if dp else None,
            "semanas": len(ultimas), "significante": bool(p < 0.05),
            "pontos": por_banco.reset_index()}  # um ponto por banco, a unidade do teste
