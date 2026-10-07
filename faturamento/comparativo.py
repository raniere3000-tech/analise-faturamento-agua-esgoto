# -*- coding: utf-8 -*-
"""Comparativo mês atual x mês anterior por grupo (água e esgoto)."""
import numpy as np
import pandas as pd

from .formatacao import nome_mes, nome_mes_curto, ref_mais_recente


def agrega_por_grupo(df, rubrica):
    if "__serv" in df.columns:
        filtro = df[df["__serv"] == ("E" if "ESGOTO" in rubrica.upper() else "A")]
    else:
        filtro = df[df["Rubrica"].str.contains(rubrica, case=False, na=False)]

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


def _num_grupo(g):
    g = str(g).strip()
    return int(g) if g.isdigit() else None


def limita_ao_ultimo_grupo(ctx):
    """Só entram na análise os grupos até o último que faturou na última referência.

    Ex.: se a última referência só tem faturamento dos grupos 01 a 05, os demais grupos (que ainda não
    faturaram) ficam de fora também nos outros meses, para a comparação ser entre os mesmos grupos."""
    base = ctx.base_final
    ctx.base_completa = base          # base inteira (todos os grupos): a previsão de fechamento projeta os grupos que faltam
    atual = base[base["Referencia de Leitura"] == ctx.ref_atual]
    com_fat = atual[pd.to_numeric(atual["Valor (R$)"], errors="coerce").fillna(0) != 0]
    nums = [n for n in (_num_grupo(g) for g in com_fat["Grupo"].unique()) if n is not None]
    ctx.ultimo_grupo = ""
    if not nums:
        return
    ultimo = max(nums)
    largura = max(len(str(g)) for g in com_fat["Grupo"].unique() if _num_grupo(g) is not None)
    ctx.ultimo_grupo = str(ultimo).zfill(largura)
    grupos = base["Grupo"]
    manter = grupos.map({g: _num_grupo(g) is None or _num_grupo(g) <= ultimo for g in grupos.unique()}).astype(bool)
    removidas = int((~manter).sum())
    if not removidas:                                 # nada a tirar: usa a mesma tabela (sem copiar 2 milhões de linhas)
        ctx.base_final = base
    else:
        ctx.base_final = base[manter]
    print(f"🔎 Último grupo faturado em {ctx.ref_atual}: {ctx.ultimo_grupo} — análise limitada aos grupos até esse "
          f"({removidas} linhas de grupos posteriores desconsideradas)")


def define_referencias(ctx):
    """Define o mês atual (maior referência da base) e o anterior, e separa a base nos dois meses."""
    ctx.ref_atual = ref_mais_recente(ctx.base_final["Referencia de Leitura"].dropna().unique())
    data_atual = pd.to_datetime(ctx.ref_atual, format="%m/%Y")
    ctx.ref_anterior = (data_atual - pd.DateOffset(months=1)).strftime("%m/%Y")
    limita_ao_ultimo_grupo(ctx)
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
