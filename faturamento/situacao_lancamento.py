# -*- coding: utf-8 -*-
"""Aba Diretas — cards da "Situacao Lancamento" da fatura de ciclo: como cada conta foi lançada (leitura real, média,
mínimo, estimado...), quanto pesa em ligações, volume e valor, e por que vale analisar cada situação."""
import html
import json
import re
import unicodedata

import pandas as pd

from .formatacao import fmt_num


def chave_texto_espacos(s):
    """Maiúsculas, sem acento, mantendo a separação entre as palavras."""
    s = unicodedata.normalize("NFKD", "" if s is None else str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).upper()

COLUNA = "Situacao Lancamento"
SEM_SITUACAO = "(sem situação)"

POR_QUE_GERAL = (
    "A situação de lançamento diz <b>como o consumo da conta foi apurado</b>. Só a leitura real mede o que o cliente consumiu; "
    "nas demais (média, mínimo, estimado, informado...) o volume é <b>calculado</b>, e o faturamento pode ficar abaixo ou acima "
    "do consumo de verdade. Acompanhar a participação de cada situação mostra a <b>qualidade da leitura</b> do mês, explica "
    "quedas e aumentos de volume sem mudança de consumo (ex.: muitas contas saindo da média para a leitura real geram acerto) "
    "e aponta onde agir: leituras não realizadas, hidrômetros com problema e imóveis sem acesso.")

# (palavras-chave procuradas no código/descrição da situação, título, por que analisar) — a primeira que bater vale
REGRAS_SITUACAO = [
    (("CANCEL",), "Conta cancelada",
     "Conta lançada e depois cancelada: vira cancelamento na DRE. Crescimento indica erro de faturamento ou retrabalho; vale ver o motivo."),
    (("REFAT", "REVIS", "RETIF", "AJUST", "CORRIG", "ACERTO"), "Conta revisada / refaturada",
     "Conta corrigida depois do lançamento. Volume alto aqui indica problema de leitura ou de cadastro no mês anterior e mexe "
     "no faturamento sem relação com consumo."),
    (("NAOREALIZ", "SEMLEITURA", "NAOLID", "IMPEDI", "SEMACESSO", "FECHAD"), "Leitura não realizada",
     "O leiturista não conseguiu ler (imóvel fechado, sem acesso, impedimento). A conta sai pela média ou mínimo: fatura o passado, "
     "não o consumo real. Recorrência na mesma ligação é perda de receita e gera acerto quando a leitura volta."),
    (("MEDIA", "MEDIO"), "Consumo pela média",
     "Leitura não realizada (sem acesso, hidrômetro ilegível, anormalidade): o consumo é a média histórica. Fatura o passado, não o "
     "consumo real — quando a leitura volta, vem o acerto (para cima ou para baixo). Muitas contas na média = risco de receita e reclamação."),
    (("MINIM", "TAXA"), "Consumo mínimo",
     "Faturado pelo mínimo da categoria: consumo medido abaixo do mínimo ou sem medição. Crescimento pode indicar imóvel vazio, "
     "hidrômetro parado ou fraude; ver as maiores quedas do Top 100 nessa situação."),
    (("ESTIM", "PRESUM", "ARBITR"), "Consumo estimado",
     "Volume estimado (sem hidrômetro ou sem leitura possível). Não mede o consumo real; acompanhar para priorizar instalação ou "
     "troca de hidrômetro."),
    (("FIXO", "FIXA", "SEMHIDR", "SEMMEDI", "NAOMEDI"), "Consumo fixo / sem medição",
     "Ligação sem hidrômetro, faturada por volume fixo. Potencial de receita na hidrometração; o volume não acompanha o consumo."),
    (("INFORM", "AUTOLEIT", "CLIENTE"), "Leitura informada",
     "Leitura passada pelo próprio cliente (autoleitura / informada). Conferir a consistência: risco de leitura subdeclarada."),
    (("ANORM", "PARAD", "QUEBR", "DEFEIT", "VAZAMENTO", "INVERT"), "Leitura com anormalidade",
     "A leitura teve ocorrência (hidrômetro parado, quebrado, invertido, vazamento...). Normalmente vira média ou mínimo; é a fila "
     "de serviços de campo para recuperar a medição."),
    (("CORT", "SUPRIM", "DESLIG"), "Ligação cortada / suprimida",
     "Conta de ligação cortada ou suprimida. Faturamento deveria ser baixo; valores relevantes aqui merecem conferência (religação "
     "sem baixa, consumo irregular)."),
    (("NORMAL", "REAL", "LIDA", "LEITURA", "MEDID"), "Leitura real",
     "Consumo medido no hidrômetro: é o cenário ideal. Quanto maior a participação, mais confiável o volume faturado do mês; "
     "queda na participação puxa contas para média/mínimo."),
]
GENERICA = ("Situação sem regra cadastrada", "Compare a participação com o mês anterior: mudança brusca de quantidade ou de volume "
            "médio por economia nesta situação explica variações do faturamento que não vêm do consumo.")


def classifica(situacao):
    """(título, por que analisar) para o código/descrição da situação de lançamento."""
    # compara o começo de cada palavra (e de pares de palavras: "NAO REALIZADA" → NAOREALIZADA), para "LEITURA NORMAL"
    # não cair em ANORMalidade
    palavras = re.findall(r"[A-Z0-9]+", chave_texto_espacos(situacao))
    candidatos = palavras + [a + b for a, b in zip(palavras, palavras[1:])]
    for chaves, titulo, porque in REGRAS_SITUACAO:
        if any(p.startswith(c) for c in chaves for p in candidatos):
            return titulo, porque
    return GENERICA


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
    """Uma linha por ligação do mês atual (rubrica de água): a lista que a seta de cada card baixa."""
    at, ant = _por_ligacao(df_at), _por_ligacao(df_ant)
    if not len(at):
        return pd.DataFrame()
    ant = ant.set_index("N. Ligação")
    d = pd.DataFrame({"N. Ligação": at["N. Ligação"]})
    for c, nome in (("Nome Cliente", "Nome Cliente"), ("Grupo", "Grupo"), ("Categoria", "Categoria"), ("__sup", "Superintendência")):
        if c in at.columns:
            d[nome] = at[c].values
    d[f"Situação Lançamento {mes}"] = at["Situação"].values
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


def resumo_situacoes(df_at, df_ant):
    """Uma linha por situação: ligações, economias, volume e valor (água + esgoto) nos dois meses e as variações."""
    at, ant = _por_ligacao(df_at), _por_ligacao(df_ant)
    if not len(at) and not len(ant):
        return pd.DataFrame()

    def soma(d, suf):
        g = d.groupby("Situação").agg(**{f"Ligações {suf}": ("N. Ligação", "size"), f"Economias {suf}": ("Economias", "sum"),
                                         f"Volume {suf}": ("Volume", "sum"), f"Valor {suf}": ("Valor", "sum")})
        return g
    r = soma(at, "atual").join(soma(ant, "anterior"), how="outer").fillna(0)
    for suf in ("atual", "anterior"):
        tot = r[f"Ligações {suf}"].sum()
        r[f"% ligações {suf}"] = r[f"Ligações {suf}"] / tot * 100 if tot else 0.0
        r[f"Vol./economia {suf}"] = (r[f"Volume {suf}"] / r[f"Economias {suf}"].where(r[f"Economias {suf}"] > 0)).fillna(0)
    r["Δ ligações"] = r["Ligações atual"] - r["Ligações anterior"]
    r["Δ p.p. participação"] = r["% ligações atual"] - r["% ligações anterior"]
    r["Δ valor"] = r["Valor atual"] - r["Valor anterior"]
    r = r.sort_values(["Ligações atual", "Ligações anterior"], ascending=False).reset_index()
    r.insert(1, "Leitura da situação", r["Situação"].map(lambda s: classifica(s)[0]))
    r["Por que analisar"] = r["Situação"].map(lambda s: classifica(s)[1])
    return r


def _card(linha, mes, ant, sup="TODAS"):
    # data-f: campos que o filtro de grupos refaz no navegador (sitlRecalcular)
    def var(v, dec=0, suf="", f=""):
        cor = "#C2560C" if v < 0 else "#176b9c" if v > 0 else "#49668C"
        sinal = "+" if v > 0 else ""
        return f'<span data-f="{f}" style="color:{cor};font-weight:600">{sinal}{fmt_num(v, dec)}{suf}</span>'
    return f"""
    <div class="sitl-card" data-sit="{html.escape(str(linha['Situação']), quote=True)}">
      <div class="sitl-topo"><b>{html.escape(str(linha['Situação']))}{_seta(linha, sup)}</b><span>{html.escape(linha['Leitura da situação'])}</span></div>
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


def _seta(linha, sup):
    """Seta que baixa as ligações desta situação (só quando há ligações no mês atual)."""
    if not linha["Ligações atual"]:
        return ""
    e = lambda v: html.escape(str(v), quote=True)
    return (f' <button type="button" class="btn-sitl-dl" data-sit="{e(linha["Situação"])}" data-sup="{e(sup)}" '
            f'title="Baixar as ligações desta situação (CSV)" aria-label="Baixar as ligações de {e(linha["Situação"])}">&#11015;</button>')


def gera_cards_situacao_html(ctx):
    """Um quadro por superintendência (o filtro Superintendência mostra o escolhido), com um card por situação."""
    from .dre import TODAS, _nome_sup, lista_sups
    from .tabelas_html import botao_download_xlsx, xlsx_bytes
    ctx.resultados["situacao_lancamento"] = {}
    if COLUNA not in ctx.df_atual.columns and COLUNA not in ctx.df_anterior.columns:
        return ("<div class='card'><h2>Situação de lançamento</h2><p class='nota-secao'>A fatura de ciclo não tem a coluna "
                "<b>Situacao Lancamento</b>: os cards aparecem quando ela vier no arquivo.</p></div>")
    blocos = []
    for sup in lista_sups(ctx):
        at, an = ctx.df_atual, ctx.df_anterior
        if sup != TODAS:
            at, an = at[at["__sup"] == sup], an[an["__sup"] == sup]
        r = resumo_situacoes(at, an)
        ctx.resultados["situacao_lancamento"][sup] = r
        suf = "" if sup == TODAS else f" — {_nome_sup(sup)}"
        slug = "".join(c for c in sup if c.isalnum())
        botao = botao_download_xlsx(f"Baixar situações{'' if sup == TODAS else ' ' + sup} (Excel)",
                                    f"Situacao_Lancamento_{slug}.xlsx", xlsx_bytes({"Situacao Lancamento": r})) if len(r) else ""
        if botao:                                      # com grupos desmarcados, baixa (CSV) o resumo refeito só com eles
            botao = (f'<span data-csv-filtrado="sitl" data-sup="{html.escape(sup, quote=True)}" '
                     f'data-nome="Situacao_Lancamento_{slug}">{botao}</span>')
        cards = "".join(_card(l, ctx.mes_atual, ctx.mes_anterior, sup) for _, l in r.iterrows()) or "<p>Sem dados</p>"
        blocos.append(f"""<div class="sup-top-bloco" data-sup="{html.escape(sup, quote=True)}">
    <div class="card">
    <h2 style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">Situação de lançamento — {html.escape(ctx.mes_atual)} × {html.escape(ctx.mes_anterior)}{html.escape(suf)} {botao}</h2>
    <p class="nota-secao">{POR_QUE_GERAL}</p>
    <p class="nota-secao">Contagem por ligação (rubrica de água; a situação é a da conta no mês). Volume e economias só onde Consumo Faturado &gt; 0;
    valor = água + esgoto da ligação. Variações contra o mês anterior; p.p. = pontos percentuais na participação das ligações.</p>
    <div class="sitl-grid">{cards}</div>
    </div></div>""")
    # lista por ligação embutida uma vez (comprimida); a seta de cada card filtra a situação e a SUP na hora de baixar
    det = detalhe_ligacoes(ctx.df_atual, ctx.df_anterior, ctx.mes_atual, ctx.mes_anterior)
    ctx.resultados["situacao_detalhe"] = det
    dados = (f'<script type="application/octet-stream" id="sitl-detalhe" data-col-sit="Situação Lançamento {html.escape(ctx.mes_atual, quote=True)}" '
             f'data-arquivo="Situacao_Lancamento_{ctx.mes_atual.replace("/", "-")}">{_csv_gz_b64(det)}</script>') if len(det) else ""
    # totais por SUP × grupo × situação (mês atual e anterior): o filtro de grupos refaz os cards com eles
    agregados = {"at": _agrega_grupo(ctx.df_atual), "ant": _agrega_grupo(ctx.df_anterior),
                 "porque": {str(sit): list(classifica(sit)) for r in ctx.resultados["situacao_lancamento"].values() for sit in r.get("Situação", [])}}
    dados += ('<script type="application/json" id="sitl-agregados">'
              + json.dumps(agregados, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    return "".join(blocos) + dados
