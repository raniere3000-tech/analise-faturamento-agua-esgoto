# -*- coding: utf-8 -*-
"""Aba Análise: ligações cortadas com consumo no mês atual (possível irregularidade, ex.: religação por conta própria).

Critério: linha de água do mês atual com Situação Ligação "CORT…" e Consumo Medido > 0. Só a medição é
referência (o Consumo Faturado entra como informação); sem a coluna Consumo Medido a seção fica vazia. Uma linha por ligação, da maior para a menor medição. O filtro de grupos e o de
Superintendência escondem as linhas e refazem os totais no navegador (cortRecalcular, relatorio.js).
"""
import html

import pandas as pd

from .analitico import _norm_situacao
from .formatacao import fmt_num


def _num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _agua_do_mes(b, ref):
    b = b[b["Referencia de Leitura"] == ref]
    serv = b["__serv"] if "__serv" in b.columns else b["Rubrica"].astype(str).str.upper().map(
        lambda r: "E" if "ESGOTO" in r else "A" if "AGUA" in r else "")
    return b[serv == "A"]


def monta_cortadas_consumo(ctx):
    """DataFrame com as ligações cortadas que têm consumo no mês atual (vazio se não houver)."""
    b = ctx.base_final
    if b is None or "Situacao Ligacao" not in b.columns:
        return pd.DataFrame()
    if "Consumo Medido" not in b.columns:            # a referência é só a medição: sem ela não há o que apontar
        return pd.DataFrame()
    col_med = "Consumo Medido"
    at = _agua_do_mes(b, ctx.ref_atual)
    cortada = at["Situacao Ligacao"].map(_norm_situacao) == "Cortada"
    at = at[cortada]
    if not len(at):
        return pd.DataFrame()
    lig = at["N. Ligação"].astype(str).str.strip()
    med, fat, val = _num(at[col_med]), _num(at["Consumo Faturado"]), _num(at["Valor (R$)"])
    soma = pd.DataFrame({"med": med.values, "fat": fat.values, "val": val.values}, index=lig.values).groupby(level=0).sum()
    soma = soma[soma["med"] > 0]
    if not len(soma):
        return pd.DataFrame()
    cols = [c for c in ("Grupo", "Nome Cliente", "Categoria", "__sup", "Situacao Lancamento", "Economias_Totais",
                        "Nome da Localidade", "Zona") if c in at.columns]
    desc = at[cols].assign(__lig=lig.values).drop_duplicates("__lig").set_index("__lig").reindex(soma.index)

    # mês anterior: se já estava cortada e quanto mediu (cortada há mais de um mês e medindo pesa mais)
    an = _agua_do_mes(b, ctx.ref_anterior)
    lig_an = an["N. Ligação"].astype(str).str.strip()
    med_an = _num(an[col_med]).groupby(lig_an.values).sum()
    sit_an = an["Situacao Ligacao"].map(_norm_situacao).groupby(lig_an.values).first()

    d = pd.DataFrame(index=soma.index)
    d.index.name = "N. Ligação"
    d["Nome Cliente"] = desc.get("Nome Cliente")
    d["Grupo"] = desc.get("Grupo")
    d["Localidade"] = desc.get("Nome da Localidade")
    d["Zona"] = desc.get("Zona")
    d["Categoria"] = desc.get("Categoria")
    d["Superintendência"] = desc.get("__sup")
    d["Situação Lançamento"] = desc.get("Situacao Lancamento")
    d["Economias"] = _num(desc["Economias_Totais"]) if "Economias_Totais" in desc.columns else 0
    d[f"Consumo Medido {ctx.ref_anterior}"] = med_an.reindex(d.index)
    d[f"Situação {ctx.ref_anterior}"] = sit_an.reindex(d.index).replace("", "Outra").fillna("Sem fatura")
    d[f"Consumo Medido {ctx.ref_atual}"] = soma["med"]
    d[f"Consumo Faturado {ctx.ref_atual}"] = soma["fat"]
    d[f"Valor Água {ctx.ref_atual} (R$)"] = soma["val"]
    return d.sort_values(f"Consumo Medido {ctx.ref_atual}", ascending=False).reset_index()


def gera_cortadas_consumo_html(ctx):
    d = monta_cortadas_consumo(ctx)
    ctx.resultados["cortadas_consumo"] = d
    titulo = f"Cortadas com consumo — possível irregularidade ({ctx.mes_atual})"
    if not len(d):
        msg = ("Nenhuma ligação cortada com consumo medido no mês." if "Consumo Medido" in ctx.base_final.columns
               else "A base de consumo não tem a coluna Consumo Medido: sem ela não dá para apontar cortadas medindo.")
        return f"<div class='card' id='cortadas-consumo'><h2>{titulo}</h2><p>{msg}</p></div>"
    ra, rn = ctx.ref_atual, ctx.ref_anterior
    e = lambda v: html.escape("" if pd.isna(v) else str(v), quote=True)
    rot = "Baixar a lista (Excel), com os filtros de grupo e Superintendência"
    dl = (f'<button type="button" class="btn-just btn-cortadas" data-mes="{e(ctx.mes_atual.replace("/", "-"))}" '
          f'title="{rot}" aria-label="{rot}">&#11015;&#8801;</button>')
    linhas = []
    for _, r in d.iterrows():
        med, med_an = r[f"Consumo Medido {ra}"], r[f"Consumo Medido {rn}"]
        sit_an = r[f"Situação {rn}"]
        reinc = sit_an == "Cortada" and (med_an or 0) > 0     # cortada e medindo há dois meses seguidos
        destaque = " style='color:#C2560C;font-weight:700'" if reinc else ""
        linhas.append(
            f'<tr data-grupo="{e(r["Grupo"])}" data-sup="{e(r["Superintendência"])}" data-med="{med}" '
            f'data-val="{r[f"Valor Água {ra} (R$)"]}" data-reinc="{int(reinc)}">'
            f'<td>{e(r["N. Ligação"])}</td><td style="text-align:left">{e(r["Nome Cliente"])}</td><td>{e(r["Grupo"])}</td>'
            f'<td style="text-align:left">{e(r["Localidade"])}</td><td>{e(r["Zona"])}</td>'
            f'<td style="text-align:left">{e(r["Categoria"])}</td><td>{fmt_num(r["Economias"])}</td>'
            f'<td>{"—" if pd.isna(med_an) else fmt_num(med_an, 1)}</td>'
            f'<td{destaque}>{e(sit_an)}</td>'
            f'<td style="font-weight:700">{fmt_num(med, 1)}</td><td>{fmt_num(r[f"Consumo Faturado {ra}"], 1)}</td>'
            f'<td>R$ {fmt_num(r[f"Valor Água {ra} (R$)"], 2)}</td>'
            f'<td style="text-align:left">{e(r["Situação Lançamento"])}</td></tr>')
    return f"""
    <div class="card" id="cortadas-consumo">
    <h2 style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">{titulo} {dl}</h2>
    <p class="nota-secao">Ligações com Situação Ligação <b>cortada</b> no mês e Consumo Medido &gt; 0 (só a medição conta; o faturado aparece apenas como informação) na conta de água: se está cortada,
    não deveria medir. Pode ser religação por conta própria, corte não executado ou situação cadastral errada. Em
    <span style="color:#C2560C;font-weight:700">laranja</span>, as que já estavam cortadas e medindo em {rn}.</p>
    <div class="cort-cards" style="display:flex; gap:12px; flex-wrap:wrap; margin:8px 0 12px;">
      <div class="cort-card"><span>Ligações</span><b id="cort-qtd">{fmt_num(len(d))}</b></div>
      <div class="cort-card"><span>Volume medido (m³)</span><b id="cort-med">{fmt_num(d[f"Consumo Medido {ra}"].sum(), 1)}</b></div>
      <div class="cort-card"><span>Valor de água faturado</span><b id="cort-val">R$ {fmt_num(d[f"Valor Água {ra} (R$)"].sum(), 2)}</b></div>
      <div class="cort-card"><span>Cortadas e medindo há 2 meses</span><b id="cort-reinc">—</b></div>
    </div>
    <div class="table-wrap" style="max-height:520px; overflow:auto;">
    <table class="tabela-cortadas" id="tabela-cortadas-consumo">
    <thead><tr><th>Ligação</th><th>Cliente</th><th>Grupo</th><th>Localidade</th><th>Zona</th><th>Categoria</th><th>Economias</th><th>Medido {rn} (m³)</th>
    <th>Situação {rn}</th><th>Medido {ra} (m³)</th><th>Faturado {ra} (m³)</th><th>Valor água {ra}</th><th>Situação lançamento</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody></table></div>
    </div>"""


# ---------------------------------------------------------------------------------------------------------------
# Cortadas com consumo nos 3 últimos meses (m-2, m-1 e o atual): em quais meses cada ligação apareceu cortada
# medindo. Combinação = a lista desses meses (ex.: "08/2026 + 09/2026"); o filtro de grupos/SUP e o clique numa
# combinação são feitos no navegador (cort3Recalcular, relatorio.js).
# ---------------------------------------------------------------------------------------------------------------

def refs_3meses(ctx):
    atual = pd.to_datetime(ctx.ref_atual, format="%m/%Y")
    return [(atual - pd.DateOffset(months=k)).strftime("%m/%Y") for k in (2, 1, 0)]


def _situacao_do_mes(b, ref):
    """Por ligação no mês: situação (Cortada/Ativa/Outra) e Consumo Medido da água."""
    ag = _agua_do_mes(b, ref)
    if not len(ag):
        return pd.DataFrame(columns=["sit", "med"])
    lig = ag["N. Ligação"].astype(str).str.strip()
    sit = ag["Situacao Ligacao"].map(_norm_situacao).replace("", "Outra")
    return pd.DataFrame({"sit": sit.groupby(lig.values).first(), "med": _num(ag["Consumo Medido"]).groupby(lig.values).sum()})


def combinacao_rotulo(chave, refs):
    meses = [r for r, c in zip(refs, chave) if c == "1"]
    return ("Só " + meses[0]) if len(meses) == 1 else " + ".join(meses)


# ordem de leitura: as que mais insistem primeiro, depois as que pararam e as que começaram agora
ORDEM_COMBOS = ["111", "110", "011", "101", "100", "010", "001"]


def monta_cortadas_3meses(ctx):
    """DataFrame: uma linha por ligação que esteve cortada com consumo medido em ao menos um dos 3 meses."""
    b = ctx.base_final
    if b is None or "Situacao Ligacao" not in b.columns or "Consumo Medido" not in b.columns:
        return pd.DataFrame()
    refs = refs_3meses(ctx)
    por_mes = [_situacao_do_mes(b, r) for r in refs]
    flags = [((m["sit"] == "Cortada") & (m["med"] > 0)) for m in por_mes]
    ligs = sorted(set().union(*[f[f].index for f in flags]))
    if not ligs:
        return pd.DataFrame()
    idx = pd.Index(ligs)
    chave = pd.Series("", index=idx)
    for f in flags:
        chave = chave + f.reindex(idx).fillna(False).astype(bool).map({True: "1", False: "0"})

    # dados descritivos da linha de água mais recente em que a ligação aparece
    cols = [c for c in ("Grupo", "Nome Cliente", "Categoria", "__sup", "Nome da Localidade", "Zona") if c in b.columns]
    ag = pd.concat([_agua_do_mes(b, r) for r in reversed(refs)])
    desc = ag[cols].assign(__lig=ag["N. Ligação"].astype(str).str.strip().values).drop_duplicates("__lig").set_index("__lig").reindex(idx)

    d = pd.DataFrame(index=idx)
    d.index.name = "N. Ligação"
    d["Nome Cliente"] = desc.get("Nome Cliente")
    d["Grupo"] = desc.get("Grupo")
    d["Localidade"] = desc.get("Nome da Localidade")
    d["Zona"] = desc.get("Zona")
    d["Categoria"] = desc.get("Categoria")
    d["Superintendência"] = desc.get("__sup")
    d["Chave"] = chave
    d["Combinação"] = chave.map(lambda c: combinacao_rotulo(c, refs))
    for r, m in zip(refs, por_mes):
        d[f"Situação {r}"] = m["sit"].reindex(idx).fillna("Sem fatura")
        d[f"Consumo Medido {r}"] = m["med"].reindex(idx)
    d["Medido nos 3 meses"] = d[[f"Consumo Medido {r}" for r in refs]].sum(axis=1)
    d["__ordem"] = d["Chave"].map({c: i for i, c in enumerate(ORDEM_COMBOS)})
    d = d.sort_values(["__ordem", "Medido nos 3 meses"], ascending=[True, False]).drop(columns="__ordem")
    return d.reset_index()


def gera_cortadas_3meses_html(ctx):
    d = monta_cortadas_3meses(ctx)
    ctx.resultados["cortadas_3meses"] = d
    refs = refs_3meses(ctx)
    titulo = f"Cortadas com consumo nos 3 últimos meses ({refs[0]} a {refs[2]})"
    if not len(d):
        return ""
    e = lambda v: html.escape("" if pd.isna(v) else str(v), quote=True)
    ra = refs[2]
    faltam = [r for r in refs if not (ctx.base_final["Referencia de Leitura"] == r).any()]
    aviso = (f" <b>Atenção:</b> {', '.join(faltam)} não está na base carregada; as combinações com esse mês ficam zeradas."
             if faltam else "")
    sit_cls = {"Cortada": "cortada", "Ativa": "ativa", "Sem fatura": "semfat"}

    # resumo por combinação (o navegador refaz com os filtros)
    resumo = []
    for c in ORDEM_COMBOS:
        x = d[d["Chave"] == c]
        marcas = "".join(f'<td class="c3-marca">{"●" if k == "1" else ""}</td>' for k in c)
        sat = x[f"Situação {ra}"]
        resumo.append(
            f'<tr class="c3-combo" data-c3="{c}" title="Clique para ver só estas ligações">{marcas}'
            f'<td style="text-align:left">{e(combinacao_rotulo(c, refs))}</td>'
            f'<td class="c3-n" style="font-weight:700">{fmt_num(len(x))}</td><td class="c3-cort">{fmt_num((sat == "Cortada").sum())}</td>'
            f'<td class="c3-ativ">{fmt_num((sat == "Ativa").sum())}</td><td class="c3-sf">{fmt_num((~sat.isin(["Cortada", "Ativa"])).sum())}</td>'
            f'<td class="c3-med">{fmt_num(x["Medido nos 3 meses"].sum(), 1)}</td></tr>')
    linhas = []
    for _, r in d.iterrows():
        meses = "".join(
            f'<td>{e(r[f"Situação {m}"])}</td><td>{"—" if pd.isna(r[f"Consumo Medido {m}"]) else fmt_num(r[f"Consumo Medido {m}"], 1)}</td>'
            for m in refs)
        linhas.append(
            f'<tr data-grupo="{e(r["Grupo"])}" data-sup="{e(r["Superintendência"])}" data-c3="{r["Chave"]}" '
            f'data-med="{r["Medido nos 3 meses"]}" data-sitat="{sit_cls.get(r[f"Situação {ra}"], "outra")}">'
            f'<td>{e(r["N. Ligação"])}</td><td style="text-align:left">{e(r["Nome Cliente"])}</td><td>{e(r["Grupo"])}</td>'
            f'<td style="text-align:left">{e(r["Localidade"])}</td><td>{e(r["Zona"])}</td>'
            f'<td style="text-align:left">{e(r["Categoria"])}</td><td style="text-align:left;font-weight:700">{e(r["Combinação"])}</td>'
            f'{meses}<td style="font-weight:700">{fmt_num(r["Medido nos 3 meses"], 1)}</td></tr>')
    rot = "Baixar a lista (Excel), com os filtros de grupo, Superintendência e combinação"
    dl = (f'<button type="button" class="btn-just btn-cortadas3" data-mes="{e(ctx.mes_atual.replace("/", "-"))}" '
          f'title="{rot}" aria-label="{rot}">&#11015;&#8801;</button>')
    cab_meses = "".join(f"<th>Situação {m}</th><th>Medido {m} (m³)</th>" for m in refs)
    return f"""
    <div class="card" id="cortadas-3meses">
    <h2 style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">{titulo} {dl}</h2>
    <p class="nota-secao">Ligações que apareceram <b>cortadas com Consumo Medido &gt; 0</b> na conta de água em pelo menos um dos
    três meses, agrupadas pela combinação de meses em que isso aconteceu (● = cortada medindo no mês). Só a medição conta.
    As colunas da direita dizem como a ligação está em {ra}: ainda cortada, ativa (religada) ou sem fatura.
    Clique numa combinação para ver só as ligações dela; clique de novo para ver todas.{aviso}</p>
    <div class="table-wrap">
    <table class="tabela-cortadas tabela-c3" id="tabela-cortadas-3meses-resumo">
    <thead><tr>{"".join(f"<th>{m}</th>" for m in refs)}<th>Combinação</th><th>Ligações</th><th>Ainda cortadas em {ra}</th>
    <th>Ativas em {ra}</th><th>Sem fatura / outra em {ra}</th><th>Medido nos 3 meses (m³)</th></tr></thead>
    <tbody>{"".join(resumo)}</tbody>
    <tfoot><tr><td colspan="4" style="text-align:left">Total</td><td class="c3-n">{fmt_num(len(d))}</td><td class="c3-cort"></td>
    <td class="c3-ativ"></td><td class="c3-sf"></td><td class="c3-med">{fmt_num(d["Medido nos 3 meses"].sum(), 1)}</td></tr></tfoot></table></div>
    <p class="c3-filtro-info" id="c3-filtro-info" style="margin:10px 0 6px; font-size:12.5px; color:#49668C;">Mostrando todas as combinações.</p>
    <div class="table-wrap" style="max-height:520px; overflow:auto;">
    <table class="tabela-cortadas" id="tabela-cortadas-3meses">
    <thead><tr><th>Ligação</th><th>Cliente</th><th>Grupo</th><th>Localidade</th><th>Zona</th><th>Categoria</th><th>Combinação</th>
    {cab_meses}<th>Medido nos 3 meses (m³)</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody></table></div>
    </div>"""
