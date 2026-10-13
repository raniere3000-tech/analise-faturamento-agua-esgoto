# -*- coding: utf-8 -*-
"""Estrutura tarifária: faixas por categoria e mínimo por economia.

Padrão em regras.json ("estrutura_tarifaria"); uma planilha na pasta substitui o padrão — arquivo com "tarif" no nome
ou com a aba tblTarifas (colunas Categoria, Limite Inicial, Limite Final, Tarifa Normal, Tarifa Progressiva) e, se
houver, a aba tblMinimo (Categoria, Limite por economia). O cálculo do valor fica em assets/tarifa.js (relatório e
site); valor_pela_media() abaixo é a mesma regra em Python (testes e conferência).
"""
import copy
import os

import pandas as pd

from .config import CONSUMO_MINIMO_POR_CATEGORIA, MINIMO_POR_TIPO_ECONOMIA, REGRAS, chave_texto
from .formatacao import normaliza_texto

PADRAO = REGRAS.get("estrutura_tarifaria", {"faixas": [], "minimos": {}})
_MINIMOS_ORIGINAIS = dict(CONSUMO_MINIMO_POR_CATEGORIA)
_POR_TIPO_ORIGINAIS = dict(MINIMO_POR_TIPO_ECONOMIA)


def _linha_cabecalho(df, exigidas):
    for i in range(min(len(df), 30)):
        chaves = {chave_texto(v) for v in df.iloc[i].tolist() if isinstance(v, str)}
        if exigidas <= chaves:
            return i
    return None


def _tabela(livro, aba, exigidas):
    bruto = livro.parse(aba, header=None)
    i = _linha_cabecalho(bruto, exigidas)
    if i is None:
        return None
    df = bruto.iloc[i + 1:].copy()
    df.columns = [chave_texto(v) for v in bruto.iloc[i].tolist()]
    return df


def abas_de_tarifa(nomes_abas, nome_arquivo=""):
    """Aba da estrutura tarifária num livro (tblTarifas / Estrutura Tarifária / Tarifas…) ou None."""
    for a in nomes_abas:
        if chave_texto(a) in ("TBLTARIFAS", "ESTRUTURATARIFARIA", "TARIFA", "TARIFAS"):
            return a
    if "TARIF" in chave_texto(os.path.basename(nome_arquivo)) and nomes_abas:
        return nomes_abas[0]
    return None


def processa_tarifa(caminho, aba):
    """{faixas, minimos} lidos da planilha (vazio se a aba não tiver as colunas esperadas)."""
    livro = pd.ExcelFile(caminho)
    exig = {"CATEGORIA", "LIMITEINICIAL", "LIMITEFINAL", "TARIFANORMAL"}
    df = _tabela(livro, aba, exig)
    if df is None:                              # aba indicada sem a tabela: procura nas outras
        for a in livro.sheet_names:
            df = _tabela(livro, a, exig)
            if df is not None:
                break
    faixas = []
    if df is not None:
        prog = "TARIFAPROGRESSIVA" if "TARIFAPROGRESSIVA" in df.columns else "TARIFANORMAL"
        for _, r in df.iterrows():
            cat = r.get("CATEGORIA")
            if not isinstance(cat, str) or not cat.strip():
                continue
            nums = [pd.to_numeric(r.get(c), errors="coerce") for c in ("LIMITEINICIAL", "LIMITEFINAL", "TARIFANORMAL", prog)]
            if any(pd.isna(x) for x in nums):
                continue
            faixas.append([cat.strip().upper(), *(float(x) for x in nums)])
    minimos = {}
    for a in livro.sheet_names:
        m = _tabela(livro, a, {"CATEGORIA", "LIMITEPORECONOMIA"})
        if m is not None:
            for _, r in m.iterrows():
                v = pd.to_numeric(r.get("LIMITEPORECONOMIA"), errors="coerce")
                if isinstance(r.get("CATEGORIA"), str) and not pd.isna(v):
                    minimos[r["CATEGORIA"].strip().upper()] = float(v)
            break
    return {"faixas": faixas, "minimos": minimos}


_aplicada = {"sim": False}


def define_tarifa(ctx, lida=None, arquivo=""):
    """Tarifa da análise: a da planilha da pasta (quando tem faixas) ou a padrão. Com planilha, os mínimos dela valem
    para todo o painel (consumo mínimo, acima × abaixo do mínimo, etapa 2); sem planilha, vale o consumo mínimo do
    regras.json (e a tarifa usa esses mesmos mínimos)."""
    t = copy.deepcopy(PADRAO)
    t.pop("_comentario", None)
    t["fonte"] = "padrão (regras.json)"
    if _aplicada["sim"]:                     # análise anterior usou mínimos de uma planilha: volta ao regras.json
        CONSUMO_MINIMO_POR_CATEGORIA.clear(); CONSUMO_MINIMO_POR_CATEGORIA.update(_MINIMOS_ORIGINAIS)
        MINIMO_POR_TIPO_ECONOMIA.clear(); MINIMO_POR_TIPO_ECONOMIA.update(_POR_TIPO_ORIGINAIS)
        _aplicada["sim"] = False
    if lida and lida.get("faixas"):
        t["faixas"] = lida["faixas"]
        t["fonte"] = arquivo or "planilha da pasta"
        if lida.get("minimos"):
            for cat, v in lida["minimos"].items():
                CONSUMO_MINIMO_POR_CATEGORIA[cat] = v
            if "PUBLICA" in lida["minimos"]:  # PUB. ESTADUAL segue a PÚBLICA, como na planilha
                CONSUMO_MINIMO_POR_CATEGORIA["PUB. ESTADUAL"] = lida["minimos"]["PUBLICA"]
            for coluna, categoria in REGRAS["categoria_por_tipo_de_economia"].items():
                if categoria in CONSUMO_MINIMO_POR_CATEGORIA:
                    MINIMO_POR_TIPO_ECONOMIA[coluna] = CONSUMO_MINIMO_POR_CATEGORIA[categoria]
            _aplicada["sim"] = True
    t["minimos"] = dict(CONSUMO_MINIMO_POR_CATEGORIA)      # a tarifa usa os mesmos mínimos do painel
    ctx.tarifa = t
    return t


# ---------- mesma regra do assets/tarifa.js ----------
def _n(s):
    return normaliza_texto(s)


def _minimo_de(tab, cat):
    c = "PUBLICA" if _n(cat) == "PUB. ESTADUAL" else _n(cat)
    for k, v in tab["minimos"].items():
        if _n(k) == c:
            return float(v)
    return 0.0


def _rotulos(categoria):
    c = _n(categoria)
    return {"res": c if c in ("RESIDENCIAL", "SOCIAL") else "RESIDENCIAL",
            "com": c if c in ("COMERCIAL", "PEQ. COMERCIO") else "COMERCIAL",
            "ind": "INDUSTRIAL",
            "pub": c if c in ("PUBLICA", "PUB. ESTADUAL") else "PUBLICA"}


def _valor_categoria(tab, cat, qty, total):
    if not qty or not total:
        return 0.0
    progressivo = total > _minimo_de(tab, cat) * qty
    soma = 0.0
    for c, ini, fim, normal, prog in tab["faixas"]:
        if _n(c) != _n(cat):
            continue
        lim_inf, lim_sup = max(ini - 1, 0) * qty, fim * qty
        vol = max((total if total < lim_sup else lim_sup) - lim_inf, 0)
        soma += vol * (prog if progressivo else normal)
    return soma


def minimo_ligacao(tab, categoria, eco):
    r = _rotulos(categoria)
    return sum(_minimo_de(tab, r[k]) * eco.get(k, 0) for k in ("res", "com", "ind", "pub") if eco.get(k, 0) > 0)


def valor_pela_media(tab, media, categoria, eco, esgoto=False):
    """Valor (R$) de `media` m³ para a ligação (categoria, economias {res, com, ind, pub}, com/sem esgoto)."""
    r = _rotulos(categoria)
    q = {k: float(eco.get(k, 0) or 0) for k in ("res", "com", "ind", "pub")}
    total_eco = sum(q.values())
    mins = {k: _minimo_de(tab, r[k]) * q[k] for k in q}
    soma = sum(mins[k] for k in q if q[k] > 0)
    extra = ((media - soma) if media > soma else 0) / total_eco if total_eco else 0
    v = sum(_valor_categoria(tab, r[k], q[k], (mins[k] + extra * q[k]) if q[k] else 0) for k in q)
    return v * (2 if esgoto else 1)
