# -*- coding: utf-8 -*-
"""Grandes Clientes (GC): faturamento, consumo e data de vencimento, mês a mês, das matrículas de uma lista.

A lista vem de duas fontes, somadas:
  - planilha da pasta com as colunas Matricula e TIPO (ex.: "Matriculas Leste GC.xlsx" — reconhecida sozinha);
  - matrículas adicionadas na aba Dados do relatório (ficam no ajustes_relatorio.json da pasta, seção "gc").
O Excel é gerado sob demanda pelo site (botão "GC" da aba Dados) com a análise que já está carregada: todos os meses
de fatura da pasta e todos os grupos (base completa).
"""
import html
import io
import json
import re

import numpy as np
import pandas as pd

from .config import chave_texto
from .formatacao import nome_mes_curto

COLUNAS_LISTA = {"MATRICULA", "TIPO"}
TIPO_PADRAO = "GC"


def eh_lista_gc(colunas):
    """A planilha tem as colunas Matricula e TIPO (sem acento/maiúsculas não importam)."""
    return COLUNAS_LISTA.issubset({chave_texto(c) for c in colunas})


def chave_matricula(valor):
    """Chave para comparar matrículas: só os dígitos, sem zeros à esquerda ("0102340199", "102340199.0" → "102340199")."""
    s = "" if valor is None else str(valor).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    d = re.sub(r"\D", "", s)
    return (d.lstrip("0") or d) if d else s.upper()


def le_lista_gc(caminho, aba=0):
    """Planilha da lista → DataFrame [Matricula, Tipo] (linhas sem matrícula ficam de fora)."""
    from .leitura import le_dataframe
    df = le_dataframe(caminho, sheet_name=aba)
    if df is None or not len(df):
        return pd.DataFrame(columns=["Matricula", "Tipo"])
    col = {chave_texto(c): c for c in df.columns}
    mat = df[col["MATRICULA"]].astype(object).where(df[col["MATRICULA"]].notna(), "")
    tipo = df[col["TIPO"]].astype(object).where(df[col["TIPO"]].notna(), "")
    out = pd.DataFrame({"Matricula": [chave_matricula(m) for m in mat],
                        "Tipo": [str(t).strip().upper() or TIPO_PADRAO for t in tipo]})
    return out[out["Matricula"] != ""].reset_index(drop=True)


def carrega_lista(ctx):
    """ctx.gc_lista = [{mat, tipo, arquivo}] das planilhas de matrículas da pasta (a primeira ocorrência vale)."""
    from . import cache_arquivos
    from .leitura import nome_relativo
    vistos, lista = set(), []
    for caminho, aba in ctx.classificacao.get("matriculas_gc", []):
        arquivo = nome_relativo(caminho, ctx.pasta)
        try:
            df = cache_arquivos.memo(caminho, f"le_lista_gc_{aba}", lambda c=caminho, a=aba: le_lista_gc(c, a))
        except Exception as exc:                   # lista com problema não derruba a análise
            ctx.avisos_base.append(f"Lista de matrículas GC em {arquivo} não pôde ser lida ({exc}).")
            continue
        novas = 0
        for m, t in zip(df["Matricula"], df["Tipo"]):
            if m not in vistos:
                vistos.add(m)
                lista.append({"mat": m, "tipo": t, "arquivo": arquivo})
                novas += 1
        tipos = ", ".join(sorted(set(df["Tipo"]))) or "—"
        ctx.bases_info_extra = getattr(ctx, "bases_info_extra", []) + [
            {"tipo": "Matrículas GC", "arquivo": arquivo, "linhas": len(df), "periodo": "", "extra": f"tipos: {tipos}"}]
    ctx.gc_lista = lista
    if lista:
        print(f"✅ Matrículas GC: {len(lista)}")
    return lista


def _chave_ref(r):
    return (str(r)[3:], str(r)[:2])


FORMATOS_VENCIMENTO = ("%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%y",
                       "%d.%m.%Y", "%d-%m-%Y", "%Y%m%d", "%Y/%m/%d")


def _vencimentos(serie):
    """Datas de vencimento distintas do mês → data única ou texto com todas. Aceita dd/mm/aaaa, dd/mm/aa, aaaa-mm-dd,
    dd.mm.aaaa, número de série do Excel (46310); o que não for data aparece como está na fatura."""
    from .leitura import converte_datas
    textos = pd.Series(serie.dropna().astype(str).str.strip().unique())
    textos = textos[~textos.isin(["", "nan", "None", "NaT"])]
    if not len(textos):
        return None
    dt = converte_datas(textos, FORMATOS_VENCIMENTO)
    serial = textos.str.fullmatch(r"\d{5}(\.0+)?") & dt.isna()          # data do Excel salva como número
    if serial.any():
        dt[serial] = pd.Timestamp("1899-12-30") + pd.to_timedelta(textos[serial].astype(float), unit="D")
    datas = sorted({pd.Timestamp(d) for d in dt.dropna()})
    outros = sorted(textos[dt.isna()])
    if not datas:
        return ", ".join(outros)
    if len(datas) == 1 and not outros:
        return datas[0].to_pydatetime().date()
    return ", ".join([d.strftime("%d/%m/%Y") for d in datas] + outros)


def monta_gc(ctx, lista):
    """Analítico (uma linha por matrícula × mês) das matrículas de `lista` ([{mat, tipo}]), com todos os meses da base.
    Devolve (analitico, refs, cadastro) — cadastro: uma linha por matrícula da lista, na ordem da lista."""
    b = ctx.base_completa if getattr(ctx, "base_completa", None) is not None else ctx.base_final
    ordem = {}
    for item in lista:
        k = chave_matricula(item.get("mat"))
        if k and k not in ordem:
            ordem[k] = str(item.get("tipo") or TIPO_PADRAO).strip().upper() or TIPO_PADRAO
    lig = b["N. Ligação"].astype(str)
    unicas = lig.unique()
    chave_por_lig = dict(zip(unicas, (chave_matricula(u) for u in unicas)))
    chaves = lig.map(chave_por_lig)
    sel = chaves.isin(ordem.keys())
    d = b[sel].copy()
    d["__k"] = chaves[sel]
    serv = d["__serv"] if "__serv" in d.columns else d["Rubrica"].astype(str).str.upper().map(
        lambda r: "E" if "ESGOTO" in r else "A" if "AGUA" in r else "")
    num = lambda c: pd.to_numeric(d[c], errors="coerce").fillna(0) if c in d.columns else pd.Series(0.0, index=d.index)
    agua, esg = serv == "A", serv == "E"
    d["__valA"] = num("Valor (R$)").where(agua, 0)
    d["__valE"] = num("Valor (R$)").where(esg, 0)
    d["__consA"] = num("Consumo Faturado").where(agua, 0)
    d["__consE"] = num("Consumo Faturado").where(esg, 0)
    d["__med"] = num("Consumo Medido").where(agua, 0)
    refs = sorted({r for r in b["Referencia de Leitura"].dropna().unique()}, key=_chave_ref)

    linhas = []
    for (k, ref), g in d.groupby(["__k", "Referencia de Leitura"], sort=False):
        ga = g[agua.loc[g.index]] if agua.loc[g.index].any() else g           # dados cadastrais da linha de água
        pega = lambda c: next((v for v in ga[c] if pd.notna(v) and str(v).strip()), None) if c in ga.columns else None
        linhas.append({
            "__k": k, "__ordem_ref": _chave_ref(ref), "Referência": ref, "Mês": nome_mes_curto(ref),
            "Nome Cliente": pega("Nome Cliente"), "Categoria": pega("Categoria"), "Grupo": pega("Grupo"),
            "Localidade": pega("Nome da Localidade"), "Situação Conta": pega("Situacao Conta"),
            "Data de Vencimento": _vencimentos(g["Data de Vencimento"]) if "Data de Vencimento" in g.columns else None,
            "Consumo Medido (m³)": g["__med"].sum(), "Consumo Faturado Água (m³)": g["__consA"].sum(),
            "Volume Esgoto (m³)": g["__consE"].sum(), "Faturado Água (R$)": round(g["__valA"].sum(), 2),
            "Faturado Esgoto (R$)": round(g["__valE"].sum(), 2), "Faturado Total (R$)": round(g["__valA"].sum() + g["__valE"].sum(), 2),
        })
    an = pd.DataFrame(linhas)
    pos = {k: i for i, k in enumerate(ordem)}
    cadastro = []
    for k, tipo in ordem.items():
        mais_recente = (an[an["__k"] == k].sort_values("__ordem_ref").iloc[-1] if len(an) and (an["__k"] == k).any() else None)
        cadastro.append({"Matrícula": k, "Tipo": tipo,
                         "Nome Cliente": mais_recente["Nome Cliente"] if mais_recente is not None else "NÃO ENCONTRADA NA BASE",
                         "Categoria": mais_recente["Categoria"] if mais_recente is not None else None,
                         "Grupo": mais_recente["Grupo"] if mais_recente is not None else None})
    cadastro = pd.DataFrame(cadastro, columns=["Matrícula", "Tipo", "Nome Cliente", "Categoria", "Grupo"])
    if len(an):
        an.insert(0, "Matrícula", an["__k"])
        an.insert(1, "Tipo", an["__k"].map(ordem))
        an["__pos"] = an["__k"].map(pos)
        an = an.sort_values(["__pos", "__ordem_ref"]).drop(columns=["__k", "__pos", "__ordem_ref"]).reset_index(drop=True)
    return an, refs, cadastro


def _por_mes(an, cadastro, refs, coluna, com_totais=True):
    """Matrícula × mês de uma coluna do analítico (meses na ordem; média e total no fim)."""
    t = cadastro.copy()
    meses = [nome_mes_curto(r) for r in refs]
    if len(an):
        p = an.pivot_table(index="Matrícula", columns="Referência", values=coluna, aggfunc="first")
    else:
        p = pd.DataFrame()
    for r, m in zip(refs, meses):
        t[m] = t["Matrícula"].map(p[r]) if r in p.columns else None
    if com_totais:
        v = t[meses].apply(pd.to_numeric, errors="coerce")
        t["Média"] = v.mean(axis=1).round(2)
        t["Total"] = v.sum(axis=1, min_count=1).round(2)
    return t


def _combinado(an, cadastro, refs):
    """Aba principal: uma linha por matrícula e, para cada mês, Faturado | Consumo | Vencimento lado a lado."""
    t = cadastro.copy()
    campos = (("Faturado Total (R$)", "Faturado (R$)"), ("Consumo Faturado Água (m³)", "Consumo (m³)"),
              ("Data de Vencimento", "Vencimento"))
    piv = {c: (an.pivot_table(index="Matrícula", columns="Referência", values=c, aggfunc="first") if len(an) else pd.DataFrame())
           for c, _ in campos}
    for r in refs:
        for c, rotulo in campos:
            p = piv[c]
            t[f"{nome_mes_curto(r)} {rotulo}"] = t["Matrícula"].map(p[r]) if r in p.columns else None
    return t


def _texto_data(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    return v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else str(v)


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(v) else round(v, 2)


def dados_gc(ctx, lista):
    """Dados da tela (aba Dados): por matrícula, cadastro e os meses [ref, vencimento, medido, água, esgoto (m³),
    faturado água, esgoto, total]."""
    an, refs, cad = monta_gc(ctx, lista)
    por_mat = {}
    for r in an.to_dict("records"):
        por_mat.setdefault(r["Matrícula"], []).append([
            r["Referência"], _texto_data(r["Data de Vencimento"]), _num(r["Consumo Medido (m³)"]),
            _num(r["Consumo Faturado Água (m³)"]), _num(r["Volume Esgoto (m³)"]), _num(r["Faturado Água (R$)"]),
            _num(r["Faturado Esgoto (R$)"]), _num(r["Faturado Total (R$)"])])
    texto = lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)
    return {"refs": refs, "matriculas": [
        {"mat": c["Matrícula"], "tipo": c["Tipo"], "nome": texto(c["Nome Cliente"]), "cat": texto(c["Categoria"]),
         "grupo": texto(c["Grupo"]), "achada": c["Matrícula"] in por_mat, "meses": por_mat.get(c["Matrícula"], [])}
        for c in cad.to_dict("records")]}


def gera_xlsx_gc(ctx, lista):
    """(bytes do .xlsx, nome do arquivo, info) — aba GC (por mês: faturado, consumo e vencimento lado a lado), abas
    Faturamento, Consumo e Vencimento (matrícula × mês) e Analítico (matrícula × mês, todas as colunas)."""
    from .tabelas_html import motor_excel
    an, refs, cadastro = monta_gc(ctx, lista)
    abas = {
        "GC": _combinado(an, cadastro, refs),
        "Faturamento (R$)": _por_mes(an, cadastro, refs, "Faturado Total (R$)"),
        "Consumo (m³)": _por_mes(an, cadastro, refs, "Consumo Faturado Água (m³)"),
        "Vencimento": _por_mes(an, cadastro, refs, "Data de Vencimento", com_totais=False),
        "Analítico": an if len(an) else pd.DataFrame(columns=["Matrícula", "Tipo", "Referência", "Mês"]),
    }
    motor = motor_excel()
    if motor is None:
        raise RuntimeError("nenhum gravador de Excel disponível (openpyxl/xlsxwriter)")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine=motor, date_format="DD/MM/YYYY", datetime_format="DD/MM/YYYY") as w:
        for nome, df in abas.items():
            df.to_excel(w, sheet_name=nome[:31], index=False)
    encontradas = int((cadastro["Nome Cliente"] != "NÃO ENCONTRADA NA BASE").sum())
    ref = getattr(ctx, "ref_atual", "") or (refs[-1] if refs else "")
    nome = f"GC_Faturamento_Consumo_{ref.replace('/', '-')}.xlsx" if ref else "GC_Faturamento_Consumo.xlsx"
    info = {"nome": nome, "matriculas": len(cadastro), "encontradas": encontradas, "meses": len(refs)}
    return buf.getvalue(), nome, info


def gera_card_gc_html(ctx):
    """Cartão da aba Dados: botão do Excel, campo para adicionar e cada matrícula como um tópico que abre (relatorio.js),
    com faturamento, consumo e vencimento mês a mês. Os dados das matrículas da planilha vêm embutidos; os das adicionadas
    o site busca na análise carregada."""
    lista = getattr(ctx, "gc_lista", None) or []
    arquivos = sorted({i["arquivo"] for i in lista})
    dados = json.dumps({"lista": [{"mat": i["mat"], "tipo": i["tipo"]} for i in lista], "arquivos": arquivos,
                        "dados": dados_gc(ctx, lista) if lista else {"refs": [], "matriculas": []}},
                       ensure_ascii=False).replace("</", "<\\/")
    origem = (f'Lista da pasta: <b>{html.escape(", ".join(arquivos))}</b>.' if arquivos else
              'Nenhuma planilha de matrículas GC na pasta (colunas <b>Matricula</b> e <b>TIPO</b>, ex.: "Matriculas Leste GC.xlsx").')
    return f"""
<div class="card gc-card" id="gc-card">
  <div class="gar-topo"><h2>Grandes Clientes (GC)</h2>
    <button type="button" class="btn-filtro" id="gcBaixar" title="Baixar faturamento, consumo e data de vencimento de todos os meses das matrículas da lista (Excel)">&#11015; GC (Excel)</button></div>
  <p class="nota-secao">Clique em uma matrícula para abrir o faturamento (água + esgoto), o consumo e a data de vencimento <b>mês a mês</b>
  (todos os meses da pasta). {origem} Para incluir mais: acrescente linhas na planilha da pasta e analise de novo, ou digite abaixo
  (ficam salvas na pasta, para todos).</p>
  <div class="gar-barra gar-entrada">
    <label for="gcEntrada">Matrículas</label>
    <textarea id="gcEntrada" rows="1" placeholder="Digite ou cole matrículas (uma por linha; pode colar as colunas Matricula e TIPO do Excel)"></textarea>
    <label for="gcTipo">Tipo</label><input type="text" id="gcTipo" value="{TIPO_PADRAO}" size="6" autocomplete="off">
    <button type="button" class="btn-just" id="gcAdicionar">Adicionar</button>
    <span class="gar-msg" id="gcMsg" role="status"></span>
  </div>
  <p class="nota-secao">A lista fica fechada: clique em <b>Matrículas da lista</b> para ver as ligações.</p>
  <details class="val-aba" id="gcListaWrap"><summary id="gcListaTitulo">Matrículas da lista</summary>
    <div class="val-bloco"><div id="gcLista"></div></div></details>
</div>
<script type="application/json" id="gc-dados">{dados}</script>
"""
