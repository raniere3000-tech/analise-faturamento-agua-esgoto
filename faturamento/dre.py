# -*- coding: utf-8 -*-
"""Abas "DRE" e "Indiretas" do relatório: realizado x orçado RF x orçado SUP, por superintendência.

Realizado
  - Diretas (água/esgoto), economias, volumes, tarifa e ticket: fatura + consumo do mês atual.
  - Indiretas: arquivo de serviço avulso (rubrica -> classe, ver `regras.json`).
  - Cancelamento: rubricas de cancelamento da fatura do ciclo.
Orçado: planilhas "RF" e "RF SUP" (colunas Sup, Rubrica e um mês por coluna).
A SUP vem da cidade (Nome da Localidade) -> relação em `regras.json`.
"""
import html
import json

import pandas as pd

from .config import LINHAS_INDIRETAS_DRE, SUP_POR_CIDADE, chave_texto
from .formatacao import fmt_num, nome_mes

TODAS = "TODAS"
SEM_SUP = "SEM SUP"
CLASSES_ORDEM = ["CORTE", "RELIGAÇÃO", "LNA", "SANÇÃO", "OUTROS", "LNE"]
NOME_CLASSE = {"CORTE": "Cortes/Recorte", "RELIGAÇÃO": "Religações", "LNA": "Ligações de água (LNA)",
               "SANÇÃO": "Fiscalização (sanções)", "OUTROS": "Outros", "LNE": "Ligações de esgoto (LNE)"}

# (chave, rótulo, formato, negrito) — formato: moeda | num | dec | blank
LINHAS = [
    ("bruto", "Faturamento Bruto", "moeda", True), (None,) * 4,
    ("dTot", "Diretas Totais", "moeda", True),
    ("dA", "DIRETAS ÁGUA", "moeda", False), ("dE", "DIRETAS ESGOTO", "moeda", False), (None,) * 4,
    ("iE", "Fat. de esgoto - Indireto", "moeda", True), (None,) * 4,
    ("iA", "Fat. de água - Indireto", "moeda", True),
    ("ri_CORTE", "RI Cortes/Recorte", "moeda", False), ("ri_RELIGAÇÃO", "RI Religações", "moeda", False),
    ("ri_LNA", "RI Ligações - Água", "moeda", False), ("ri_SANÇÃO", "RI Fiscalização", "moeda", False),
    ("ri_OUTROS", "RI Outros - Água", "moeda", False), (None,) * 4,
    ("ecoA", "Economias de Água - Faturadas", "num", False), ("ecoE", "Economias de Esgoto - Faturadas", "num", False),
    ("volA", "Volume de Água - Faturado", "num", False), ("volE", "Volume de Esgoto - Faturado", "num", False),
    ("vmA", "Volume Médio Faturado de Água", "dec", False), ("vmE", "Volume Médio Faturado de Esgoto", "dec", False),
    ("tarA", "Tarifa Média de Água (m³)", "dec", False), ("tarE", "Tarifa Média  de Esgoto (m³)", "dec", False),
    (None,) * 4,
    ("tickA", "Ticket Média de Água (R$)", "dec", False), ("tickE", "Ticket Média  de Esgoto (R$)", "dec", False),
    (None,) * 4,
    ("canc", "Cancelamento", "moeda", True),
]

# Rótulo da planilha de orçado (comparado sem acento/pontuação) -> chave interna
ROTULOS_ORCADO = {
    "FaturamentoBruto": "bruto", "FatBrutodeaguaDireto": "dA", "FatBrutodeesgotoDireto": "dE",
    "FatBrutodeaguaIndireto": "iA", "FatBrutodeesgotoIndireto": "iE", "Cancelamentos": "canc",
    "EconomiasdeAguaFaturadas": "ecoA", "EconomiasdeEsgotoFaturadas": "ecoE",
    "VolumedeAguaFaturado": "volA", "VolumedeEsgotoFaturado": "volE",
}
for _cl, _rotulo in LINHAS_INDIRETAS_DRE.items():
    if _cl != "LNE":
        ROTULOS_ORCADO[_rotulo] = "ri_" + _cl
ROTULOS_ORCADO = {chave_texto(k): v for k, v in ROTULOS_ORCADO.items()}


def _ligacao(serie):
    return serie.astype(str).str.strip()


def prepara(ctx):
    """Marca cidade/SUP em cada tabela e junta os avisos. Roda uma vez por análise."""
    if getattr(ctx, "dre_pronto", False):
        return
    avisos = []
    mapa = {}
    base = ctx.base_final
    if "Nome da Localidade" in base.columns:
        t = base.dropna(subset=["Nome da Localidade"])
        mapa.update(dict(zip(_ligacao(t["N. Ligação"]), t["Nome da Localidade"])))
    avu = ctx.avulso if ctx.avulso is not None else pd.DataFrame()
    if len(avu) and "Nome da Localidade" in avu.columns:
        t = avu.dropna(subset=["Nome da Localidade", "N. da Ligacao"])
        for lig, cid in zip(_ligacao(t["N. da Ligacao"]), t["Nome da Localidade"]):
            mapa.setdefault(lig, cid)

    def marca(df, col_lig):
        if df is None or not len(df):
            return df
        df = df.copy()
        cid = df["Nome da Localidade"] if "Nome da Localidade" in df.columns else pd.Series(index=df.index, dtype=object)
        cid = cid.where(cid.notna(), _ligacao(df[col_lig]).map(mapa))
        df["__cidade"] = cid
        df["__sup"] = cid.map(lambda c: SUP_POR_CIDADE.get(chave_texto(c), SEM_SUP) if pd.notna(c) else SEM_SUP)
        return df

    ctx.base_final = marca(ctx.base_final, "N. Ligação")
    ctx.df_atual = marca(ctx.df_atual, "N. Ligação")
    ctx.df_anterior = marca(ctx.df_anterior, "N. Ligação")
    ctx.cancelamento = marca(ctx.cancelamento, "N. da Ligacao")
    ctx.avulso = marca(avu, "N. da Ligacao") if len(avu) else avu

    if not len(avu):
        avisos.append("Nenhum arquivo de serviço avulso encontrado na pasta (o nome precisa conter \"avulso\"): as indiretas ficaram zeradas.")
    else:
        if not (ctx.avulso["Referencia"] == ctx.ref_atual).any():
            avisos.append(f"O arquivo de serviço avulso não tem lançamentos de {nome_mes(ctx.ref_atual)}: indiretas zeradas neste mês.")
        sem_classe = ctx.avulso[ctx.avulso["Classe"].isna()]["Rubrica"].unique()
        if len(sem_classe):
            avisos.append("Rubricas de serviço avulso fora da relação (contadas em \"RI Outros - Água\"): "
                          + "; ".join(sorted(map(str, sem_classe))[:8]) + (" …" if len(sem_classe) > 8 else ""))
            ctx.avulso["Classe"] = ctx.avulso["Classe"].fillna("OUTROS")
    if ctx.cancelamento is None or not len(ctx.cancelamento):
        avisos.append("Nenhuma rubrica de cancelamento encontrada na fatura: cancelamento zerado.")
    if ctx.orcado.get("rf") is None:
        avisos.append("Orçado RF não encontrado (planilha com colunas Sup, Rubrica e meses, ex.: RF01T26.xlsx).")
    if ctx.orcado.get("sup") is None:
        avisos.append("Orçado SUP não encontrado (mesmo modelo do RF, com \"SUP\" no nome, ex.: RF SUP.xlsx).")
    sem_sup = ctx.df_atual[ctx.df_atual["__sup"] == SEM_SUP]
    if len(sem_sup):
        avisos.append(f"{len(sem_sup)} linhas do mês atual sem cidade/SUP identificada (a fatura precisa ter a coluna "
                      "\"Nome da Localidade\" ou a ligação aparecer no serviço avulso); aparecem em \"SEM SUP\".")
    ctx.avisos_dre = avisos
    ctx.dre_pronto = True


def lista_sups(ctx):
    prepara(ctx)
    sups = set(ctx.base_final["__sup"])
    if len(ctx.avulso):
        sups |= set(ctx.avulso["__sup"])
    return [TODAS] + sorted(sups - {SEM_SUP}) + ([SEM_SUP] if SEM_SUP in sups else [])


def _filtra(df, sup):
    if df is None or not len(df) or sup == TODAS:
        return df
    return df[df["__sup"] == sup]


def _div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def realizado(ctx, sup, ref=None):
    ref = ref or ctx.ref_atual
    at = _filtra(ctx.base_final[ctx.base_final["Referencia de Leitura"] == ref], sup)
    r = {}
    for k, rub in (("A", "AGUA"), ("E", "ESGOTO")):
        d = at[at["Rubrica"].str.contains(rub, case=False, na=False)]
        pos = d[d["Consumo Faturado"] > 0]
        r["d" + k] = float(d["Valor (R$)"].sum())
        r["eco" + k] = float(pos["Economias_Totais"].sum())
        r["vol" + k] = float(pos["Consumo Faturado"].sum())
    avu = _filtra(ctx.avulso, sup)
    if avu is not None and len(avu):
        avu = avu[avu["Referencia"] == ref]
    por_classe = avu.groupby("Classe")["Valor Parcela"].sum() if avu is not None and len(avu) else {}
    for cl in CLASSES_ORDEM:
        r["ri_" + cl] = float(por_classe.get(cl, 0.0))
    r["iE"] = r.pop("ri_LNE")
    r["iA"] = sum(r["ri_" + cl] for cl in CLASSES_ORDEM if cl != "LNE")
    canc = _filtra(ctx.cancelamento, sup)
    if canc is not None and len(canc):
        canc = canc[canc["Referencia de Leitura"] == ref]
    r["canc"] = float(canc["Valor Parcela"].sum()) if canc is not None and len(canc) else 0.0
    return completa(r)


def completa(r):
    """Calcula as linhas derivadas (totais, médias) a partir das básicas, mesmo se faltarem algumas."""
    r = dict(r)
    if r.get("dTot") is None and (r.get("dA") is not None or r.get("dE") is not None):
        r["dTot"] = (r.get("dA") or 0) + (r.get("dE") or 0)
    if r.get("iA") is None:
        ris = [r.get("ri_" + cl) for cl in CLASSES_ORDEM if cl != "LNE" and r.get("ri_" + cl) is not None]
        if ris:
            r["iA"] = sum(ris)
    if r.get("bruto") is None and any(r.get(k) is not None for k in ("dTot", "iA", "iE")):
        r["bruto"] = sum(r.get(k) or 0 for k in ("dTot", "iA", "iE"))
    for s in ("A", "E"):
        r["vm" + s] = _div(r.get("vol" + s), r.get("eco" + s))
        r["tar" + s] = _div(r.get("d" + s), r.get("vol" + s))
        r["tick" + s] = _div(r.get("d" + s), r.get("eco" + s))
    return r


def orcado(ctx, fonte, sup, ref=None):
    """Valores do orçado ('rf' ou 'sup') no mês, por linha. Devolve {} se não houver dados."""
    ref = ref or ctx.ref_atual
    info = ctx.orcado.get(fonte)
    if not info:
        return {}
    d = info["dados"]
    d = d[d["Referencia"] == ref]
    chaves_sup = d["Sup"].map(chave_texto)
    if sup == TODAS:
        if (chaves_sup == "INTERIOR").any():
            d = d[chaves_sup == "INTERIOR"]
    else:
        d = d[chaves_sup == chave_texto(sup)]
    r = {}
    for rotulo, valor in zip(d["Rubrica"].map(chave_texto), d["Valor"]):
        chave = ROTULOS_ORCADO.get(rotulo)
        if chave:
            r[chave] = r.get(chave, 0.0) + float(valor)
    return completa(r)


# ---------- meses e filtros ----------
def lista_meses(ctx):
    """Meses (MM/AAAA, em ordem) que têm dados de fatura, serviço avulso ou cancelamento."""
    prepara(ctx)
    refs = set(ctx.base_final["Referencia de Leitura"].dropna())
    for df, col in ((ctx.avulso, "Referencia"), (ctx.cancelamento, "Referencia de Leitura")):
        if df is not None and len(df):
            refs |= set(df[col].dropna())
    return sorted(refs, key=lambda r: (r[3:], r[:2]))


def _mes_anterior(ref):
    m, a = int(ref[:2]), int(ref[3:])
    return f"{12 if m == 1 else m - 1:02d}/{a - 1 if m == 1 else a}"


# ---------- HTML ----------
def _fmt(v, formato):
    if v is None:
        return "-"
    if formato == "dec":
        return fmt_num(v, 2)
    if formato == "num":
        return fmt_num(v, 0)
    texto = fmt_num(abs(v), 0)
    return f"R$ ({texto})" if v < 0 else f"R$ {texto}"


def _pct(real, orc):
    if real is None or orc in (None, 0):
        return None
    return real / orc - 1


def _cel(valor, cls=""):
    return f'<td class="{cls}">{valor}</td>'


def _celulas_delta(real, orc, formato, eh_canc, classe):
    """Δ (%) e Δ (R$) do realizado contra um orçado. `classe`: col-rf ou col-sup (o filtro Referência esconde uma delas)."""
    dec = 2 if formato == "dec" else 0
    d = None if real is None or orc is None else real - orc
    pct = _pct(real, orc)

    def neg(v):
        return "neg" if (v is not None and v < -(0.005 if dec else 0.5) and not eh_canc) else ""
    return (_cel("-" if pct is None else fmt_num(pct * 100, 1) + "%", f"num {classe} {neg(pct)}"),
            _cel("-" if d is None else fmt_num(d, dec), f"num {classe} {neg(d)}"))


def _linha_dre(rotulo, formato, negrito, rf, sup, real, eh_canc):
    p_rf, d_rf = _celulas_delta(real, rf, formato, eh_canc, "col-rf")
    p_sup, d_sup = _celulas_delta(real, sup, formato, eh_canc, "col-sup")
    return (f'<tr class="{"dre-forte" if negrito else ""}"><td class="dre-rotulo">{html.escape(rotulo)}</td>'
            + _cel(_fmt(rf, formato), "num") + _cel(_fmt(sup, formato), "num") + _cel(_fmt(real, formato), "num")
            + p_rf + d_rf + p_sup + d_sup + "</tr>")


CABECALHO_DELTAS = ('<th class="col-rf">Δ (%)</th><th class="col-rf">Δ (R$)</th>'
                    '<th class="col-sup">Δ (%) Sup</th><th class="col-sup">Δ R$ (Orçado Sup)</th>')


def tabela_dre(ctx, sup, ref):
    real = realizado(ctx, sup, ref)
    rf = orcado(ctx, "rf", sup, ref)
    os_ = orcado(ctx, "sup", sup, ref)
    linhas = []
    for chave, rotulo, formato, negrito in LINHAS:
        if chave is None:
            linhas.append('<tr class="dre-vazia"><td colspan="8"></td></tr>')
        else:
            linhas.append(_linha_dre(rotulo, formato, negrito, rf.get(chave), os_.get(chave), real.get(chave), chave == "canc"))
    return ('<div class="tabela-wrap"><table class="tabela-dre"><thead><tr><th>Projeto/Linha</th><th>ORÇADO - RF</th>'
            f'<th>ORÇADO - SUP</th><th>REALIZADO</th>{CABECALHO_DELTAS}</tr></thead><tbody>'
            + "".join(linhas) + "</tbody></table></div>")


def _avisos_html(ctx):
    if not ctx.avisos_dre:
        return ""
    itens = "".join(f"<li>{html.escape(a)}</li>" for a in ctx.avisos_dre)
    return f'<div class="card avisos-card"><h2>Avisos</h2><ul class="avisos-dre">{itens}</ul></div>'


def _nome_sup(sup):
    return "Todas as superintendências (Interior)" if sup == TODAS else sup


def _bloco(sup, ref, conteudo):
    return f'<div class="sup-bloco" data-sup="{html.escape(sup, quote=True)}" data-mes="{ref}">{conteudo}</div>'


def gera_aba_dre_html(ctx):
    prepara(ctx)
    fontes = [f"{nome}: {html.escape(ctx.orcado[k]['arquivo'])}" for k, nome in (("rf", "Orçado RF"), ("sup", "Orçado SUP")) if ctx.orcado.get(k)]
    nota = " · ".join(fontes) if fontes else "Sem planilhas de orçado na pasta"
    blocos = []
    for ref in lista_meses(ctx):
        for sup in lista_sups(ctx):
            blocos.append(_bloco(sup, ref, (
                f'<div class="card"><h2>DRE — {html.escape(_nome_sup(sup))} — {nome_mes(ref)}</h2>'
                f'<p class="nota-secao">{nota}. Δ (%) e Δ (R$) comparam o realizado com o orçado RF; as colunas "Sup" comparam com o orçado SUP.</p>'
                f'{tabela_dre(ctx, sup, ref)}</div>')))
    return _avisos_html(ctx) + "".join(blocos)


# ---------- Indiretas ----------
def _indiretas_mes(ctx, sup, ref):
    """{classe: (qtd, valor)} do serviço avulso no mês (sem as rubricas excluídas)."""
    av = _filtra(ctx.avulso, sup)
    av = av[(av["Referencia"] == ref) & (av["Classe"] != "EXCLUIR")]
    g = av.groupby("Classe")["Valor Parcela"].agg(["size", "sum"])
    return {cl: (int(g.loc[cl, "size"]), float(g.loc[cl, "sum"])) if cl in g.index else (0, 0.0) for cl in CLASSES_ORDEM}


def tabela_orcado_realizado(ctx, sup, ref):
    real = realizado(ctx, sup, ref)
    rf, os_ = orcado(ctx, "rf", sup, ref), orcado(ctx, "sup", sup, ref)
    linhas = []
    for chave, rotulo, negrito in (("ri_CORTE", "RI Cortes/Recorte", False), ("ri_RELIGAÇÃO", "RI Religações", False),
                                   ("ri_LNA", "RI Ligações - Água", False), ("ri_SANÇÃO", "RI Fiscalização", False),
                                   ("ri_OUTROS", "RI Outros - Água", False), ("iA", "Fat. de água - Indireto", True),
                                   ("iE", "Fat. de esgoto - Indireto", True)):
        linhas.append(_linha_dre(rotulo, "moeda", negrito, rf.get(chave), os_.get(chave), real.get(chave), False))
    tot = lambda d: None if d.get("iA") is None and d.get("iE") is None else (d.get("iA") or 0) + (d.get("iE") or 0)
    linhas.append(_linha_dre("Total indiretas", "moeda", True, tot(rf), tot(os_), tot(real), False))
    return ('<div class="tabela-wrap"><table class="tabela-dre"><thead><tr><th>Classe / linha da DRE</th><th>ORÇADO - RF</th>'
            f'<th>ORÇADO - SUP</th><th>REALIZADO</th>{CABECALHO_DELTAS}</tr></thead><tbody>' + "".join(linhas) + "</tbody></table></div>")


def tabela_evolucao(ctx, sup, ref, meses):
    por_mes = {m: _indiretas_mes(ctx, sup, m) for m in meses}
    cab = "".join(f'<th class="{"mes-sel" if m == ref else ""}">{nome_mes(m)}</th>' for m in meses)
    linhas = []
    for cl in CLASSES_ORDEM:
        cel = "".join(_cel(fmt_num(por_mes[m][cl][1], 0), "num mes-sel" if m == ref else "num") for m in meses)
        linhas.append(f'<tr><td class="dre-rotulo">{NOME_CLASSE[cl]}</td>{cel}</tr>')
    cel = "".join(_cel(fmt_num(sum(v[1] for v in por_mes[m].values()), 0), "num mes-sel" if m == ref else "num") for m in meses)
    linhas.append(f'<tr class="dre-forte"><td class="dre-rotulo">Total</td>{cel}</tr>')
    dados = {"meses": [nome_mes(m) for m in meses],
             "series": [{"classe": NOME_CLASSE[cl], "valores": [round(por_mes[m][cl][1], 2) for m in meses]} for cl in CLASSES_ORDEM]}
    grafico = (f'<div class="grafico-area grafico-indiretas"><canvas class="canvas-indiretas" '
               f'data-dados="{html.escape(json.dumps(dados), quote=True)}"></canvas></div>')
    return grafico + ('<div class="tabela-wrap"><table class="tabela-dre"><thead><tr><th>Classe</th>' + cab
                      + "</tr></thead><tbody>" + "".join(linhas) + "</tbody></table></div>")


def tabela_qtd_ticket(ctx, sup, ref):
    atual, ant = _indiretas_mes(ctx, sup, ref), _indiretas_mes(ctx, sup, _mes_anterior(ref))
    linhas = []
    tq = tv = tqa = tva = 0
    for cl in CLASSES_ORDEM:
        (q, v), (qa, va) = atual[cl], ant[cl]
        tq, tv, tqa, tva = tq + q, tv + v, tqa + qa, tva + va
        tk, tka = _div(v, q), _div(va, qa)
        d = None if tk is None or tka is None else tk - tka
        linhas.append(f'<tr><td class="dre-rotulo">{NOME_CLASSE[cl]}</td>' + _cel(q, "num") + _cel(_fmt(v, "moeda"), "num")
                      + _cel(_fmt(tk, "dec"), "num") + _cel(qa, "num") + _cel(_fmt(tka, "dec"), "num")
                      + _cel("-" if d is None else fmt_num(d, 2), "num " + ("neg" if d is not None and d < -0.005 else "")) + "</tr>")
    tk, tka = _div(tv, tq), _div(tva, tqa)
    linhas.append('<tr class="dre-forte"><td class="dre-rotulo">Total</td>' + _cel(tq, "num") + _cel(_fmt(tv, "moeda"), "num")
                  + _cel(_fmt(tk, "dec"), "num") + _cel(tqa, "num") + _cel(_fmt(tka, "dec"), "num")
                  + _cel("-" if tk is None or tka is None else fmt_num(tk - tka, 2), "num") + "</tr>")
    return ('<div class="tabela-wrap"><table class="tabela-dre"><thead><tr><th>Classe</th><th>Lançamentos</th><th>Valor (R$)</th>'
            f'<th>Ticket médio (R$)</th><th>Lanç. {nome_mes(_mes_anterior(ref))}</th><th>Ticket {nome_mes(_mes_anterior(ref))}</th>'
            "<th>Δ ticket (R$)</th></tr></thead><tbody>" + "".join(linhas) + "</tbody></table></div>")


def gera_aba_indiretas_html(ctx):
    prepara(ctx)
    if not len(ctx.avulso):
        return '<div class="card"><h2>Indiretas</h2><p>Nenhum arquivo de serviço avulso encontrado na pasta (o nome precisa conter "avulso").</p></div>'
    meses_av = sorted(set(ctx.avulso["Referencia"].dropna()), key=lambda r: (r[3:], r[:2]))
    blocos = []
    for ref in lista_meses(ctx):
        for sup in lista_sups(ctx):
            nome = html.escape(_nome_sup(sup))
            blocos.append(_bloco(sup, ref, (
                f'<div class="card"><h2>Indiretas: orçado × realizado — {nome} — {nome_mes(ref)}</h2>'
                '<p class="nota-secao">Realizado = serviço avulso do mês, por classe da rubrica. Orçado das linhas "RI" só aparece se a planilha RF tiver essas linhas.</p>'
                f'{tabela_orcado_realizado(ctx, sup, ref)}</div>'
                f'<div class="card"><h2>Evolução mensal por classe — {nome}</h2>{tabela_evolucao(ctx, sup, ref, meses_av)}</div>'
                f'<div class="card"><h2>Quantidade e ticket médio — {nome} — {nome_mes(ref)}</h2>{tabela_qtd_ticket(ctx, sup, ref)}</div>')))
    return "".join(blocos)


def gera_filtros_dre_html(ctx):
    """Seletores para quando o relatório é aberto sozinho (no site, o cabeçalho cuida disso)."""
    def opcoes(itens):
        return "".join(f'<option value="{html.escape(v, quote=True)}">{html.escape(t)}</option>' for v, t in itens)
    sups = opcoes([(s, _nome_sup(s) if s == TODAS else s) for s in lista_sups(ctx)])
    meses = opcoes([(m, nome_mes(m)) for m in lista_meses(ctx)])
    refs = opcoes([("AMBOS", "RF e SUP"), ("RF", "Só RF"), ("SUP", "Só SUP")])
    return ('<span class="seletor-sup" id="seletorSup" hidden>'
            f'<label>Superintendência <select id="selSup" onchange="definirFiltros({{sup:this.value}})">{sups}</select></label>'
            f'<label>Mês <select id="selMes" onchange="definirFiltros({{mes:this.value}})">{meses}</select></label>'
            f'<label>Referência <select id="selRef" onchange="definirFiltros({{ref:this.value}})">{refs}</select></label></span>')


def gera_info_filtros_json(ctx):
    info = {"sups": lista_sups(ctx), "meses": [{"ref": m, "label": nome_mes(m)} for m in lista_meses(ctx)],
            "mesAtual": ctx.ref_atual, "temRF": bool(ctx.orcado.get("rf")), "temSUP": bool(ctx.orcado.get("sup"))}
    return '<script type="application/json" id="info-filtros">' + json.dumps(info).replace("<", "\\u003c") + "</script>"
