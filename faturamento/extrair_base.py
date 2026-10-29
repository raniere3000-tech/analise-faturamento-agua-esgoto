# -*- coding: utf-8 -*-
"""Extração de bases (aba Dados › Bases analíticas › "Por matrículas e meses", no site) — como a aba Base do painel da
arrecadação: só as matrículas informadas (coladas ou de um arquivo) ou todas, nos meses marcados.

Dois formatos, a partir da base já lida (todos os grupos, sem o corte do último grupo faturado):
  - "matricula": uma linha por matrícula e mês, com dados da matrícula, consumos e faturamento água/esgoto/total
    (mesmas colunas da base completa por matrícula do botão do site);
  - "linhas": as linhas da base como estão (uma por rubrica), com todas as colunas.
Até LIMITE_XLSX linhas sai Excel (uma aba por mês); acima, CSV (separador ";", abre no Excel), que é bem mais leve.
"""
import io
import re
import types

import pandas as pd

from .analitico import _por_mes
from .formatacao import nome_mes, normaliza_texto

LIMITE_XLSX = 150_000


def chave_lig(v):
    """Matrícula comparável: só os dígitos, sem zeros à esquerda ("0100398", "100398.0" e "100.398" viram "100398")."""
    t = str(v if v is not None else "").strip()
    t = re.sub(r"\.0+$", "", t)
    t = re.sub(r"\D", "", t).lstrip("0")
    return t


def ligacoes_do_texto(texto):
    """Matrículas de um texto colado (uma por linha, ou separadas por espaço, vírgula, ponto e vírgula ou tab)."""
    vistos, lista = set(), []
    for tok in re.split(r"[\s,;|]+", str(texto or "")):
        k = chave_lig(tok)
        if k and k not in vistos:
            vistos.add(k)
            lista.append(k)
    return lista


def ligacoes_do_arquivo(nome, conteudo):
    """Matrículas de um arquivo: Excel (coluna Matrícula/Ligação, ou a 1ª coluna) ou CSV/TXT."""
    if re.search(r"\.xlsx?$", nome or "", re.I):
        bruto = pd.read_excel(io.BytesIO(conteudo), header=None, dtype=str)
        if not len(bruto):
            return []
        cab = [normaliza_texto(str(c)) for c in bruto.iloc[0].fillna("")]
        col = next((i for i, c in enumerate(cab) if re.search(r"MATRICULA|LIGACAO", c)), None)
        valores = bruto.iloc[1:, col] if col is not None else bruto.iloc[:, 0]
        return ligacoes_do_texto("\n".join(valores.dropna().astype(str)))
    texto = conteudo.decode("utf-8-sig", errors="ignore")
    linhas = texto.splitlines()
    if linhas and re.search(r"MATRICULA|LIGACAO", normaliza_texto(linhas[0])):
        sep = ";" if ";" in linhas[0] else "," if "," in linhas[0] else "\t"
        cab = [normaliza_texto(c) for c in linhas[0].split(sep)]
        col = next(i for i, c in enumerate(cab) if re.search(r"MATRICULA|LIGACAO", c))
        texto = "\n".join(l.split(sep)[col] if len(l.split(sep)) > col else "" for l in linhas[1:])
    return ligacoes_do_texto(texto)


def _situacao_limpa(s):
    """"A - Ativa" -> "ATIVA" (sem o código antes do hífen, maiúsculas e sem acento) — como na base completa do site."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    t = str(s)
    if "-" in t:
        t = t.split("-", 1)[1]
    return normaliza_texto(t).strip()


def _por_matricula(ctx_base, ref, ligs):
    d = _por_mes(ctx_base, ref)
    if not len(d):
        return pd.DataFrame()
    if ligs is not None:
        chave = pd.Series(d.index.astype(str), index=d.index).map(chave_lig)
        d = d[chave.isin(ligs).values]
    if not len(d):
        return pd.DataFrame()
    g = lambda c: d[c] if c in d.columns else pd.Series(None, index=d.index, dtype=object)
    num = lambda c: pd.to_numeric(g(c), errors="coerce").fillna(0.0)
    fat_esg = (num("valor_esgoto") != 0) | (num("eco_fat_esgoto") > 0)
    cons_esg = num("consumo_esgoto").where(~(fat_esg & (num("consumo_esgoto") == 0)), num("consumo_agua"))
    out = pd.DataFrame({
        "Mês": nome_mes(ref), "Matrícula": d.index.astype(str), "Cliente": g("Nome Cliente").values,
        "Categoria": g("Categoria").values, "Superintendência": g("__sup").values, "Localidade": g("Nome da Localidade").values,
        "Zona": g("Zona").values, "Grupo": g("Grupo").values,
        "Situação ligação": g("Situacao Ligacao").map(_situacao_limpa).values,
        "Situação lançamento": g("Situacao Lancamento").values,
        "Economias": pd.to_numeric(g("Economias_Totais"), errors="coerce").values,
        "Tipo de faturamento": ["AGUA E ESGOTO" if x else "AGUA" for x in fat_esg],
        "Consumo medido água (m³)": num("medido_agua").values, "Consumo faturado água (m³)": num("consumo_agua").values,
        "Consumo faturado esgoto (m³)": cons_esg.where(fat_esg, 0.0).values,
        "Economias faturadas água": num("eco_fat_agua").values, "Economias faturadas esgoto": num("eco_fat_esgoto").values,
        "Faturamento água (R$)": num("valor_agua").round(2).values, "Faturamento esgoto (R$)": num("valor_esgoto").round(2).values,
    })
    out["Faturamento total (R$)"] = (out["Faturamento água (R$)"] + out["Faturamento esgoto (R$)"]).round(2)
    return out.sort_values(["Grupo", "Matrícula"], key=lambda s: s.astype(str)).reset_index(drop=True)


def _linhas(base, ref, ligs):
    b = base[base["Referencia de Leitura"] == ref]
    if ligs is not None:
        lig = b["N. Ligação"].astype(str)
        b = b[lig.map({v: chave_lig(v) for v in lig.unique()}).isin(ligs)]
    return b[[c for c in b.columns if not str(c).startswith("__")]].reset_index(drop=True)


def extrai_base(ctx, ligs, meses, formato="matricula"):
    """ligs: lista de matrículas (None = todas); meses: ["MM/AAAA"]. Devolve dict com os bytes do arquivo e o resumo."""
    base = getattr(ctx, "base_completa", None)
    if base is None:
        base = ctx.base_final
    alvo = set(ligs) if ligs is not None else None
    ctx_base = types.SimpleNamespace(base_final=base)            # todos os grupos (sem o corte do último grupo faturado)
    partes, por_mes, achadas = {}, {}, set()
    for ref in sorted(meses, key=lambda r: (r[3:], r[:2])):
        df = _por_matricula(ctx_base, ref, alvo) if formato == "matricula" else _linhas(base, ref, alvo)
        por_mes[ref] = int(len(df))
        if len(df):
            partes[ref] = df
            if alvo is not None:
                col = "Matrícula" if formato == "matricula" else "N. Ligação"
                achadas |= {chave_lig(v) for v in df[col].astype(str).unique()}
    total = sum(por_mes.values())
    nao = [l for l in ligs if l not in achadas] if ligs is not None else []
    rot = "completa" if ligs is None else "matriculas"
    tipo = "por_matricula" if formato == "matricula" else "linhas"
    ordem = sorted(partes, key=lambda r: (r[3:], r[:2]))
    periodo = ("_a_".join(dict.fromkeys([ordem[0], ordem[-1]])).replace("/", "-")) if ordem else "vazia"
    nome = f"Base_{rot}_{tipo}_{periodo}"
    from .tabelas_html import motor_excel
    if total and total <= LIMITE_XLSX and motor_excel():
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine=motor_excel()) as w:
            for ref, df in partes.items():
                df.to_excel(w, sheet_name=nome_mes(ref).replace("/", "-")[:31], index=False)
        conteudo, nome = buf.getvalue(), nome + ".xlsx"
    else:
        tudo = pd.concat(list(partes.values()), ignore_index=True) if partes else pd.DataFrame()
        if formato == "linhas" and len(tudo):
            tudo.insert(0, "Mês", tudo["Referencia de Leitura"].map(nome_mes))
        conteudo = tudo.to_csv(sep=";", index=False, decimal=",").encode("utf-8-sig")
        nome = nome + ".csv"
    return {"nome": nome, "conteudo": conteudo, "linhas": total, "porMes": por_mes, "naoEncontradas": nao,
            "matriculas": None if ligs is None else len(ligs)}
