# -*- coding: utf-8 -*-
"""Orçado por ciclo (grupo) da aba Diretas: Água e Esgoto, realizado × orçado RF e × orçado SUP.

Cada métrica tem o seu próprio peso por ciclo, separado para água e para esgoto:
  - Faturamento: média, nos últimos 3 meses, da participação do grupo no valor faturado (água ou esgoto) do mês.
  - Volume: idem, pela participação no volume faturado (Consumo Faturado, só onde > 0).
  - Economias: idem, pela participação nas economias faturadas (Economias_Totais, só onde Consumo Faturado > 0).
Orçado do ciclo = peso da métrica × orçado da DRE (diretas água/esgoto, volume e economias) do mês atual.
"""
import html

import pandas as pd

from .comparativo import agrega_por_grupo
from .dre import TODAS, _fontes, orcado
from .previsao import _refs_base, valores_grupo
from .tabelas_html import gera_tabela

RUBRICAS = (("Água", "AGUA", "dA", "volA", "ecoA"), ("Esgoto", "ESGOTO", "dE", "volE", "ecoE"))


METRICAS = ("valor", "volume", "economias")


def pesos_por_ciclo(ctx, rubrica_txt):
    """{métrica: {grupo: peso}} pela participação média do grupo nos últimos meses (cada métrica soma 1). Com cache."""
    cache = ctx.__dict__.setdefault("_cache_pesos", {})
    chave = (id(ctx.base_completa), ctx.ref_atual, rubrica_txt.upper())
    if chave not in cache:
        cache[chave] = _pesos_por_ciclo(ctx, rubrica_txt)
    return cache[chave]


def _pesos_por_ciclo(ctx, rubrica_txt):
    s = "E" if "ESGOTO" in rubrica_txt.upper() else "A"
    colunas = {"valor": "d" + s, "volume": "vol" + s, "economias": "eco" + s}
    refs = _refs_base(ctx)
    acum = {m: {} for m in METRICAS}
    n = {m: 0 for m in METRICAS}
    for r in refs:
        por_g = valores_grupo(ctx, r, TODAS)
        for m, col in colunas.items():
            total = sum(v[col] for v in por_g.values())
            if not total:
                continue
            n[m] += 1
            for g, v in por_g.items():
                acum[m][g] = acum[m].get(g, 0.0) + v[col] / total
    return {m: {g: v / n[m] for g, v in acum[m].items()} if n[m] else {} for m in METRICAS}


def _realizado_por_grupo(ctx, rubrica_txt):
    """Realizado do mês atual por grupo (todos os grupos), calculado uma vez por serviço."""
    cache = ctx.__dict__.setdefault("_cache_real_ciclo", {})
    chave = (id(ctx.base_completa), ctx.ref_atual, rubrica_txt.upper())
    if chave not in cache:
        base = ctx.base_completa
        atual = base[base["Referencia de Leitura"] == ctx.ref_atual].copy()
        atual["Grupo"] = atual["Grupo"].astype(str).str.strip()
        cache[chave] = agrega_por_grupo(atual, rubrica_txt).set_index("Grupo") if len(atual) else pd.DataFrame()
    return cache[chave]


def comparativo_orcado(ctx, rotulo_rubrica, rubrica_txt, k_fat, k_vol, k_eco, orc):
    """DataFrame no formato do comparativo: *_atual = realizado do mês, *_anterior = orçado do ciclo."""
    pesos = pesos_por_ciclo(ctx, rubrica_txt)
    real = _realizado_por_grupo(ctx, rubrica_txt)
    grupos = sorted(set().union(*pesos.values()) | set(real.index))
    linhas = []
    for g in grupos:
        r = real.loc[g] if g in real.index else None
        fat_o, vol_o, eco_o = (pesos[m].get(g, 0.0) * (orc.get(k) or 0.0)
                               for m, k in (("valor", k_fat), ("volume", k_vol), ("economias", k_eco)))
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
    """Duas tabelas (Água e Esgoto por ciclo) contra o orçado escolhido no seletor da própria seção.
    Cada planilha gera seu par de tabelas; o seletor mostra só o par da planilha escolhida."""
    if getattr(ctx, "base_completa", None) is None or not len(ctx.orcado):
        return ""
    fontes, _ = _fontes(ctx)
    fontes = [f for f in fontes if "SUP" not in f.upper()] + [f for f in fontes if "SUP" in f.upper()]
    blocos = []
    for f in fontes:
        orc = orcado(ctx, f, TODAS, ctx.ref_atual)
        if not orc or all(orc.get(k) is None for k in ("dA", "dE")):
            continue
        tabelas = ""
        for rotulo, rub, kf, kv, ke in RUBRICAS:
            comp = comparativo_orcado(ctx, rotulo, rub, kf, kv, ke, orc)
            if not len(comp):
                continue
            slug = "orc-" + rub.lower() + "-" + "".join(c for c in f.lower() if c.isalnum())
            tabelas += gera_tabela(ctx, comp, f"{rotulo} por ciclo — Realizado × Orçado {html.escape(f)} ({ctx.mes_atual})", slug,
                                   com_dias=False, rot_atual="Realizado", rot_ant="Orçado")
        if tabelas:
            blocos.append((f, tabelas))
    if not blocos:
        return ""
    e = lambda v: html.escape(v, quote=True)
    opcoes = "".join(f'<option value="{e(f)}">{html.escape(f)}</option>' for f, _ in blocos)
    seletor = ('<div class="barra-orcado-ciclo"><label>Orçado por ciclo — comparar com '
               f'<select id="selOrcCiclo" onchange="selecionarOrcadoCiclo(this.value)">{opcoes}</select></label>'
               '<p class="nota-secao">Orçado de cada grupo de leitura = orçado do mês × peso do grupo. Cada métrica tem o seu peso, separado '
               'para água e esgoto: faturamento pela participação do grupo no valor faturado, volume pela participação no volume e '
               'economias pela participação nas economias (média dos últimos 3 meses).</p></div>')
    corpo = "".join(f'<div class="orc-ciclo-bloco" data-orc-ciclo="{e(f)}"{"" if i == 0 else " hidden"}>{t}</div>'
                    for i, (f, t) in enumerate(blocos))
    return seletor + corpo
