# -*- coding: utf-8 -*-
"""Cálculos de análise: Top 100 quedas, resumo por grupo e consumo mínimo por matrícula."""
import os

import numpy as np
import pandas as pd

from .config import CONSUMO_MINIMO_POR_CATEGORIA, MINIMO_POR_TIPO_ECONOMIA
from .formatacao import normaliza_texto


_CACHE_COMP = {}          # (id das tabelas, rubrica) -> comparação por ligação (a parte cara do Top 100), reaproveitada


def _texto(serie):
    """str + strip calculado uma vez por valor distinto (bem mais rápido que .astype(str).str.strip() na coluna inteira)."""
    return serie.map({u: ("" if u is None or (isinstance(u, float) and u != u) else str(u).strip()) for u in serie.unique()})


def comparativo_ligacoes(df_at, df_ant, rubrica):
    """Uma linha por ligação que faturou a rubrica nos dois meses: consumo e valor de cada mês, nome, grupo, categoria,
    SUP e situação de lançamento. Calculado uma vez por par de tabelas e rubrica (cache)."""
    chave = (id(df_at), id(df_ant), len(df_at), len(df_ant), rubrica)
    if chave in _CACHE_COMP:
        return _CACHE_COMP[chave]
    com_sit = "Situacao Lancamento" in df_at.columns and "Situacao Lancamento" in df_ant.columns
    serv = "E" if "ESGOTO" in rubrica.upper() else "A"

    def lado(df, atual):
        filtro = (df["__serv"] == serv) if "__serv" in df.columns else df["Rubrica"].str.contains(rubrica, case=False, na=False)
        extras = ["Nome Cliente", "Grupo", "Categoria", "__sup"] if atual else []
        cols = [c for c in ["N. Ligação", "Consumo Faturado", "Valor (R$)", "Situacao Lancamento"] + extras if c in df.columns]
        d = df.loc[filtro, cols]                       # só as colunas usadas (não copia a tabela inteira)
        out = pd.DataFrame({"N. Ligação": _texto(d["N. Ligação"]),
                            "Consumo": pd.to_numeric(d["Consumo Faturado"], errors="coerce").fillna(0),
                            "Valor": pd.to_numeric(d["Valor (R$)"], errors="coerce").fillna(0),
                            "Sit": _texto(d["Situacao Lancamento"]) if com_sit else ""})
        aggs = {"Consumo": "sum", "Valor": "sum", "Sit": "first"}
        if atual:
            for c, nome in (("Nome Cliente", "Nome_Cliente"), ("Grupo", "Grupo"), ("Categoria", "Categoria"), ("__sup", "Superintendência")):
                out[nome] = _texto(d[c]) if c in d.columns else ""
                aggs[nome] = "first"
        return out.groupby("N. Ligação", sort=False).agg(aggs)

    at, ant = lado(df_at, True), lado(df_ant, False)
    comp = at.join(ant, how="inner", lsuffix="_Atual", rsuffix="_Anterior").reset_index()
    comp.attrs["com_sit"] = com_sit
    if len(_CACHE_COMP) > 8:
        _CACHE_COMP.clear()
    _CACHE_COMP[chave] = comp
    return comp


def gera_top100_quedas(df_at, df_ant, rubrica, ref_at, ref_ant, aumento=False, por_grupo=False, sup=None):
    """Top 100 ligações com maior queda de consumo (ou maior aumento, com `aumento=True`) entre os dois meses.
    sup: só as ligações dessa superintendência (None/TODAS = todas).
    por_grupo=True: as 100 maiores de CADA grupo, na ordem geral (+ coluna Superintendência) — o Top 100 de qualquer
    conjunto de grupos sai dessa lista, e é isso que o filtro de grupos usa no navegador."""
    base = comparativo_ligacoes(df_at, df_ant, rubrica)
    com_sit = base.attrs.get("com_sit", False)
    if sup and sup != "TODAS":
        base = base[base["Superintendência"] == sup]
    p = "Aumento" if aumento else "Queda"
    sinal = -1 if aumento else 1
    dif = sinal * (base["Consumo_Anterior"] - base["Consumo_Atual"])
    comp = base[dif > 0].copy()
    comp[f"{p}_Consumo"] = dif[dif > 0]
    ant_pos = comp["Consumo_Anterior"] > 0
    # no aumento, quem não consumia no mês anterior fica sem % (vazio), em vez de 0%
    comp[f"{p}_%"] = np.where(ant_pos, comp[f"{p}_Consumo"] / comp["Consumo_Anterior"].where(ant_pos, 1) * 100,
                              np.nan if aumento else 0)
    comp[f"{p}_Valor_R$"] = sinal * (comp["Valor_Anterior"] - comp["Valor_Atual"])
    comp = comp.sort_values(f"{p}_Consumo", ascending=False, kind="stable")
    comp = comp.groupby("Grupo", sort=False).head(100) if por_grupo else comp.head(100)
    comp["Ranking"] = range(1, len(comp) + 1)

    col_nome_at, col_nome_ant = f"Consumo {ref_at}", f"Consumo {ref_ant}"
    col_valor_at, col_valor_ant = f"Valor R$ {ref_at}", f"Valor R$ {ref_ant}"
    col_sit_at, col_sit_ant = f"Situação Lançamento {ref_at}", f"Situação Lançamento {ref_ant}"
    comp = comp.rename(columns={"Sit_Atual": col_sit_at, "Sit_Anterior": col_sit_ant,
                                "Consumo_Atual": col_nome_at, "Consumo_Anterior": col_nome_ant,
                                "Valor_Atual": col_valor_at, "Valor_Anterior": col_valor_ant})
    return comp[["Ranking", "N. Ligação", "Nome_Cliente", "Grupo", "Categoria"]
                + ([col_sit_at, col_sit_ant] if com_sit else [])
                + [col_nome_at, col_nome_ant, f"{p}_Consumo", f"{p}_%", col_valor_at, col_valor_ant, f"{p}_Valor_R$"]
                + (["Superintendência"] if por_grupo else [])].reset_index(drop=True)


def gera_top100_aumentos(df_at, df_ant, ref_at, ref_ant, sup=None):
    """(água, esgoto): Top 100 ligações com maior aumento de consumo."""
    print("📈 Calculando Top 100 clientes com maior aumento de consumo...")
    return tuple(gera_top100_quedas(df_at, df_ant, rub, ref_at, ref_ant, aumento=True, sup=sup) for rub in ("AGUA", "ESGOTO"))


def monta_dados_resumo_grupo(ctx):
    """Consolida água+esgoto por grupo para alimentar KPIs, gráfico, insights e tabela resumo."""
    print("📊 Montando dados de resumo consolidado por grupo...")
    resumo = ctx.comp_agua.merge(
        ctx.comp_esgoto, on="Grupo", how="outer", suffixes=("_agua", "_esgoto")
    ).fillna(0)

    resumo["FatAgua_Atual"] = resumo["Faturamento_atual_agua"]
    resumo["FatAgua_Anterior"] = resumo["Faturamento_anterior_agua"]
    resumo["FatEsgoto_Atual"] = resumo["Faturamento_atual_esgoto"]
    resumo["FatEsgoto_Anterior"] = resumo["Faturamento_anterior_esgoto"]
    resumo["Fat_Atual"] = resumo["FatAgua_Atual"] + resumo["FatEsgoto_Atual"]
    resumo["Fat_Anterior"] = resumo["FatAgua_Anterior"] + resumo["FatEsgoto_Anterior"]

    resumo["Eco_Atual"] = resumo[["Economias_atual_agua", "Economias_atual_esgoto"]].max(axis=1)
    resumo["Eco_Anterior"] = resumo[["Economias_anterior_agua", "Economias_anterior_esgoto"]].max(axis=1)

    resumo["VolFat_Atual"] = resumo["Volume_Faturado_atual_agua"]
    resumo["VolFat_Anterior"] = resumo["Volume_Faturado_anterior_agua"]

    if not ctx.df_minimo_por_grupo.empty:
        minimo = ctx.df_minimo_por_grupo[["Grupo", "Acima_Atual", "Acima_Ant"]].copy()
        resumo = resumo.merge(minimo, on="Grupo", how="left").fillna(0)
    else:
        resumo["Acima_Atual"] = 0
        resumo["Acima_Ant"] = 0

    # dias 0 = grupo sem leitura no mês (ou sem esgoto): não entra na média, senão puxa os dias para baixo
    for sufixo in ("atual", "anterior"):
        cols = [f"Dias_Leitura_{sufixo}_agua", f"Dias_Leitura_{sufixo}_esgoto"]
        resumo[f"Dias_Leitura_{sufixo.capitalize()}"] = resumo[cols].where(resumo[cols] > 0).mean(axis=1).fillna(0)

    colunas_finais = [
        "Grupo", "FatAgua_Atual", "FatAgua_Anterior", "FatEsgoto_Atual", "FatEsgoto_Anterior",
        "Fat_Atual", "Fat_Anterior", "Eco_Atual", "Eco_Anterior",
        "VolFat_Atual", "VolFat_Anterior", "Acima_Atual", "Acima_Ant",
        "Dias_Leitura_Atual", "Dias_Leitura_Anterior"
    ]
    return resumo[colunas_finais].sort_values("Grupo").reset_index(drop=True)


def calcula_minimo_matricula(linha):
    """Devolve o mínimo (m³) da matrícula, ou None se a categoria não tem mínimo cadastrado."""
    qtds = {c: float(linha.get(c, 0) or 0) for c in MINIMO_POR_TIPO_ECONOMIA}
    tipos_presentes = [c for c, q in qtds.items() if q > 0]
    if len(tipos_presentes) > 1:                      # ligação mista
        return sum(q * MINIMO_POR_TIPO_ECONOMIA[c] for c, q in qtds.items())
    minimo_cat = CONSUMO_MINIMO_POR_CATEGORIA.get(normaliza_texto(linha.get("Categoria", "")))
    if minimo_cat is None:
        return None
    return minimo_cat * sum(qtds.values())


def exporta_top100(df_atual, df_anterior, ref_atual, ref_anterior, caminho_saida):
    print("🏆 Calculando Top 100 clientes com maior queda de consumo...")

    top_agua_df = gera_top100_quedas(df_atual, df_anterior, "AGUA", ref_atual, ref_anterior)
    top_esg_df = gera_top100_quedas(df_atual, df_anterior, "ESGOTO", ref_atual, ref_anterior)

    from .tabelas_html import xlsx_bytes            # xlsxwriter ou openpyxl, o que estiver instalado
    os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)
    with open(caminho_saida, "wb") as f:
        f.write(xlsx_bytes({"Top100_Agua": top_agua_df, "Top100_Esgoto": top_esg_df}))

    print(f"✅ Top 100 quedas exportado para: {caminho_saida}")
    return top_agua_df, top_esg_df


def minimo_matricula_vetorizado(df):
    """Mesma regra de `calcula_minimo_matricula`, para a tabela inteira de uma vez (NaN = categoria sem mínimo)."""
    tipos = list(MINIMO_POR_TIPO_ECONOMIA)
    qtds = df[tipos].astype(float)
    mista = (qtds > 0).sum(axis=1) > 1
    minimo_misto = sum(qtds[c] * MINIMO_POR_TIPO_ECONOMIA[c] for c in tipos)
    cats = df["Categoria"].fillna("")
    unicas = cats.unique()
    minimo_cat = cats.map({c: CONSUMO_MINIMO_POR_CATEGORIA.get(normaliza_texto(c)) for c in unicas}).astype(float)
    return minimo_misto.where(mista, minimo_cat * qtds.sum(axis=1))
