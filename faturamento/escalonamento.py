# -*- coding: utf-8 -*-
"""Validação do escalonamento do esgoto (botão ao lado do Comparativo Esgoto Mês a Mês).

Para todas as matrículas que faturam esgoto em algum mês da pasta: o faturado de água, o de esgoto e quanto o esgoto
representa da água (%), mês a mês. Serve para conferir o escalonamento das ligações inseridas recentemente no esgoto
(a % sobe em degraus até chegar a 100%).

A % sai arredondada para o inteiro (24,99% / 25,01% → 25%), para a tabela dinâmica juntar os mesmos degraus.
Duas abas: "Por mês" (uma linha por matrícula e mês — a melhor para a tabela dinâmica) e "Lado a lado" (uma linha por
matrícula, com água, esgoto e % de cada mês). Segue a Superintendência e os grupos do cabeçalho; vale para todos os meses
da pasta (todos os grupos, sem o corte do último grupo faturado).
"""
import io
import types

import pandas as pd

from .analitico import _por_mes
from .formatacao import nome_mes

LIMITE_XLSX = 1_000_000          # linhas da aba "Por mês" (o Excel aceita até 1.048.576); acima disso sai CSV


def _chave_ref(r):
    return (str(r)[3:], str(r)[:2])


def pct_esgoto(agua, esgoto):
    """% do esgoto em relação à água, arredondada para o inteiro; sem água no mês = vazio."""
    if agua is None or pd.isna(agua) or abs(agua) < 0.005:
        return None
    return int(round(esgoto / agua * 100))


def dados_escalonamento(ctx, sup=None, grupos=None):
    """DataFrame longo (matrícula × mês) só com as matrículas que faturaram esgoto em algum mês (com os filtros)."""
    from .leitura import chave_grupo
    base = getattr(ctx, "base_completa", None)
    if base is None:
        base = ctx.base_final
    ctx_base = types.SimpleNamespace(base_final=base)
    alvo = {chave_grupo(g) for g in grupos} if grupos else None
    partes = []
    for ref in sorted(base["Referencia de Leitura"].dropna().unique(), key=_chave_ref):
        d = _por_mes(ctx_base, ref)
        if not len(d):
            continue
        if sup and sup != "TODAS" and "__sup" in d.columns:
            d = d[d["__sup"] == sup]
        if alvo is not None and "Grupo" in d.columns:
            d = d[d["Grupo"].map(chave_grupo).isin(alvo)]
        if not len(d):
            continue
        col = lambda c: d[c] if c in d.columns else pd.Series(None, index=d.index, dtype=object)
        num = lambda c: pd.to_numeric(col(c), errors="coerce").fillna(0.0)
        partes.append(pd.DataFrame({
            "ref": ref, "Matrícula": d.index.astype(str), "Cliente": col("Nome Cliente").values,
            "Categoria": col("Categoria").values, "Localidade": col("Nome da Localidade").values,
            "Grupo": col("Grupo").values, "SUP": col("__sup").values,
            "Economias": pd.to_numeric(col("Economias_Totais"), errors="coerce").values,
            "Água (R$)": num("valor_agua").round(2).values, "Esgoto (R$)": num("valor_esgoto").round(2).values,
        }))
    if not partes:
        return pd.DataFrame()
    df = pd.concat(partes, ignore_index=True)
    com_esgoto = set(df.loc[df["Esgoto (R$)"] != 0, "Matrícula"])
    df = df[df["Matrícula"].isin(com_esgoto)].copy()
    if not len(df):
        return df
    df["% esgoto/água"] = pd.array([pct_esgoto(a, e) for a, e in zip(df["Água (R$)"], df["Esgoto (R$)"])], dtype="Int64")
    primeiro = df[df["Esgoto (R$)"] != 0].sort_values("ref", key=lambda s: s.map(_chave_ref)).drop_duplicates("Matrícula")
    df["1º mês com esgoto"] = df["Matrícula"].map(dict(zip(primeiro["Matrícula"], primeiro["ref"].map(nome_mes))))
    df["Mês"] = df["ref"].map(nome_mes)
    return df


def gera_escalonamento(ctx, sup=None, grupos=None):
    """Arquivo da validação do escalonamento: {nome, conteudo (bytes), matriculas, linhas, meses}."""
    df = dados_escalonamento(ctx, sup, grupos)
    rot = (sup or "TODAS").replace(" ", "_")
    if not len(df):
        return {"nome": "", "conteudo": b"", "matriculas": 0, "linhas": 0, "meses": []}
    refs = sorted(df["ref"].unique(), key=_chave_ref)
    cad = ["Matrícula", "Cliente", "Categoria", "Localidade", "Grupo", "SUP", "Economias", "1º mês com esgoto"]
    # cadastro do mês mais recente de cada matrícula
    df = df.assign(__o=df["ref"].map(_chave_ref)).sort_values(["Matrícula", "__o"])
    ult = df.drop_duplicates("Matrícula", keep="last").set_index("Matrícula")
    longo = df[["Mês"] + cad + ["Água (R$)", "Esgoto (R$)", "% esgoto/água"]].reset_index(drop=True)
    largo = ult[cad[1:]].copy()
    for r in refs:
        m = df[df["ref"] == r].set_index("Matrícula")
        n = nome_mes(r)
        largo[f"Água {n} (R$)"] = m["Água (R$)"]
        largo[f"Esgoto {n} (R$)"] = m["Esgoto (R$)"]
        largo[f"% esgoto/água {n}"] = m["% esgoto/água"]
    largo = largo.reset_index().sort_values(["Grupo", "Matrícula"], key=lambda s: s.astype(str)).reset_index(drop=True)
    periodo = "_a_".join(dict.fromkeys([refs[0], refs[-1]])).replace("/", "-")
    nome = f"Validacao_escalonamento_esgoto_{rot}_{periodo}"
    from .tabelas_html import motor_excel
    motor = motor_excel()
    if motor and len(longo) <= LIMITE_XLSX:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine=motor) as w:
            longo.to_excel(w, sheet_name="Por mês", index=False)
            largo.to_excel(w, sheet_name="Lado a lado", index=False)
        conteudo, nome = buf.getvalue(), nome + ".xlsx"
    else:
        conteudo, nome = longo.to_csv(sep=";", index=False, decimal=",").encode("utf-8-sig"), nome + ".csv"
    return {"nome": nome, "conteudo": conteudo, "matriculas": int(longo["Matrícula"].nunique()), "linhas": int(len(longo)),
            "meses": [nome_mes(r) for r in refs]}
