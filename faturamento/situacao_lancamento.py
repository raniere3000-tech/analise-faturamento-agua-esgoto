# -*- coding: utf-8 -*-
"""Aba Diretas — cards da "Situacao Lancamento" da fatura de ciclo: como cada conta foi lançada (leitura real, média,
mínimo, estimado...), quanto pesa em ligações, volume e valor, e por que vale analisar cada situação."""
import html
import json

import pandas as pd

from .formatacao import fmt_num


COLUNA = "Situacao Lancamento"
SEM_SITUACAO = "(sem situação)"

POR_QUE_GERAL = (
    "A situação de lançamento diz <b>o que aconteceu com a conta depois de emitida</b>: se foi entregue ao cliente (e como), "
    "se ficou <b>retida</b> para análise (aumento ou queda de consumo, ligação bloqueada, NFAG, recálculo), se foi consolidada "
    "(órgãos públicos) ou se não foi entregue. Conta retida ou não entregue é faturamento que <b>não chega ao cliente</b>: atrasa a "
    "arrecadação e pode virar reclamação ou refaturamento. Comparar com o mês anterior mostra se as retenções estão crescendo e "
    "onde agir; a visão <b>sintética</b> junta os códigos pela leitura da situação.")

OUTROS = "Outros"
# por que analisar cada grupo da visão sintética (os códigos de cada grupo estão em regras.json → situacao_lancamento_grupos)
POR_QUE_GRUPO = {
    "Entregue": "Conta entregue ao cliente (em mãos, caixa de correio, portão, vizinho, caixa de luz, hidrômetro). É a base da "
                "arrecadação do mês. Vale olhar a forma de entrega: portão e caixa de luz têm mais risco de extravio e de reclamação "
                "de \"não recebi a conta\".",
    "Retida": "Conta emitida, mas retida (emitido-retida, NFAG, ligação bloqueada, recalculada). O valor não chega ao cliente "
              "enquanto não for liberado: atrasa a arrecadação. Crescimento indica gargalo na análise ou problema de cadastro/crítica.",
    "Público": "Contas retidas para consolidação (clientes públicos / faturas consolidadas). Poucos clientes com valor alto: "
               "acompanhar o envio da fatura consolidada e o prazo de pagamento.",
    "Aumento de Consumo": "Retida pela crítica porque o consumo passou de 2× a média (medida ou faturada). Precisa de análise antes "
                          "de liberar: pode ser vazamento ou erro de leitura. Reter demais atrasa a receita; liberar sem análise gera "
                          "reclamação e refaturamento.",
    "Queda de Consumo": "Retida por queda de consumo: risco de perda de receita (hidrômetro parado, fraude, imóvel vazio, erro de "
                        "leitura). Conferir antes de liberar e cruzar com o Top 100 de quedas.",
    "Não Entregue": "Conta não entregue ao cliente: risco de inadimplência e de reclamação. Verificar endereço, rota de entrega e "
                    "imóveis sem acesso.",
    OUTROS: "Código fora da relação de situações (regras.json → situacao_lancamento_grupos). Cadastre o código no grupo certo "
            "para ele entrar na visão sintética.",
}
ORDEM_GRUPOS = ["Entregue", "Retida", "Público", "Aumento de Consumo", "Queda de Consumo", "Não Entregue", OUTROS]


def _grupos_cadastrados():
    from .config import REGRAS, chave_texto
    return {chave_texto(k): str(v).strip() for k, v in (REGRAS.get("situacao_lancamento_grupos") or {}).items()
            if not k.startswith("_")}


_GRUPOS = None


def grupo_da_situacao(situacao):
    """Leitura da situação (grupo da visão sintética) de um código; 'Outros' se não estiver cadastrado."""
    global _GRUPOS
    from .config import chave_texto
    if _GRUPOS is None:
        _GRUPOS = _grupos_cadastrados()
    return _GRUPOS.get(chave_texto(situacao), OUTROS)


def classifica(situacao):
    """(leitura da situação, por que analisar) de um código de situação de lançamento."""
    g = grupo_da_situacao(situacao)
    return g, POR_QUE_GRUPO.get(g, POR_QUE_GRUPO[OUTROS])


def _por_ligacao(df):
    """Uma linha por ligação (rubrica de água): situação, economias, volume e valor de água + esgoto."""
    if df is None or not len(df) or COLUNA not in df.columns:
        return pd.DataFrame(columns=["N. Ligação", "Situação", "Economias", "Volume", "Valor"])
    serv = df["__serv"] if "__serv" in df.columns else df["Rubrica"].astype(str).str.upper().map(
        lambda r: "E" if "ESGOTO" in r else "A" if "AGUA" in r else "")
    d = df[serv != ""]
    agua = d[serv[serv != ""] == "A"]
    sit = agua[COLUNA].astype(object).where(agua[COLUNA].notna(), SEM_SITUACAO).astype(str).str.strip().replace("", SEM_SITUACAO)
    pos = pd.to_numeric(agua["Consumo Faturado"], errors="coerce").fillna(0)
    lig = pd.DataFrame({"N. Ligação": agua["N. Ligação"].values, "Situação": sit.values,
                        "Economias": pd.to_numeric(agua["Economias_Totais"], errors="coerce").fillna(0).where(pos > 0, 0).values,
                        "Volume": pos.where(pos > 0, 0).values})
    extras = {c: c for c in ("Nome Cliente", "Grupo", "Categoria", "__sup") if c in agua.columns}
    for c in extras:
        lig[c] = agua[c].values
    lig = lig.groupby("N. Ligação").agg(Situação=("Situação", "first"), Economias=("Economias", "sum"), Volume=("Volume", "sum"),
                                        **{c: (c, "first") for c in extras})
    valor = pd.to_numeric(d["Valor (R$)"], errors="coerce").fillna(0).groupby(d["N. Ligação"].values).sum()
    lig["Valor"] = valor.reindex(lig.index).fillna(0)
    return lig.reset_index()


def detalhe_ligacoes(df_at, df_ant, mes, mes_ant):
    """Uma linha por ligação do mês atual (rubrica de água): a lista que as setas baixam (por código, por grupo ou inteira)."""
    at, ant = _por_ligacao(df_at), _por_ligacao(df_ant)
    if not len(at):
        return pd.DataFrame()
    ant = ant.set_index("N. Ligação")
    d = pd.DataFrame({"N. Ligação": at["N. Ligação"]})
    for c, nome in (("Nome Cliente", "Nome Cliente"), ("Grupo", "Grupo"), ("Categoria", "Categoria"), ("__sup", "Superintendência")):
        if c in at.columns:
            d[nome] = at[c].values
    d[f"Situação Lançamento {mes}"] = at["Situação"].values
    d[f"Leitura da situação {mes}"] = at["Situação"].map({v: grupo_da_situacao(v) for v in at["Situação"].unique()}).values
    d[f"Situação Lançamento {mes_ant}"] = at["N. Ligação"].map(ant["Situação"]).fillna("").values if len(ant) else ""
    d[f"Economias {mes}"] = at["Economias"].values
    d[f"Volume {mes}"] = at["Volume"].values
    d[f"Volume {mes_ant}"] = at["N. Ligação"].map(ant["Volume"]).values if len(ant) else None
    d[f"Valor água + esgoto {mes}"] = at["Valor"].values
    d[f"Valor água + esgoto {mes_ant}"] = at["N. Ligação"].map(ant["Valor"]).values if len(ant) else None
    num = d.select_dtypes("number").columns
    d[num] = d[num].round(2)                           # sem resto de ponto flutuante no CSV (322,67 e não 322,66999…)
    return d.sort_values([f"Situação Lançamento {mes}", "N. Ligação"]).reset_index(drop=True)


def _csv_gz_b64(df):
    """CSV (";" e vírgula decimal, como as bases) comprimido em gzip e em base64 — o navegador descompacta na hora de baixar."""
    import base64
    import gzip
    texto = "\ufeff" + df.to_csv(sep=";", decimal=",", index=False)
    return base64.b64encode(gzip.compress(texto.encode("utf-8"), 6)).decode("ascii")


def _agrega_grupo(df):
    """[[sup, grupo, situação, ligações, economias, volume, valor], ...] — uma linha por SUP × grupo × situação."""
    lig = _por_ligacao(df)
    if not len(lig):
        return []
    for c in ("__sup", "Grupo"):
        if c not in lig.columns:
            lig[c] = ""
    g = lig.groupby(["__sup", "Grupo", "Situação"], observed=True).agg(
        n=("N. Ligação", "size"), eco=("Economias", "sum"), vol=("Volume", "sum"), val=("Valor", "sum")).reset_index()
    return [[str(a), str(b).strip(), str(c), int(n), round(float(e), 2), round(float(v), 2), round(float(x), 2)]
            for a, b, c, n, e, v, x in g.itertuples(index=False)]


def resumo_situacoes(df_at, df_ant, sintetico=False):
    """Uma linha por situação (ou, com sintetico=True, por leitura da situação — o grupo): ligações, economias, volume e
    valor (água + esgoto) nos dois meses e as variações. Na sintética, 'Leitura da situação' lista os códigos do grupo."""
    at, ant = _por_ligacao(df_at), _por_ligacao(df_ant)
    if not len(at) and not len(ant):
        return pd.DataFrame()
    codigos = {}
    if sintetico:
        for d in (at, ant):
            for cod in d["Situação"].unique():
                codigos.setdefault(grupo_da_situacao(cod), set()).add(str(cod))
            d["Situação"] = d["Situação"].map(lambda c: grupo_da_situacao(c))

    def soma(d, suf):
        return d.groupby("Situação").agg(**{f"Ligações {suf}": ("N. Ligação", "size"), f"Economias {suf}": ("Economias", "sum"),
                                            f"Volume {suf}": ("Volume", "sum"), f"Valor {suf}": ("Valor", "sum")})
    r = soma(at, "atual").join(soma(ant, "anterior"), how="outer").fillna(0)
    for suf in ("atual", "anterior"):
        tot = r[f"Ligações {suf}"].sum()
        r[f"% ligações {suf}"] = r[f"Ligações {suf}"] / tot * 100 if tot else 0.0
        r[f"Vol./economia {suf}"] = (r[f"Volume {suf}"] / r[f"Economias {suf}"].where(r[f"Economias {suf}"] > 0)).fillna(0)
    r["Δ ligações"] = r["Ligações atual"] - r["Ligações anterior"]
    r["Δ p.p. participação"] = r["% ligações atual"] - r["% ligações anterior"]
    r["Δ valor"] = r["Valor atual"] - r["Valor anterior"]
    r = r.sort_values(["Ligações atual", "Ligações anterior"], ascending=False).reset_index()
    if sintetico:
        r.insert(1, "Leitura da situação", r["Situação"].map(lambda g: ", ".join(sorted(codigos.get(g, ())))))
        r["Por que analisar"] = r["Situação"].map(lambda g: POR_QUE_GRUPO.get(g, POR_QUE_GRUPO[OUTROS]))
    else:
        r.insert(1, "Leitura da situação", r["Situação"].map(lambda c: classifica(c)[0]))
        r["Por que analisar"] = r["Situação"].map(lambda c: classifica(c)[1])
    return r


def _card(linha, mes, ant, sup="TODAS", sintetico=False):
    # data-f: campos que o filtro de grupos refaz no navegador (sitlRecalcular)
    def var(v, dec=0, suf="", f=""):
        cor = "#C2560C" if v < 0 else "#176b9c" if v > 0 else "#49668C"
        sinal = "+" if v > 0 else ""
        return f'<span data-f="{f}" style="color:{cor};font-weight:600">{sinal}{fmt_num(v, dec)}{suf}</span>'
    attr = "data-gsit" if sintetico else "data-sit"
    return f"""
    <div class="sitl-card" {attr}="{html.escape(str(linha['Situação']), quote=True)}">
      <div class="sitl-topo"><b>{html.escape(str(linha['Situação']))}{_seta(linha, sup, sintetico)}</b><span>{html.escape(linha['Leitura da situação'])}</span></div>
      <div class="sitl-num"><span>Ligações {html.escape(mes)}</span><b data-f="lig">{fmt_num(linha['Ligações atual'])}</b>
        <small><span data-f="pct">{fmt_num(linha['% ligações atual'], 1)}</span>% do total · {var(linha['Δ p.p. participação'], 1, ' p.p.', 'pp')} vs {html.escape(ant)}</small></div>
      <ul class="sitl-lista">
        <li><span>Δ ligações</span>{var(linha['Δ ligações'], f='dlig')}</li>
        <li><span>Volume (m³)</span><b data-f="vol">{fmt_num(linha['Volume atual'])}</b></li>
        <li><span>Vol./economia</span><b data-f="vme">{fmt_num(linha['Vol./economia atual'], 2)}</b> <small>(<span data-f="vmeant">{fmt_num(linha['Vol./economia anterior'], 2)}</span>)</small></li>
        <li><span>Valor água + esgoto</span><b data-f="val">R$ {fmt_num(linha['Valor atual'], 2)}</b></li>
        <li><span>Δ valor</span>{var(linha['Δ valor'], 2, f='dval')}</li>
      </ul>
      <p class="sitl-porque"><b>Por que analisar:</b> {html.escape(linha['Por que analisar'])}</p>
    </div>"""


def _seta(linha, sup, sintetico=False):
    """Seta que baixa (CSV) as ligações desta situação — ou de todos os códigos do grupo, na sintética."""
    if not linha["Ligações atual"]:
        return ""
    e = lambda v: html.escape(str(v), quote=True)
    attr = "data-gsit" if sintetico else "data-sit"
    return (f' <button type="button" class="btn-sitl-dl" {attr}="{e(linha["Situação"])}" data-sup="{e(sup)}" '
            f'title="Baixar as matrículas de {e(linha["Situação"])} (CSV)" aria-label="Baixar as matrículas de {e(linha["Situação"])}">&#11015;</button>')


def gera_cards_situacao_html(ctx):
    """Um quadro por superintendência (o filtro Superintendência mostra o escolhido), com a visão analítica (um card por
    código) e a sintética (um card por leitura da situação); o botão Analítica/Sintética troca as duas em todos os quadros."""
    from .dre import TODAS, _nome_sup, lista_sups
    ctx.resultados["situacao_lancamento"] = {}
    ctx.resultados["situacao_lancamento_sintetica"] = {}
    if COLUNA not in ctx.df_atual.columns and COLUNA not in ctx.df_anterior.columns:
        return ("<div class='card'><h2>Situação de lançamento</h2><p class='nota-secao'>A fatura de ciclo não tem a coluna "
                "<b>Situacao Lancamento</b>: os cards aparecem quando ela vier no arquivo.</p></div>")
    blocos = []
    for sup in lista_sups(ctx):
        at, an = ctx.df_atual, ctx.df_anterior
        if sup != TODAS:
            at, an = at[at["__sup"] == sup], an[an["__sup"] == sup]
        r = resumo_situacoes(at, an)
        rs = resumo_situacoes(at, an, sintetico=True)
        ctx.resultados["situacao_lancamento"][sup] = r
        ctx.resultados["situacao_lancamento_sintetica"][sup] = rs
        suf = "" if sup == TODAS else f" — {_nome_sup(sup)}"
        ds = html.escape(sup, quote=True)
        seta_base = (f'<button type="button" class="btn-sitl-dl" data-sup="{ds}" title="Baixar a base analítica com as matrículas (CSV)" '
                     f'aria-label="Baixar a base analítica com as matrículas">&#11015;</button>') if len(r) else ""
        cards = "".join(_card(l, ctx.mes_atual, ctx.mes_anterior, sup) for _, l in r.iterrows()) or "<p>Sem dados</p>"
        cards_s = "".join(_card(l, ctx.mes_atual, ctx.mes_anterior, sup, True) for _, l in rs.iterrows()) or "<p>Sem dados</p>"
        blocos.append(f"""<div class="sup-top-bloco" data-sup="{ds}">
    <div class="card">
    <h2 style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">Situação de lançamento — {html.escape(ctx.mes_atual)} × {html.escape(ctx.mes_anterior)}{html.escape(suf)} {seta_base}
      <span class="sitl-visao" role="group" aria-label="Visão"><button type="button" data-visao="analitica" class="ativo" aria-pressed="true">Analítica</button><button type="button" data-visao="sintetica" aria-pressed="false">Sintética</button></span></h2>
    <p class="nota-secao">{POR_QUE_GERAL}</p>
    <p class="nota-secao">Contagem por ligação (rubrica de água; a situação é a da conta no mês). Volume e economias só onde Consumo Faturado &gt; 0;
    valor = água + esgoto da ligação. Variações contra o mês anterior; p.p. = pontos percentuais na participação das ligações.
    A seta ao lado do título baixa todas as matrículas; a de cada card, só as daquela situação (ou do grupo, na sintética).</p>
    <div class="sitl-grid" data-visao="analitica">{cards}</div>
    <div class="sitl-grid" data-visao="sintetica" hidden>{cards_s}</div>
    </div></div>""")
    # lista por ligação embutida uma vez (comprimida); as setas filtram situação/grupo, SUP e grupos marcados na hora de baixar
    det = detalhe_ligacoes(ctx.df_atual, ctx.df_anterior, ctx.mes_atual, ctx.mes_anterior)
    ctx.resultados["situacao_detalhe"] = det
    m = html.escape(ctx.mes_atual, quote=True)
    dados = (f'<script type="application/octet-stream" id="sitl-detalhe" data-col-sit="Situação Lançamento {m}" '
             f'data-col-gsit="Leitura da situação {m}" '
             f'data-arquivo="Situacao_Lancamento_{ctx.mes_atual.replace("/", "-")}">{_csv_gz_b64(det)}</script>') if len(det) else ""
    # totais por SUP × grupo × situação (mês atual e anterior): o filtro de grupos refaz os cards com eles
    at_ag, ant_ag = _agrega_grupo(ctx.df_atual), _agrega_grupo(ctx.df_anterior)
    agregados = {"at": at_ag, "ant": ant_ag,
                 "grupo": {l[2]: grupo_da_situacao(l[2]) for l in at_ag + ant_ag}}
    dados += ('<script type="application/json" id="sitl-agregados">'
              + json.dumps(agregados, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    return "".join(blocos) + dados
