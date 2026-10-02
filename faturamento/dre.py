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
    sups = set(ctx.df_atual["__sup"])
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
    base = ctx.df_atual if ref == ctx.ref_atual else ctx.df_anterior
    at = _filtra(base, sup)
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


# ---------- HTML ----------
def _fmt(v, formato, delta=False):
    if v is None:
        return "-"
    if formato == "dec":
        return fmt_num(v, 2)
    if formato == "num" or delta:
        return fmt_num(v, 0)
    texto = fmt_num(abs(v), 0)
    return f"R$ ({texto})" if v < 0 else f"R$ {texto}"


def _pct(real, orc):
    if real is None or orc in (None, 0):
        return None
    return real / orc - 1


def _linha_dre(rotulo, formato, negrito, rf, sup, real, eh_canc):
    def cel(v, cls=""):
        return f'<td class="{cls}">{v}</td>'

    def delta(a, b):
        if a is None or b is None:
            return None
        return a - b
    d_rf, d_sup = delta(real, rf), delta(real, sup)
    pct = _pct(real, rf)
    dec = 2 if formato == "dec" else 0

    def neg(v):
        return "neg" if (v is not None and v < -(0.005 if dec else 0.5) and not eh_canc) else ""
    pct_txt = "-" if pct is None else fmt_num(pct * 100, 1) + "%"
    cls_linha = "dre-forte" if negrito else ""
    return (f'<tr class="{cls_linha}"><td class="dre-rotulo">{html.escape(rotulo)}</td>'
            + cel(_fmt(rf, formato), "num") + cel(_fmt(sup, formato), "num") + cel(_fmt(real, formato), "num")
            + cel(pct_txt, "num " + neg(pct))
            + cel("-" if d_rf is None else fmt_num(d_rf, dec), "num " + neg(d_rf)) + '<td class="dre-esp"></td>'
            + cel("-" if d_sup is None else fmt_num(d_sup, dec), "num " + neg(d_sup)) + "</tr>")


def tabela_dre(ctx, sup):
    real = realizado(ctx, sup)
    rf = orcado(ctx, "rf", sup)
    os_ = orcado(ctx, "sup", sup)
    linhas = []
    for chave, rotulo, formato, negrito in LINHAS:
        if chave is None:
            linhas.append('<tr class="dre-vazia"><td colspan="8"></td></tr>')
        else:
            linhas.append(_linha_dre(rotulo, formato, negrito, rf.get(chave), os_.get(chave), real.get(chave), chave == "canc"))
    return ('<div class="tabela-wrap"><table class="tabela-dre"><thead><tr><th>Projeto/Linha</th><th>ORÇADO - RF</th>'
            '<th>ORÇADO - SUP</th><th>REALIZADO</th><th>Δ (%)</th><th>Δ (R$)</th><th class="dre-esp"></th>'
            '<th>Δ R$ (Orçado Sup)</th></tr></thead><tbody>' + "".join(linhas) + "</tbody></table></div>")


def _avisos_html(ctx):
    if not ctx.avisos_dre:
        return ""
    itens = "".join(f"<li>{html.escape(a)}</li>" for a in ctx.avisos_dre)
    return f'<ul class="avisos-dre">{itens}</ul>'


def _nome_sup(sup):
    return "Todas as superintendências (Interior)" if sup == TODAS else sup


def gera_aba_dre_html(ctx):
    prepara(ctx)
    fontes = []
    for chave, nome in (("rf", "Orçado RF"), ("sup", "Orçado SUP")):
        info = ctx.orcado.get(chave)
        if info:
            fontes.append(f"{nome}: {html.escape(info['arquivo'])}")
    nota = " · ".join(fontes) if fontes else "Sem planilhas de orçado na pasta"
    blocos = []
    for sup in lista_sups(ctx):
        blocos.append(
            f'<div class="sup-bloco" data-sup="{html.escape(sup, quote=True)}">'
            f'<div class="card"><h2>DRE — {html.escape(_nome_sup(sup))} — {ctx.mes_atual}</h2>'
            f'<p class="nota-secao">{nota}. Δ (%) e Δ (R$) comparam o realizado com o orçado RF; a última coluna compara com o orçado SUP.</p>'
            f'{tabela_dre(ctx, sup)}</div></div>')
    avisos = f'<div class="card avisos-card"><h2>Avisos</h2>{_avisos_html(ctx)}</div>' if ctx.avisos_dre else ""
    return avisos + "".join(blocos)


def tabela_indiretas(ctx, sup):
    atual = ctx.avulso[ctx.avulso["Referencia"] == ctx.ref_atual]
    ant = ctx.avulso[ctx.avulso["Referencia"] == ctx.ref_anterior]
    if sup != TODAS:
        atual, ant = atual[atual["__sup"] == sup], ant[ant["__sup"] == sup]

    def pct(a, b):
        return "-" if not b else fmt_num((a / b - 1) * 100, 1) + "%"

    linhas, tot = [], [0, 0.0, 0.0]
    for cl in CLASSES_ORDEM:
        a, b = atual[atual["Classe"] == cl], ant[ant["Classe"] == cl]
        va, vb = float(a["Valor Parcela"].sum()), float(b["Valor Parcela"].sum())
        tot = [tot[0] + len(a), tot[1] + va, tot[2] + vb]
        linhas.append(f'<tr><td>{NOME_CLASSE[cl]}</td><td>{LINHAS_INDIRETAS_DRE[cl]}</td><td class="num">{len(a)}</td>'
                      f'<td class="num">{fmt_num(vb, 0)}</td><td class="num">{fmt_num(va, 0)}</td>'
                      f'<td class="num {"neg" if va - vb < -0.5 else ""}">{fmt_num(va - vb, 0)}</td>'
                      f'<td class="num">{pct(va, vb)}</td></tr>')
    linhas.append(f'<tr class="linha-total"><td>Total</td><td></td><td class="num">{tot[0]}</td>'
                  f'<td class="num">{fmt_num(tot[2], 0)}</td><td class="num">{fmt_num(tot[1], 0)}</td>'
                  f'<td class="num">{fmt_num(tot[1] - tot[2], 0)}</td><td class="num">{pct(tot[1], tot[2])}</td></tr>')
    por_classe = ('<table><thead><tr><th>Classe</th><th>Linha na DRE</th><th>Lançamentos</th>'
                  f'<th>{ctx.mes_anterior_curto} (R$)</th><th>{ctx.mes_atual_curto} (R$)</th><th>Δ (R$)</th><th>Δ (%)</th></tr></thead>'
                  f'<tbody>{"".join(linhas)}</tbody></table>')

    rub = (atual[atual["Classe"] != "EXCLUIR"].groupby(["Rubrica", "Classe"]).agg(qtd=("Valor Parcela", "size"), valor=("Valor Parcela", "sum"))
           .reset_index().sort_values("valor", ascending=False).head(30))
    linhas_r = "".join(
        f'<tr><td>{html.escape(str(r.Rubrica))}</td><td>{html.escape(str(r.Classe))}</td><td class="num">{r.qtd}</td>'
        f'<td class="num">{fmt_num(r.valor, 2)}</td></tr>' for r in rub.itertuples())
    por_rubrica = ('<table><thead><tr><th>Rubrica</th><th>Classe</th><th>Lançamentos</th><th>Valor (R$)</th></tr></thead>'
                   f'<tbody>{linhas_r}</tbody></table>')

    cid = atual.assign(Cidade=atual["__cidade"].fillna("(sem cidade)")).pivot_table(
        index="Cidade", columns="Classe", values="Valor Parcela", aggfunc="sum", fill_value=0)
    cid = cid.reindex(columns=[c for c in CLASSES_ORDEM if c in cid.columns])
    cid["Total"] = cid.sum(axis=1)
    cid = cid.sort_values("Total", ascending=False)
    cab = "".join(f"<th>{NOME_CLASSE[c]}</th>" for c in cid.columns[:-1]) + "<th>Total</th>"
    linhas_c = "".join(
        f'<tr><td>{html.escape(str(idx))}</td><td>{html.escape(SUP_POR_CIDADE.get(chave_texto(idx), SEM_SUP))}</td>'
        + "".join(f'<td class="num">{fmt_num(v, 0)}</td>' for v in row) + "</tr>" for idx, row in cid.iterrows())
    por_cidade = f'<table><thead><tr><th>Cidade</th><th>SUP</th>{cab}</tr></thead><tbody>{linhas_c}</tbody></table>'
    return por_classe, por_cidade, por_rubrica


def gera_aba_indiretas_html(ctx):
    prepara(ctx)
    if not len(ctx.avulso):
        return '<div class="card"><h2>Indiretas</h2><p>Nenhum arquivo de serviço avulso encontrado na pasta (o nome precisa conter "avulso").</p></div>'
    blocos = []
    for sup in lista_sups(ctx):
        por_classe, por_cidade, por_rubrica = tabela_indiretas(ctx, sup)
        blocos.append(
            f'<div class="sup-bloco" data-sup="{html.escape(sup, quote=True)}">'
            f'<div class="card"><h2>Indiretas por classe — {html.escape(_nome_sup(sup))}</h2>'
            f'<p class="nota-secao">Receita de serviços avulsos de {ctx.mes_atual} comparada com {ctx.mes_anterior}. A classe vem da rubrica (relação em regras.json).</p>'
            f'<div class="tabela-wrap">{por_classe}</div></div>'
            f'<div class="card"><h2>Por cidade — {ctx.mes_atual}</h2><div class="tabela-wrap">{por_cidade}</div></div>'
            f'<div class="card"><h2>Maiores rubricas — {ctx.mes_atual}</h2><div class="tabela-wrap">{por_rubrica}</div></div></div>')
    return "".join(blocos)


def gera_seletor_sup_html(ctx):
    opcoes = "".join(f'<option value="{html.escape(s, quote=True)}">{html.escape(_nome_sup(s) if s == TODAS else s)}</option>'
                     for s in lista_sups(ctx))
    return ('<label class="seletor-sup" id="seletorSup" hidden>Superintendência '
            f'<select onchange="trocarSup(this.value)">{opcoes}</select></label>')
