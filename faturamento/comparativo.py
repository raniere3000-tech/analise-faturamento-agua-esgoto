# -*- coding: utf-8 -*-
"""Comparativo mês atual x mês anterior por grupo (água e esgoto)."""
import numpy as np
import pandas as pd

from .formatacao import nome_mes, nome_mes_curto, ref_mais_recente


def agrega_por_grupo(df, rubrica):
    filtro = df[df["Rubrica"].str.contains(rubrica, case=False, na=False)].copy()

    # ------------------------------------------------------------------
    # Replica a regra do Excel: SOMASES(...; V; ">0")
    # Só considera Economias e Volume Faturado onde Consumo Faturado > 0
    # ------------------------------------------------------------------
    filtro_volume = filtro[filtro["Consumo Faturado"] > 0]

    agrupado_base = filtro.groupby("Grupo").agg(
        **{
            "Dias_Leitura": ("Qts. Dias", "mean"),
            "Faturamento": ("Valor (R$)", "sum"),
        }
    ).reset_index()

    agrupado_filtrado = filtro_volume.groupby("Grupo").agg(
        **{
            "Economias": ("Economias_Totais", "sum"),
            "Volume_Faturado": ("Consumo Faturado", "sum"),
        }
    ).reset_index()

    agrupado = agrupado_base.merge(agrupado_filtrado, on="Grupo", how="left")
    agrupado["Economias"] = agrupado["Economias"].fillna(0)
    agrupado["Volume_Faturado"] = agrupado["Volume_Faturado"].fillna(0)

    agrupado["Volume_Medio"] = agrupado["Volume_Faturado"] / agrupado["Economias"].replace(0, np.nan)
    agrupado["Tarifa_Media"] = agrupado["Faturamento"] / agrupado["Volume_Faturado"].replace(0, np.nan)
    agrupado["Ticket_Medio"] = agrupado["Faturamento"] / agrupado["Economias"].replace(0, np.nan)

    return agrupado.fillna(0)


def monta_comparativo(df_at, df_ant, rubrica):
    at = agrega_por_grupo(df_at, rubrica)
    ant = agrega_por_grupo(df_ant, rubrica)
    comp = at.merge(ant, on="Grupo", how="outer", suffixes=("_atual","_anterior")).fillna(0)
    return comp.sort_values("Grupo").reset_index(drop=True)


def define_referencias(ctx):
    """Define o mês atual (maior referência da base) e o anterior, e separa a base nos dois meses."""
    ctx.ref_atual = ref_mais_recente(ctx.base_final["Referencia de Leitura"].dropna().unique())
    data_atual = pd.to_datetime(ctx.ref_atual, format="%m/%Y")
    ctx.ref_anterior = (data_atual - pd.DateOffset(months=1)).strftime("%m/%Y")
    ctx.mes_atual = nome_mes(ctx.ref_atual)
    ctx.mes_anterior = nome_mes(ctx.ref_anterior)
    ctx.mes_atual_curto = nome_mes_curto(ctx.ref_atual)
    ctx.mes_anterior_curto = nome_mes_curto(ctx.ref_anterior)
    print(f"📅 {ctx.ref_anterior} ({ctx.mes_anterior}) vs {ctx.ref_atual} ({ctx.mes_atual})\n")
    ctx.df_atual = ctx.base_final[ctx.base_final["Referencia de Leitura"] == ctx.ref_atual].copy()
    ctx.df_anterior = ctx.base_final[ctx.base_final["Referencia de Leitura"] == ctx.ref_anterior].copy()


def calcula_comparativos(ctx):
    print("📊 Comparando Água...")
    ctx.comp_agua = monta_comparativo(ctx.df_atual, ctx.df_anterior, "AGUA")
    print(f"   {len(ctx.comp_agua)} grupos")
    print("📊 Comparando Esgoto...")
    ctx.comp_esgoto = monta_comparativo(ctx.df_atual, ctx.df_anterior, "ESGOTO")
    print(f"   {len(ctx.comp_esgoto)} grupos")
