# -*- coding: utf-8 -*-
"""Previsão de fechamento do mês (aba DRE).

Fechamento = realizado até agora (grupos já faturados) + projeção do que falta.
  - Diretas (água/esgoto), economias e volume: cada grupo que ainda não faturou entra com a média dos
    últimos 3 meses desse mesmo grupo.
  - Indiretas (RI e esgoto indireto): ticket por dia útil (realizado ÷ dias úteis decorridos) × dias úteis que faltam;
    Cortes só contam dias úteis que não são sexta nem véspera de feriado.
  - Cancelamento: falta = média dos últimos 3 meses − realizado, nunca negativo.
A coluna "Forecast" (o que falta faturar) é editável no relatório; totais, médias e comparações são refeitos no navegador (relatorio.js).
"""
import calendar
import copy
import datetime as dt
import html

import pandas as pd

from .config import REGRAS
from .dre import (LINHAS, TODAS, _filtra, _fmt, _fontes, _nome_sup, _orcados_do_mes, _pct, realizado)
from .formatacao import fmt_num, nome_mes

MESES_BASE = 3
# linhas que o usuário edita (as demais são calculadas a partir delas)
LINHAS_BASICAS = ["dA", "dE", "iE", "ri_CORTE", "ri_RELIGAÇÃO", "ri_LNA", "ri_SANÇÃO", "ri_OUTROS", "ecoA", "ecoE", "volA", "volE", "canc"]
LINHAS_POR_GRUPO = ["dA", "dE", "ecoA", "ecoE", "volA", "volE"]


# ---------- dias úteis ----------
CLASSES_POR_DIA_UTIL = ["iE", "ri_CORTE", "ri_RELIGAÇÃO", "ri_LNA", "ri_SANÇÃO", "ri_OUTROS"]


def _pascoa(ano):
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(ano, mes, dia)


def feriados(ano):
    """Feriados nacionais, Sexta Santa e São Jorge (RJ), mais os de "feriados_extras" em regras.json (AAAA-MM-DD).
    Pontos facultativos (Carnaval, Corpus Christi, 28/10...) contam como dia útil."""
    p = _pascoa(ano)
    dias = [(1, 1), (21, 4), (23, 4), (1, 5), (7, 9), (12, 10), (2, 11), (15, 11), (20, 11), (25, 12)]
    fixos = {dt.date(ano, m, d) for d, m in dias}
    extras = set()
    for t in REGRAS.get("feriados_extras", []):
        try:
            extras.add(dt.date.fromisoformat(str(t).strip()))
        except ValueError:
            pass
    return fixos | {p - dt.timedelta(days=2)} | extras


def _eh_util(d, fer):
    return d.weekday() < 5 and d not in fer


def dias_uteis_do_mes(ref, corte):
    """Dias úteis do mês `ref` (MM/AAAA): total/decorridos até `corte` (inclusive) e os de corte (sem sextas e vésperas de feriado)."""
    m, a = int(ref[:2]), int(ref[3:])
    fer = feriados(a) | feriados(a + 1)
    dias = [dt.date(a, m, n) for n in range(1, calendar.monthrange(a, m)[1] + 1)]
    uteis = [d for d in dias if _eh_util(d, fer)]
    cortes = [d for d in uteis if d.weekday() != 4 and (d + dt.timedelta(days=1)) not in fer]
    f = lambda lista: (len(lista), sum(1 for d in lista if d <= corte))
    (tu, du), (tc, dc) = f(uteis), f(cortes)
    return {"uteis": tu, "uteis_decorridos": du, "uteis_faltam": tu - du,
            "corte": tc, "corte_decorridos": dc, "corte_faltam": tc - dc}


def _mes_deslocado(ref, n):
    m, a = int(ref[:2]), int(ref[3:])
    t = a * 12 + (m - 1) - n
    return f"{t % 12 + 1:02d}/{t // 12}"


def _refs_base(ctx):
    """Até 3 meses imediatamente anteriores ao atual que existem na base (do mais antigo ao mais novo)."""
    existentes = set(ctx.base_completa["Referencia de Leitura"].dropna())
    return [r for r in (_mes_deslocado(ctx.ref_atual, n) for n in range(MESES_BASE, 0, -1)) if r in existentes]


def _completo(ctx):
    """Cópia do contexto cuja base tem todos os grupos (para os meses anteriores inteiros)."""
    c = copy.copy(ctx)
    c.base_final = ctx.base_completa
    return c


def _por_grupo(df, rubrica_txt):
    d = df[df["Rubrica"].str.contains(rubrica_txt, case=False, na=False)]
    pos = d[d["Consumo Faturado"] > 0]
    return d, pos


def _valores_grupo(df_mes):
    """{grupo: {dA, dE, ecoA, ecoE, volA, volE}} de um mês (já filtrado por SUP)."""
    saida = {}
    for g, bloco in df_mes.groupby(df_mes["Grupo"].astype(str).str.strip()):
        r = {}
        for k, rub in (("A", "AGUA"), ("E", "ESGOTO")):
            d, pos = _por_grupo(bloco, rub)
            r["d" + k] = float(d["Valor (R$)"].sum())
            r["eco" + k] = float(pos["Economias_Totais"].sum())
            r["vol" + k] = float(pos["Consumo Faturado"].sum())
        saida[g] = r
    return saida


def calcula_previsao(ctx, sup):
    """Devolve dict com meses-base, realizado completo dos meses-base, realizado até agora, projeção e previsão."""
    refs = _refs_base(ctx)
    if not refs:
        return None
    cheio = _completo(ctx)
    meses = {r: realizado(cheio, sup, r) for r in refs}
    atual = realizado(ctx, sup, ctx.ref_atual)

    base = ctx.base_completa
    faturados = set(_filtra(base[base["Referencia de Leitura"] == ctx.ref_atual], sup)["Grupo"].astype(str).str.strip())
    por_mes = {r: _valores_grupo(_filtra(base[base["Referencia de Leitura"] == r], sup)) for r in refs}
    faltam = sorted({g for r in refs for g in por_mes[r]} - faturados)

    falta = {k: 0.0 for k in LINHAS_BASICAS}
    grupos = {}                                    # memória de cálculo: média de cada grupo que falta
    for g in faltam:
        meses_g = [r for r in refs if g in por_mes[r]]
        media = {k: sum(por_mes[r][g][k] for r in meses_g) / len(meses_g) for k in LINHAS_POR_GRUPO}
        grupos[g] = {"meses": meses_g, "media": media, "por_mes": {r: por_mes[r][g] for r in meses_g}}
        for k in LINHAS_POR_GRUPO:
            falta[k] += media[k]
    corte = getattr(ctx, "data_corte", None) or (dt.date.today() - dt.timedelta(days=1))   # a atualização é D-1
    du = dias_uteis_do_mes(ctx.ref_atual, corte)
    for k in CLASSES_POR_DIA_UTIL:                 # indiretas: ticket por dia útil × dias úteis que faltam
        real = atual.get(k) or 0.0
        sufixo = "corte" if k == "ri_CORTE" else "uteis"
        decorridos, faltam_dias = du[sufixo + "_decorridos"], du[sufixo + "_faltam"]
        falta[k] = (real / decorridos) * faltam_dias if decorridos else 0.0
    medias = {}
    for k in LINHAS_BASICAS:
        if k in LINHAS_POR_GRUPO or k in CLASSES_POR_DIA_UTIL:
            continue
        media = medias[k] = sum(meses[r].get(k) or 0.0 for r in refs) / len(refs)
        real = atual.get(k) or 0.0
        falta[k] = 0.0 if abs(real) >= abs(media) else media - real
    return {"refs": refs, "meses": meses, "atual": atual, "falta": falta, "faltam": faltam, "dias": du, "corte": corte,
            "grupos": grupos, "medias": medias}


def _attr(v):
    return "" if v is None else repr(round(float(v), 6))


def previsao_html(ctx, sup):
    if getattr(ctx, "base_completa", None) is None:
        return ""
    dados = calcula_previsao(ctx, sup)
    nome = html.escape(_nome_sup(sup))
    e = lambda v: html.escape(v, quote=True)
    if dados is None:
        return (f'<div class="card"><h2>Previsão de fechamento — {nome} — {nome_mes(ctx.ref_atual)}</h2>'
                '<p class="nota-secao">Sem meses anteriores na base para projetar o fechamento.</p></div>')
    atual, falta = dados["atual"], dados["falta"]
    fontes, _ = _fontes(ctx)
    fontes = [f for f in fontes if not f.upper().count("SUP")] + [f for f in fontes if f.upper().count("SUP")]   # RF primeiro, SUP depois
    orc = _orcados_do_mes(ctx, sup, ctx.ref_atual, fontes)

    cab = ["<th>Rubrica</th>"]
    cab += [f'<th data-src="{e(f)}" data-tipo="orc">Orçado<br>{html.escape(f)}</th>' for f in fontes]
    cab += ["<th>Realizado</th>", '<th class="prev-col-prev p-col-forecast">Forecast ✎</th>', "<th>Realizado<br>+ Forecast</th>"]
    for f in fontes:
        cab += [f'<th data-src="{e(f)}" data-tipo="dreal">Δ %<br>vs {html.escape(f)}</th>',
                f'<th data-src="{e(f)}" data-tipo="dreal">Δ R$<br>vs {html.escape(f)}</th>']
    ncol = len(cab)

    linhas = []
    for chave, rotulo, formato, negrito in LINHAS:
        if chave is None:
            linhas.append(f'<tr class="dre-vazia"><td colspan="{ncol}"></td></tr>')
            continue
        basica = chave in LINHAS_BASICAS
        real = atual.get(chave)
        auto = falta.get(chave) if basica and real is not None else None     # forecast = o que ainda vai ser faturado
        tds = [f'<td class="dre-rotulo">{html.escape(rotulo)}</td>']
        tds += [f'<td class="num" data-src="{e(f)}" data-tipo="orc">{_fmt(orc[f].get(chave), formato)}</td>' for f in fontes]
        tds.append(f'<td class="num p-real">{_fmt(real, formato)}</td>')
        cls = "num p-prev p-col-forecast" + (" prev-edit" if basica else "")
        editavel = ' contenteditable="true" spellcheck="false"' if basica else ""
        dica = "Clique para editar o forecast" if basica else "Calculado a partir das linhas editáveis"
        tds.append(f'<td class="{cls}" data-k="{chave}"{editavel} title="{dica}">{_fmt(auto, formato)}</td>')
        tds.append('<td class="num p-fech">-</td>')
        for f in fontes:
            o = _attr(orc[f].get(chave))
            tds.append(f'<td class="num p-dorc" data-src="{e(f)}" data-tipo="dreal" data-orc="{o}">-</td>')
            tds.append(f'<td class="num p-dorcv" data-src="{e(f)}" data-tipo="dreal" data-orc="{o}">-</td>')
        linhas.append(f'<tr class="{"dre-forte" if negrito else ""}" data-k="{chave}" data-fmt="{formato}" '
                      f'data-real="{_attr(real)}" data-auto="{_attr(auto)}" data-canc="{1 if chave == "canc" else 0}">'
                      + "".join(tds) + "</tr>")

    nota = ("<b>Fechamento = Realizado + Forecast.</b> Clique em um valor da coluna Forecast ✎ para editar; fechamento, totais e "
            "comparações com os orçados são refeitos na hora. Como cada linha é calculada (com os números do mês): "
            "aba <b>Dados</b> › <b>5. Forecast</b>.")
    return (f'<div class="card prev-card"><h2 class="prev-titulo">Forecast de fechamento — {nome} — {nome_mes(ctx.ref_atual)}'
            '<span class="prev-acoes"><button type="button" class="btn-just btn-prev-restaurar" onclick="previsaoRestaurar(this)">↺ Restaurar automático</button>'
            '<button type="button" class="btn-just btn-prev-toggle" onclick="previsaoAlternar()">Ocultar forecast</button></span></h2>'
            f'<p class="nota-secao prev-nota">{nota}</p>'
            f'<div class="tabela-wrap"><table class="tabela-dre tabela-previsao" data-prev="{e(sup)}" data-mes="{ctx.ref_atual}"><thead><tr>' + "".join(cab)
            + "</tr></thead><tbody>" + "".join(linhas) + "</tbody></table></div></div>")


def gera_aba_forecast_html(ctx):
    """Aba "Forecast": um bloco por superintendência (o filtro Superintendência escolhe qual aparece)."""
    from .dre import lista_sups, prepara
    prepara(ctx)
    return "".join(f'<div class="prev-bloco" data-sup="{html.escape(sup, quote=True)}">{previsao_html(ctx, sup)}</div>'
                   for sup in lista_sups(ctx))
