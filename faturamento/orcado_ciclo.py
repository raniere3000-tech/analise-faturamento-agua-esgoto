# -*- coding: utf-8 -*-
"""Orçado por ciclo (grupo) da aba Diretas: Água e Esgoto, realizado × orçado RF e × orçado SUP.

Peso do ciclo = média, nos últimos 3 meses, da participação do grupo no valor faturado (água ou esgoto) do mês.
Orçado do ciclo = peso × orçado da DRE (diretas água/esgoto, volume e economias) do mês atual.
"""
import html

import numpy as np
import pandas as pd

from .comparativo import agrega_por_grupo
from .dre import TODAS, _fontes, orcado
from .previsao import _refs_base
from .tabelas_html import gera_tabela

RUBRICAS = (("Água", "AGUA", "dA", "volA", "ecoA"), ("Esgoto", "ESGOTO", "dE", "volE", "ecoE"))


def pesos_por_ciclo(ctx, rubrica_txt):
    """{grupo: peso} pela participação média do grupo nos últimos meses (soma 1)."""
    base = ctx.base_completa
    refs = _refs_base(ctx)
    if not refs:
        return {}
    acum = {}
    for r in refs:
        d = base[(base["Referencia de Leitura"] == r) & base["Rubrica"].str.contains(rubrica_txt, case=False, na=False)]
        por_g = d.groupby(d["Grupo"].astype(str).str.strip())["Valor (R$)"].sum()
        total = por_g.sum()
        if not total:
            continue
        for g, v in por_g.items():
            acum[g] = acum.get(g, 0.0) + v / total
    n = len(refs)
    return {g: v / n for g, v in acum.items()}


def comparativo_orcado(ctx, rotulo_rubrica, rubrica_txt, k_fat, k_vol, k_eco, orc):
    """DataFrame no formato do comparativo: *_atual = realizado do mês, *_anterior = orçado do ciclo."""
    pesos = pesos_por_ciclo(ctx, rubrica_txt)
    base = ctx.base_completa
    atual = base[base["Referencia de Leitura"] == ctx.ref_atual].copy()
    atual["Grupo"] = atual["Grupo"].astype(str).str.strip()
    real = agrega_por_grupo(atual, rubrica_txt).set_index("Grupo") if len(atual) else pd.DataFrame()
    grupos = sorted(set(pesos) | set(real.index))
    linhas = []
    for g in grupos:
        w = pesos.get(g, 0.0)
        r = real.loc[g] if g in real.index else None
        fat_o, vol_o, eco_o = (w * (orc.get(k) or 0.0) for k in (k_fat, k_vol, k_eco))
        fat_r = float(r["Faturamento"]) if r is not None else 0.0
        eco_r = float(r["Economias"]) if r is not None else 0.0
        vol_r = float(r["Volume_Faturado"]) if r is not None else 0.0
        div = lambda a, b: a / b if b else 0.0
        linhas.append({
            "Grupo": g, "Dias_Leitura_atual": 0.0, "Dias_Leitura_anterior": 0.0,
            "Faturamento_atual": fat_r, "Faturamento_anterior": fat_o,
            "Economias_atual": eco_r, "Economias_anterior": eco_o,
            "Volume_Faturado_atual": vol_r, "Volume_Faturado_anterior": vol_o,
            "Volume_Medio_atual": div(vol_r, eco_r), "Volume_Medio_anterior": div(vol_o, eco_o),
            "Tarifa_Media_atual": div(fat_r, vol_r), "Tarifa_Media_anterior": div(fat_o, vol_o),
            "Ticket_Medio_atual": div(fat_r, eco_r), "Ticket_Medio_anterior": div(fat_o, eco_o),
        })
    return pd.DataFrame(linhas)


def gera_tabelas_orcado_ciclo_html(ctx):
    """Água e Esgoto por ciclo contra cada planilha de orçado (o filtro Referência escolhe quais aparecem)."""
    if getattr(ctx, "base_completa", None) is None or not len(ctx.orcado):
        return ""
    fontes, _ = _fontes(ctx)
    fontes = [f for f in fontes if "SUP" not in f.upper()] + [f for f in fontes if "SUP" in f.upper()]
    saida = ""
    for f in fontes:
        orc = orcado(ctx, f, TODAS, ctx.ref_atual)
        if not orc or all(orc.get(k) is None for k in ("dA", "dE")):
            continue
        for rotulo, rub, kf, kv, ke in RUBRICAS:
            comp = comparativo_orcado(ctx, rotulo, rub, kf, kv, ke, orc)
            if not len(comp):
                continue
            slug = "orc-" + rub.lower() + "-" + "".join(c for c in f.lower() if c.isalnum())
            saida += gera_tabela(ctx, comp, f"{rotulo} por ciclo — Realizado × Orçado {html.escape(f)} ({ctx.mes_atual})", slug,
                                 com_dias=False, rot_atual="Realizado", rot_ant="Orçado",
                                 card_attrs=f' data-src="{html.escape(f, quote=True)}"')
    return saida
