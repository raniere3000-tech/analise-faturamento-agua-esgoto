# -*- coding: utf-8 -*-
"""Analítico por matrícula da aba Análise: uma linha por ligação, com o mês anterior e o atual lado a lado.

É a base que explica as tabelas resumidas (ativas × cortadas, matriz de migração, acima × abaixo do mínimo,
situação de lançamento e Top 100). Vai embutida uma vez no relatório (CSV comprimido) e a seta "detalhe" de cada
tabela baixa as colunas e as linhas daquela tabela, já com os filtros de Superintendência e Grupo (relatorio.js).
"""
import html

import numpy as np
import pandas as pd

from .analises import classifica_minimo
from .situacao_lancamento import SEM_SITUACAO, grupo_da_situacao


def _norm_situacao(s):
    """Mesma regra da tabela ativas × cortadas: 'ATIV…' = Ativa, 'CORT…' = Cortada; o resto fica fora."""
    t = str(s).upper()
    return "Ativa" if "ATIV" in t else "Cortada" if "CORT" in t else ""


def _por_mes(ctx, ref):
    """Uma linha por ligação no mês: dados da linha de água e totais de água e esgoto."""
    b = ctx.base_final
    b = b[b["Referencia de Leitura"] == ref]
    serv = b["__serv"] if "__serv" in b.columns else b["Rubrica"].astype(str).str.upper().map(
        lambda r: "E" if "ESGOTO" in r else "A" if "AGUA" in r else "")
    lig = b["N. Ligação"].astype(str).str.strip()
    consumo = pd.to_numeric(b["Consumo Faturado"], errors="coerce").fillna(0)
    valor = pd.to_numeric(b["Valor (R$)"], errors="coerce").fillna(0)
    a = serv == "A"
    agua = b[a]
    if not len(agua) and not (serv == "E").any():
        return pd.DataFrame()
    # dados descritivos da linha de água (a primeira, se houver mais de uma)
    cols = [c for c in ("Grupo", "Nome Cliente", "Categoria", "Situacao Ligacao", "Situacao Lancamento", "__sup",
                        "Economias_Totais") if c in agua.columns]
    desc = agua[cols].assign(__lig=lig[a].values).drop_duplicates("__lig").set_index("__lig")
    mn = classifica_minimo(agua.assign(**{"Consumo Faturado": consumo[a]}))
    mn = mn.assign(__lig=lig[a].values).drop_duplicates("__lig").set_index("__lig")
    out = desc.copy()
    if "Situacao Lancamento" in out.columns:                 # mesma leitura dos cards: vazio = "Sem situação"
        sit = out["Situacao Lancamento"].astype(object).where(out["Situacao Lancamento"].notna(), SEM_SITUACAO)
        out["Situacao Lancamento"] = sit.astype(str).str.strip().replace("", SEM_SITUACAO)
    out["linhas_agua"] = lig[a].value_counts()
    out["consumo_agua"] = consumo[a].groupby(lig[a].values).sum()
    out["valor_agua"] = valor[a].groupby(lig[a].values).sum()
    e = serv == "E"
    # economias faturadas = mesma regra do Comparativo das Diretas: economias das linhas com Consumo Faturado > 0
    eco = pd.to_numeric(b["Economias_Totais"], errors="coerce").fillna(0) if "Economias_Totais" in b.columns else consumo * 0
    out["eco_fat_agua"] = eco[a].where(consumo[a] > 0, 0).groupby(lig[a].values).sum()
    esg = pd.DataFrame({"consumo_esgoto": consumo[e].groupby(lig[e].values).sum(), "valor_esgoto": valor[e].groupby(lig[e].values).sum(),
                        "eco_fat_esgoto": eco[e].where(consumo[e] > 0, 0).groupby(lig[e].values).sum()})
    out = out.join(esg, how="outer")
    out["minimo"] = mn["minimo"]
    out["conta"] = mn["conta"]
    out["classe_minimo"] = mn["classe"]
    return out


def monta_analitico(ctx):
    """DataFrame (uma linha por ligação dos dois meses comparados) com as colunas do analítico."""
    ra, rn = ctx.ref_atual, ctx.ref_anterior
    at, an = _por_mes(ctx, ra), _por_mes(ctx, rn)
    if not len(at) and not len(an):
        return pd.DataFrame()
    ligs = at.index.union(an.index)
    at, an = at.reindex(ligs), an.reindex(ligs)
    pega = lambda c: (at[c] if c in at.columns else pd.Series(np.nan, index=ligs)).combine_first(
        an[c] if c in an.columns else pd.Series(np.nan, index=ligs))
    d = pd.DataFrame(index=ligs)
    d.index.name = "N. Ligação"
    d["Nome Cliente"] = pega("Nome Cliente")
    d["Categoria"] = pega("Categoria")
    d["Superintendência"] = pega("__sup")
    g_at = at["Grupo"].astype(object).where(at["Grupo"].notna()) if "Grupo" in at.columns else pd.Series(np.nan, index=ligs)
    g_an = an["Grupo"].astype(object).where(an["Grupo"].notna()) if "Grupo" in an.columns else pd.Series(np.nan, index=ligs)
    d["Grupo"] = g_at.combine_first(g_an)                                   # para o filtro de grupos do relatório
    d[f"Grupo {rn}"], d[f"Grupo {ra}"] = g_an, g_at
    # migração (mesma regra da matriz: só água com Consumo Faturado > 0 em cada mês)
    fat_at = at["consumo_agua"].fillna(0) > 0 if "consumo_agua" in at.columns else pd.Series(False, index=ligs)
    fat_an = an["consumo_agua"].fillna(0) > 0 if "consumo_agua" in an.columns else pd.Series(False, index=ligs)
    d["Migração de grupo"] = np.select(
        [fat_an & fat_at & (g_an.astype(str) == g_at.astype(str)), fat_an & fat_at, fat_an & ~fat_at, ~fat_an & fat_at],
        ["Permaneceu no grupo", "Mudou de grupo", "Sem faturamento atual", "Sem faturamento anterior"], default="Sem consumo nos dois meses")
    for ref, x in ((rn, an), (ra, at)):
        sit = x["Situacao Ligacao"] if "Situacao Ligacao" in x.columns else pd.Series(np.nan, index=ligs)
        d[f"Situação Ligação {ref}"] = sit
        classe = sit.map(lambda s: _norm_situacao(s) if pd.notna(s) else "")
        consumo_pos = x["consumo_agua"].fillna(0) > 0 if "consumo_agua" in x.columns else pd.Series(False, index=ligs)
        d[f"Ativa/Cortada {ref}"] = classe.where(consumo_pos & (classe != ""), "")      # o que a tabela ativas × cortadas conta
    for ref, x in ((rn, an), (ra, at)):
        d[f"Situação Lançamento {ref}"] = x["Situacao Lancamento"] if "Situacao Lancamento" in x.columns else np.nan
    for ref in (rn, ra):
        sl = d[f"Situação Lançamento {ref}"]
        d[f"Leitura da situação {ref}"] = sl.map(lambda c: grupo_da_situacao(c) if pd.notna(c) else np.nan)
    for ref, x in ((rn, an), (ra, at)):
        d[f"Economias {ref}"] = x["Economias_Totais"] if "Economias_Totais" in x.columns else np.nan
    for ref, x in ((rn, an), (ra, at)):
        d[f"Consumo água {ref}"] = x.get("consumo_agua")
    d["Δ consumo água"] = d[f"Consumo água {ra}"] - d[f"Consumo água {rn}"]
    d["Δ % consumo água"] = (d["Δ consumo água"] / d[f"Consumo água {rn}"].where(d[f"Consumo água {rn}"] > 0)) * 100
    for ref, x in ((rn, an), (ra, at)):
        d[f"Consumo esgoto {ref}"] = x.get("consumo_esgoto")
    for serv, col in (("água", "eco_fat_agua"), ("esgoto", "eco_fat_esgoto")):
        for ref, x in ((rn, an), (ra, at)):
            d[f"Economias faturadas {serv} {ref}"] = x.get(col)
    for ref, x in ((rn, an), (ra, at)):
        d[f"Valor água {ref}"] = x.get("valor_agua")
        d[f"Valor esgoto {ref}"] = x.get("valor_esgoto")
    for ref in (rn, ra):
        d[f"Valor total {ref}"] = d[[f"Valor água {ref}", f"Valor esgoto {ref}"]].sum(axis=1, min_count=1)
    d["Δ valor total"] = d[f"Valor total {ra}"] - d[f"Valor total {rn}"]
    for ref, x in ((rn, an), (ra, at)):
        d[f"Mínimo da matrícula {ref}"] = x.get("minimo")
    d[f"Conta do mínimo {ra}"] = at.get("conta")
    for ref, x in ((rn, an), (ra, at)):
        d[f"Acima/Abaixo do mínimo {ref}"] = x.get("classe_minimo")
    num = d.select_dtypes("number").columns
    d[num] = d[num].round(2)
    return d.reset_index().sort_values(["Grupo", "N. Ligação"], key=lambda s: s.astype(str)).reset_index(drop=True)


def gera_analitico_html(ctx):
    """<script> com o analítico (CSV em gzip/base64) que as setas "detalhe" da aba Análise usam."""
    from .situacao_lancamento import _csv_gz_b64
    d = monta_analitico(ctx)
    ctx.resultados["analitico"] = d
    if not len(d):
        return ""
    e = lambda v: html.escape(str(v), quote=True)
    return (f'<script type="application/octet-stream" id="analitico-dados" data-gz="1" data-ref-atual="{e(ctx.ref_atual)}" '
            f'data-ref-anterior="{e(ctx.ref_anterior)}" data-mes="{e(ctx.mes_atual.replace("/", "-"))}">{_csv_gz_b64(d)}</script>')


def seta_detalhe(tipo, sup="TODAS", rotulo="Baixar o analítico por matrícula desta tabela (CSV)"):
    """Seta "detalhe" ao lado do título de uma tabela da aba Análise."""
    e = lambda v: html.escape(str(v), quote=True)
    return (f'<button type="button" class="btn-just btn-detalhe" data-detalhe="{e(tipo)}" data-sup="{e(sup)}" '
            f'title="{e(rotulo)}" aria-label="{e(rotulo)}">&#11015;&#8801;</button>')
