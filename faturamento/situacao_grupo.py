# -*- coding: utf-8 -*-
"""Situação de cada grupo de leitura no mês vigente (coluna "Situação" das tabelas da aba Diretas).

  - LIS: o grupo que está sendo lido hoje (Data da Leitura do cronograma = hoje).
  - Aguardando: grupos com leitura depois de hoje (ainda não lidos) ou ainda sem nenhuma linha no mês.
  - Em Análise: ao menos uma matrícula com Situacao Conta = EM ANALISE (fatura de ciclo e/ou consumo do mês).
  - Liberado: nenhuma matrícula em análise (todas LIBERADA).
"Hoje" é o dia seguinte à data de corte (D-1), a mesma referência do forecast.
"""
import datetime as dt

import pandas as pd

from .config import SITUACAO_CONTA_EM_ANALISE
from .formatacao import normaliza_texto

LIS, AGUARDANDO, EM_ANALISE, LIBERADO = "LIS", "Aguardando", "Em Análise", "Liberado"
LIBERADA = "LIBERADA"


def resumo_situacao_conta(df, col_grupo, col_ref, col_sit="Situacao Conta"):
    """Por grupo × mês: quantas linhas, se alguma está EM ANALISE e se todas estão LIBERADA."""
    if df is None or not len(df) or col_sit not in df.columns or col_grupo not in df.columns or col_ref not in df.columns:
        return pd.DataFrame(columns=["g", "ref", "n", "em_analise", "liberada"])
    from .leitura import chave_grupo
    sit = df[col_sit]
    unicos = sit.dropna().unique()
    norm = sit.map(dict(zip(unicos, (normaliza_texto(v) for v in unicos))))
    d = pd.DataFrame({"g": df[col_grupo].map({g: chave_grupo(g) for g in df[col_grupo].dropna().unique()}).values,
                      "ref": df[col_ref].astype(str).values,
                      "an": (norm == SITUACAO_CONTA_EM_ANALISE).values,
                      "lib": (norm == LIBERADA).values,
                      "tem": norm.notna().values & (norm != "").values})
    d = d[d["tem"] & d["g"].notna()]
    if not len(d):
        return pd.DataFrame(columns=["g", "ref", "n", "em_analise", "liberada"])
    r = d.groupby(["g", "ref"]).agg(n=("tem", "size"), em_analise=("an", "any"), liberada=("lib", "all")).reset_index()
    return r


def _datas_de_leitura(ctx, ref):
    """{grupo: data da leitura no mês `ref`} pelo cronograma."""
    crono = getattr(ctx, "cronograma_leitura", None)
    if crono is None or not len(crono) or "Referencia Cronograma" not in crono.columns:
        return {}
    c = crono[crono["Referencia Cronograma"] == ref]
    datas = pd.to_datetime(c["Data da Leitura"].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce")
    faltam = datas.isna()
    if faltam.any():
        datas[faltam] = pd.to_datetime(c.loc[faltam, "Data da Leitura"], errors="coerce", dayfirst=True)
    out = {}
    for g, d in zip(c["Grupo"], datas):
        if pd.notna(d):
            out[str(g)] = min(out.get(str(g), d.date()), d.date())
    return out


def situacao_dos_grupos(ctx):
    """{chave do grupo: situação} para o mês vigente (ref_atual). Guarda em ctx.situacao_grupo."""
    if getattr(ctx, "situacao_grupo", None) is not None:
        return ctx.situacao_grupo
    from .leitura import chave_grupo
    from .previsao import data_corte
    hoje = data_corte(ctx) + dt.timedelta(days=1)
    ref = ctx.ref_atual
    datas = _datas_de_leitura(ctx, ref)
    resumo = getattr(ctx, "situacao_conta_resumo", None)
    conta = {}
    if resumo is not None and len(resumo):
        r = resumo[resumo["ref"] == ref]
        for g, n, an, lib in zip(r["g"], r["n"], r["em_analise"], r["liberada"]):
            a = conta.setdefault(g, {"n": 0, "an": False, "lib": True})
            a["n"] += int(n); a["an"] = a["an"] or bool(an); a["lib"] = a["lib"] and bool(lib)
    grupos = set(datas) | set(conta)
    fat = getattr(ctx, "fatura_total", None)
    if fat is not None and "Grupo" in fat.columns:
        grupos |= {chave_grupo(g) for g in fat["Grupo"].dropna().unique()}
    sit = {}
    for g in grupos:
        d, c = datas.get(g), conta.get(g)
        if d is not None and d == hoje:
            sit[g] = LIS
        elif d is not None and d > hoje:
            sit[g] = AGUARDANDO
        elif not c or not c["n"]:
            sit[g] = AGUARDANDO
        else:
            sit[g] = EM_ANALISE if c["an"] else LIBERADO
    ctx.situacao_grupo = sit
    return sit


def situacao(ctx, grupo):
    from .leitura import chave_grupo
    return situacao_dos_grupos(ctx).get(chave_grupo(grupo), "")
