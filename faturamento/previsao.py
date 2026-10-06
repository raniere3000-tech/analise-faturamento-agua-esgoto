# -*- coding: utf-8 -*-
"""Previsão de fechamento do mês (aba DRE).

Fechamento = realizado até agora (grupos já faturados) + projeção do que falta.
  - Diretas (água/esgoto), economias e volume: cada grupo que ainda não faturou entra com
    economias × volume por economia × tarifa do próprio grupo (até 6 meses de histórico, média ponderada),
    corrigidos pela tendência dos grupos que já faturaram no mês (ver projecao_grupos.py).
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
from .dre import LINHAS, TODAS, _fmt, _fontes, _nome_sup, _orcados_do_mes, realizado
from .formatacao import nome_mes
from .projecao_grupos import backtest, projeta

MESES_BASE = 3
MESES_HIST = 6          # histórico usado no forecast das diretas por grupo
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


def _refs_existentes(ctx):
    base = ctx.base_completa
    cache = ctx.__dict__.get("_refs_existentes")
    if cache is None or cache[0] is not base:
        cache = ctx._refs_existentes = (base, set(base["Referencia de Leitura"].dropna().unique()))
    return cache[1]


def _refs_base(ctx, n_meses=MESES_BASE):
    """Até `n_meses` meses imediatamente anteriores ao atual que existem na base (do mais antigo ao mais novo)."""
    existentes = _refs_existentes(ctx)
    return [r for r in (_mes_deslocado(ctx.ref_atual, n) for n in range(n_meses, 0, -1)) if r in existentes]


def resumo_mensal(ctx):
    """Soma por mês × grupo × superintendência, colunas dA, dE, ecoA, ecoE, volA, volE (economias/volume só com Consumo > 0).
    Calculado uma vez por relatório: alimenta forecast, backtest e orçado por ciclo sem varrer a base de novo."""
    from .dre import prepara
    prepara(ctx)
    base = ctx.base_completa
    cache = ctx.__dict__.get("_resumo_mensal")
    if cache is not None and cache[0] is base:
        return cache[1]
    d = base[base["__serv"].isin(["A", "E"])]
    pos = d["Consumo Faturado"] > 0
    t = pd.DataFrame({"ref": d["Referencia de Leitura"], "g": d["Grupo"].astype(str).str.strip(), "sup": d["__sup"],
                      "s": d["__serv"], "d": d["Valor (R$)"], "eco": d["Economias_Totais"].where(pos, 0),
                      "vol": d["Consumo Faturado"].where(pos, 0)})
    agg = t.groupby(["ref", "g", "sup", "s"]).sum().unstack("s", fill_value=0)
    agg.columns = [f"{m}{sv}" for m, sv in agg.columns]
    for c in LINHAS_POR_GRUPO:
        if c not in agg.columns:
            agg[c] = 0.0
    agg = agg[LINHAS_POR_GRUPO].astype(float)
    ctx._resumo_mensal = (base, agg)
    return agg


def valores_grupo(ctx, ref, sup):
    """{grupo: {dA, dE, ecoA, ecoE, volA, volE}} de um mês e superintendência (a partir do resumo mensal)."""
    agg = resumo_mensal(ctx)
    if ref not in agg.index.get_level_values("ref"):
        return {}
    x = agg.xs(ref, level="ref")
    if sup != TODAS:
        x = x[x.index.get_level_values("sup") == sup]
    x = x.groupby(level="g").sum()
    return {g: {k: float(v) for k, v in linha.items()} for g, linha in zip(x.index, x.to_dict("records"))}


def _completo(ctx):
    """Cópia do contexto cuja base tem todos os grupos (para os meses anteriores inteiros)."""
    c = copy.copy(ctx)
    c.base_final = ctx.base_completa
    return c


def calcula_previsao(ctx, sup):
    """Devolve dict com meses-base, realizado completo dos meses-base, realizado até agora, projeção e previsão.
    Com cache: a aba Forecast e a aba Dados pedem a mesma SUP."""
    cache = ctx.__dict__.setdefault("_cache_previsao", {})
    chave = (id(ctx.base_final), id(ctx.base_completa), sup, ctx.ref_atual, getattr(ctx, "data_corte", None))
    if chave not in cache:
        cache[chave] = _calcula_previsao(ctx, sup)
    return cache[chave]


def _calcula_previsao(ctx, sup):
    refs = _refs_base(ctx)
    if not refs:
        return None
    cheio = _completo(ctx)
    meses = {r: realizado(cheio, sup, r) for r in refs}
    atual = realizado(ctx, sup, ctx.ref_atual)

    refs_hist = _refs_base(ctx, MESES_HIST)
    mes_atual = valores_grupo(ctx, ctx.ref_atual, sup)
    faturados = sorted(mes_atual)
    por_mes = {r: valores_grupo(ctx, r, sup) for r in refs_hist}
    # grupos que faltam: faturaram nos últimos 3 meses e ainda não no mês atual
    faltam = sorted({g for r in refs for g in por_mes[r]} - set(faturados))

    falta = {k: 0.0 for k in LINHAS_BASICAS}
    proj = projeta(por_mes, refs_hist, mes_atual, faltam, faturados)
    for k in LINHAS_POR_GRUPO:
        falta[k] = proj["total"][k]
    # backtest: os meses do histórico simulados como se os últimos grupos ainda não tivessem faturado
    todos = _refs_base(ctx, MESES_HIST + 3)
    por_mes_bt = {r: por_mes.get(r) or valores_grupo(ctx, r, sup) for r in todos}
    n_grupos = len(set(faturados) | set(faltam))
    teste = backtest(por_mes_bt, todos, len(faltam) or max(1, round(n_grupos / 3)), n_hist=MESES_HIST)
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
    return {"refs": refs, "refs_hist": refs_hist, "meses": meses, "atual": atual, "falta": falta, "faltam": faltam,
            "faturados": faturados, "dias": du, "corte": corte, "projecao": proj, "por_mes": por_mes, "mes_atual": mes_atual,
            "backtest": teste, "medias": medias}


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

    fx = dados["projecao"]["faixa"]
    faixa = "; ".join(f"{nome}: {_fmt((atual.get(k) or 0) + fx[k][0], 'moeda')} a {_fmt((atual.get(k) or 0) + fx[k][1], 'moeda')}"
                      for k, nome in (("dA", "Diretas Água"), ("dE", "Diretas Esgoto"))) if dados["faltam"] else ""
    nota = ("<b>Fechamento = Realizado + Forecast.</b> Clique em um valor da coluna Forecast ✎ para editar; fechamento, totais e "
            "comparações com os orçados são refeitos na hora. "
            + (f"Fechamento provável (~80%) — {faixa}. " if faixa else "")
            + "Como cada linha é calculada (com os números do mês): aba <b>Dados</b> › <b>5. Forecast</b>.")
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
    sups = lista_sups(ctx)
    blocos = []
    for i, sup in enumerate(sups):
        ctx.progresso.etapa(i, len(sups), 92, 94, f"Criando aba Forecast: {_nome_sup(sup)}")
        blocos.append(f'<div class="prev-bloco" data-sup="{html.escape(sup, quote=True)}">{previsao_html(ctx, sup)}</div>')
    return "".join(blocos)
