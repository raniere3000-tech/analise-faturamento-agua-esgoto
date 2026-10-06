# -*- coding: utf-8 -*-
"""Cálculos de análise: Top 100 quedas, resumo por grupo e consumo mínimo por matrícula."""
import os

import numpy as np
import pandas as pd

from .config import CONSUMO_MINIMO_POR_CATEGORIA, MINIMO_POR_TIPO_ECONOMIA
from .formatacao import normaliza_texto


def gera_top100_quedas(df_at, df_ant, rubrica, ref_at, ref_ant, aumento=False):
    """Top 100 ligações com maior queda de consumo (ou maior aumento, com `aumento=True`) entre os dois meses."""
    def prepara(df):
        df = df.copy()
        df["N. Ligação"] = df["N. Ligação"].astype(str).str.strip()
        df["Nome_Cliente"] = df.get("Nome Cliente", pd.Series(dtype=str)).astype(str).str.strip()
        df["Grupo"] = df.get("Grupo", pd.Series(dtype=str)).astype(str).str.strip()
        df["Categoria"] = df.get("Categoria", pd.Series(dtype=str)).astype(str).str.strip()
        df["Consumo_Num"] = pd.to_numeric(df.get("Consumo Faturado", 0), errors="coerce").fillna(0)
        df["Valor_Num"] = pd.to_numeric(df.get("Valor (R$)", 0), errors="coerce").fillna(0)
        return df

    at = prepara(df_at[df_at["Rubrica"].str.contains(rubrica, case=False, na=False)])
    ant = prepara(df_ant[df_ant["Rubrica"].str.contains(rubrica, case=False, na=False)])

    at_group = at.groupby("N. Ligação").agg(
        **{
            "Nome_Cliente": ("Nome_Cliente", "first"),
            "Grupo": ("Grupo", "first"),
            "Categoria": ("Categoria", "first"),
            "Consumo_Atual": ("Consumo_Num", "sum"),
            "Valor_Atual": ("Valor_Num", "sum"),
        }
    ).reset_index()

    ant_group = ant.groupby("N. Ligação").agg(
        **{
            "Consumo_Anterior": ("Consumo_Num", "sum"),
            "Valor_Anterior": ("Valor_Num", "sum")
        }
    ).reset_index()

    comp = at_group.merge(ant_group, on="N. Ligação", how="inner")
    p = "Aumento" if aumento else "Queda"
    sinal = -1 if aumento else 1
    comp[f"{p}_Consumo"] = sinal * (comp["Consumo_Anterior"] - comp["Consumo_Atual"])
    # no aumento, quem não consumia no mês anterior fica sem % (vazio), em vez de 0%
    comp[f"{p}_%"] = np.where(comp["Consumo_Anterior"] > 0, comp[f"{p}_Consumo"] / comp["Consumo_Anterior"].where(comp["Consumo_Anterior"] > 0, 1) * 100,
                              np.nan if aumento else 0)
    comp[f"{p}_Valor_R$"] = sinal * (comp["Valor_Anterior"] - comp["Valor_Atual"])
    comp = comp[comp[f"{p}_Consumo"] > 0]
    comp = comp.sort_values(f"{p}_Consumo", ascending=False).head(100)
    comp["Ranking"] = range(1, len(comp) + 1)

    col_nome_at = f"Consumo {ref_at}"
    col_nome_ant = f"Consumo {ref_ant}"
    col_valor_at = f"Valor R$ {ref_at}"
    col_valor_ant = f"Valor R$ {ref_ant}"

    comp = comp.rename(columns={
        "Consumo_Atual": col_nome_at,
        "Consumo_Anterior": col_nome_ant,
        "Valor_Atual": col_valor_at,
        "Valor_Anterior": col_valor_ant,
    })

    return comp[["Ranking", "N. Ligação", "Nome_Cliente", "Grupo", "Categoria",
        col_nome_at, col_nome_ant, f"{p}_Consumo", f"{p}_%",
        col_valor_at, col_valor_ant, f"{p}_Valor_R$"]]


def gera_top100_aumentos(df_at, df_ant, ref_at, ref_ant):
    """(água, esgoto): Top 100 ligações com maior aumento de consumo."""
    print("📈 Calculando Top 100 clientes com maior aumento de consumo...")
    return tuple(gera_top100_quedas(df_at, df_ant, rub, ref_at, ref_ant, aumento=True) for rub in ("AGUA", "ESGOTO"))


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

    resumo["Dias_Leitura_Atual"] = resumo[["Dias_Leitura_atual_agua", "Dias_Leitura_atual_esgoto"]].mean(axis=1)
    resumo["Dias_Leitura_Anterior"] = resumo[["Dias_Leitura_anterior_agua", "Dias_Leitura_anterior_esgoto"]].mean(axis=1)

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

    os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)
    with pd.ExcelWriter(caminho_saida, engine="xlsxwriter") as writer:
        top_agua_df.to_excel(writer, sheet_name="Top100_Agua", index=False)
        top_esg_df.to_excel(writer, sheet_name="Top100_Esgoto", index=False)

    print(f"✅ Top 100 quedas exportado para: {caminho_saida}")
    return top_agua_df, top_esg_df
