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
import json

import pandas as pd

from .config import ALIAS_SUP, LINHAS_INDIRETAS_DRE, SUP_POR_CIDADE, chave_texto, sup_da_localidade
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
    # nomes do RF antigo (RF3T25)
    "Cancelamento": "canc", "EconomiasdeAguaFaturadas": "ecoA", "EconomiasdeEsgotoFaturadas": "ecoE",
    "VolTotalFaturadoAgua": "volA", "VolTotalFaturadoEsgoto": "volE",
}
for _cl, _rotulo in LINHAS_INDIRETAS_DRE.items():
    if _cl != "LNE":
        ROTULOS_ORCADO[_rotulo] = "ri_" + _cl
# o RF também traz as linhas das indiretas só com o nome da classe (CORTE, RELIGAÇÃO, LNA, SANÇÃO, OUTROS)
for _cl in ("CORTE", "RELIGAÇÃO", "LNA", "SANÇÃO", "OUTROS"):
    ROTULOS_ORCADO[_cl] = "ri_" + _cl
ROTULOS_ORCADO = {chave_texto(k): v for k, v in ROTULOS_ORCADO.items()}
# Linhas "RI" do RF (metas das indiretas): reconhecidas também com pequenas variações no nome
# (ex.: "RI Ligações - Água", "RI Ligações Água", "RI Fiscalização - Água").
_PREFIXOS_RI = [(chave_texto("RI Cortes"), "ri_CORTE"), (chave_texto("RI Religa"), "ri_RELIGAÇÃO"),
                (chave_texto("RI Ligac"), "ri_LNA"), (chave_texto("RI Fiscaliz"), "ri_SANÇÃO"), (chave_texto("RI Outros"), "ri_OUTROS")]


def linha_do_orcado(chave):
    """Linha interna (ex.: 'dA', 'ri_CORTE') para o rótulo já normalizado com `chave_texto`; None se não reconhecido."""
    if chave in ROTULOS_ORCADO:
        return ROTULOS_ORCADO[chave]
    return next((linha for prefixo, linha in _PREFIXOS_RI if chave.startswith(prefixo)), None)


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
        t = base.dropna(subset=["Nome da Localidade"]).drop_duplicates("N. Ligação")
        mapa.update(dict(zip(_ligacao(t["N. Ligação"]), t["Nome da Localidade"])))
    avu = ctx.avulso if ctx.avulso is not None else pd.DataFrame()
    if len(avu) and "Nome da Localidade" in avu.columns:
        t = avu.dropna(subset=["Nome da Localidade", "N. da Ligacao"])
        for lig, cid in zip(_ligacao(t["N. da Ligacao"]), t["Nome da Localidade"]):
            mapa.setdefault(lig, cid)

    def marca(df, col_lig):
        if df is None or not len(df):
            return df
        df = df.copy(deep=False)                          # só acrescenta colunas: não precisa duplicar os dados
        cid = df["Nome da Localidade"] if "Nome da Localidade" in df.columns else pd.Series(index=df.index, dtype=object)
        faltam = cid.isna()
        if faltam.any():
            cid = cid.where(~faltam, _ligacao(df.loc[faltam, col_lig]).map(mapa))
        df["__cidade"] = cid
        unicas = cid.dropna().unique()                    # SUP calculada uma vez por cidade, não por linha
        df["__sup"] = cid.map({c: SUP_POR_CIDADE.get(chave_texto(c), SEM_SUP) for c in unicas}).fillna(SEM_SUP)
        if "Rubrica" in df.columns and "__serv" not in df.columns:   # serviço da linha (A = água, E = esgoto)
            rub = df["Rubrica"].astype(str)
            df["__serv"] = rub.map({r: "E" if "ESGOTO" in r.upper() else "A" if "AGUA" in r.upper() else "" for r in rub.unique()})
        return df

    ctx.base_final = marca(ctx.base_final, "N. Ligação")
    if getattr(ctx, "base_completa", None) is not None:
        ctx.base_completa = marca(ctx.base_completa, "N. Ligação")
    ctx.df_atual = marca(ctx.df_atual, "N. Ligação")
    ctx.df_anterior = marca(ctx.df_anterior, "N. Ligação")
    ctx.cancelamento = marca(ctx.cancelamento, "N. da Ligacao")
    ctx.avulso = marca(avu, "N. da Ligacao") if len(avu) else avu

    # superintendência de cada grupo: pela Localidade do cronograma; sem cronograma, pela SUP mais frequente das ligações do grupo.
    # Linhas sem cidade (SEM SUP) herdam a SUP do seu grupo.
    ctx.grupo_sup = sup_por_grupo(ctx)
    for nome in ("base_final", "base_completa", "df_atual", "df_anterior", "cancelamento", "avulso"):
        setattr(ctx, nome, _preenche_sup_pelo_grupo(getattr(ctx, nome, None), ctx.grupo_sup))

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
    if not fontes_rf(ctx):
        avisos.append("Orçado RF não encontrado (planilha com colunas Sup, Rubrica e meses, ex.: RF01T26.xlsx).")
    if not fontes_sup(ctx):
        avisos.append("Orçado SUP não encontrado (mesmo modelo do RF, com \"SUP\" no nome, ex.: RF SUP.xlsx).")
    sem_sup = ctx.df_atual[ctx.df_atual["__sup"] == SEM_SUP]
    if len(sem_sup):
        avisos.append(f"{len(sem_sup)} linhas do mês atual sem cidade/SUP identificada (a fatura precisa ter a coluna "
                      "\"Nome da Localidade\" ou a ligação aparecer no serviço avulso); aparecem em \"SEM SUP\".")
    ctx.avisos_dre = avisos
    ctx.dre_pronto = True


def _cache(ctx, nome, chave, funcao):
    """Guarda no contexto o resultado de `funcao()` enquanto `chave` (ids das bases usadas) não mudar."""
    atual = ctx.__dict__.get(nome)
    if atual is None or atual[0] != chave:
        atual = ctx.__dict__[nome] = (chave, funcao())
    return atual[1]


def sup_por_grupo(ctx):
    """{grupo: SUP}. Prioridade: cidade do grupo no cronograma (Localidade); senão, a SUP mais frequente nas linhas do grupo."""
    from .leitura import chave_grupo
    mapa = {}
    for g, cidade in (getattr(ctx, "grupo_localidade", None) or {}).items():
        sup = sup_da_localidade(cidade)               # cidade ou o próprio nome da SUP ("Lagos", "Leste")
        if sup:
            mapa[chave_grupo(g)] = sup
    base = getattr(ctx, "base_completa", None)
    base = ctx.base_final if base is None else base
    if base is not None and len(base) and "__sup" in base.columns:
        t = base.loc[base["__sup"] != SEM_SUP, ["Grupo", "__sup"]]
        if len(t):
            # conta primeiro por grupo bruto × SUP (poucas linhas) e só então normaliza o grupo — antes era linha a linha
            freq = t.groupby(["Grupo", "__sup"], observed=True, dropna=True).size().reset_index(name="n")
            freq["Grupo"] = freq["Grupo"].astype(str).map(chave_grupo)
            freq = freq.groupby(["Grupo", "__sup"], observed=True).n.sum().reset_index()
            for g, d in freq.sort_values("n", ascending=False).groupby(freq.columns[0]):
                mapa.setdefault(g, d["__sup"].iloc[0])
    return mapa


def _preenche_sup_pelo_grupo(df, grupo_sup):
    if df is None or not len(df) or "__sup" not in df.columns or "Grupo" not in df.columns or not grupo_sup:
        return df
    from .leitura import chave_grupo
    sem = df["__sup"] == SEM_SUP
    if not sem.any():
        return df
    grupos = df.loc[sem, "Grupo"]
    chaves = {g: grupo_sup.get(chave_grupo(g)) for g in grupos.dropna().unique()}
    novo = grupos.map(chaves)
    df = df.copy(deep=False)
    df.loc[sem, "__sup"] = novo.where(novo.notna(), SEM_SUP).values
    return df


def grupos_da_sup(ctx, rotulos):
    """{rótulo do grupo como aparece no filtro: SUP} para o filtro de grupos do relatório."""
    from .leitura import chave_grupo
    mapa = getattr(ctx, "grupo_sup", None) or {}
    return {g: mapa.get(chave_grupo(g), SEM_SUP) for g in rotulos}


def lista_sups(ctx):
    prepara(ctx)
    return list(_cache(ctx, "_lista_sups", (id(ctx.base_final), id(ctx.avulso)), lambda: _lista_sups(ctx)))


def _lista_sups(ctx):
    sups = set(ctx.base_final["__sup"].unique())
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
    """Realizado da DRE (com cache: a mesma SUP × mês é pedida por várias abas)."""
    ref = ref or ctx.ref_atual
    cache = ctx.__dict__.setdefault("_cache_realizado", {})
    chave = (id(ctx.base_final), id(ctx.avulso), sup, ref)
    if chave not in cache:
        cache[chave] = _realizado(ctx, sup, ref)
    return dict(cache[chave])


def _diretas_agregadas(ctx, base):
    """Soma das diretas por mês × SUP × serviço (valor; economias e volume só com Consumo > 0), calculada uma vez.
    Tabela pequena: a DRE de qualquer mês × SUP sai dela sem filtrar (nem copiar) a base de milhões de linhas."""
    def calcula():
        serv = base["__serv"] if "__serv" in base.columns else base["Rubrica"].astype(str).map(
            lambda r: "E" if "ESGOTO" in r.upper() else "A" if "AGUA" in r.upper() else "")
        pos = base["Consumo Faturado"] > 0
        t = pd.DataFrame({"ref": base["Referencia de Leitura"].values, "sup": base["__sup"].values, "s": serv.values,
                          "d": base["Valor (R$)"].values, "eco": base["Economias_Totais"].where(pos, 0).values,
                          "vol": base["Consumo Faturado"].where(pos, 0).values})
        return t[t["s"].isin(["A", "E"])].groupby(["ref", "sup", "s"]).sum()
    return _cache(ctx, "_diretas_%d" % id(base), id(base), calcula)


def _realizado(ctx, sup, ref):
    agg = _diretas_agregadas(ctx, ctx.base_final)
    r = {}
    for k in ("A", "E"):
        sel = agg[(agg.index.get_level_values("ref") == ref) & (agg.index.get_level_values("s") == k)
                  & ((agg.index.get_level_values("sup") == sup) if sup != TODAS else True)]
        r["d" + k] = float(sel["d"].sum())
        r["eco" + k] = float(sel["eco"].sum())
        r["vol" + k] = float(sel["vol"].sum())
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




def fontes_rf(ctx):
    return [n for n, i in ctx.orcado.items() if i["tipo"] == "rf"]


def fontes_sup(ctx):
    return [n for n, i in ctx.orcado.items() if i["tipo"] == "sup"]


def _sup_orcado(valor):
    k = chave_texto(valor)
    return ALIAS_SUP.get(k, k)


def orcado(ctx, fonte, sup, ref=None):
    """Valores da planilha de orçado `fonte` (ex.: "RF01T26") no mês, por linha. {} se não houver dados."""
    ref = ref or ctx.ref_atual
    info = ctx.orcado.get(fonte)
    if not info:
        return {}
    d = info["dados"]
    d = d[d["Referencia"] == ref]
    if sup != TODAS:                       # TODAS soma todas as superintendências da planilha
        d = d[d["Sup"].map(_sup_orcado) == _sup_orcado(sup)]
    r = {}
    for rotulo, valor in zip(d["Rubrica"].map(chave_texto), d["Valor"]):
        chave = linha_do_orcado(rotulo)
        if chave:
            r[chave] = r.get(chave, 0.0) + float(valor)
    return completa(r)


# ---------- meses e filtros ----------
def lista_meses(ctx):
    """Meses (MM/AAAA, em ordem) que têm dados de fatura, serviço avulso ou cancelamento."""
    prepara(ctx)
    return list(_cache(ctx, "_lista_meses", (id(ctx.base_final), id(ctx.avulso), id(ctx.cancelamento)), lambda: _lista_meses(ctx)))


def _lista_meses(ctx):
    refs = set(ctx.base_final["Referencia de Leitura"].dropna().unique())
    for df, col in ((ctx.avulso, "Referencia"), (ctx.cancelamento, "Referencia de Leitura")):
        if df is not None and len(df):
            refs |= set(df[col].dropna().unique())
    return sorted(refs, key=lambda r: (r[3:], r[:2]))


def _mes_anterior(ref):
    m, a = int(ref[:2]), int(ref[3:])
    return f"{12 if m == 1 else m - 1:02d}/{a - 1 if m == 1 else a}"


# ---------- HTML ----------
def _fmt(v, formato):
    if v is None:
        return "-"
    if formato == "dec":
        return fmt_num(v, 2)
    if formato == "num":
        return fmt_num(v, 0)
    texto = fmt_num(abs(v), 0)
    return f"R$ ({texto})" if v < 0 else f"R$ {texto}"


def _pct(real, orc):
    if real is None or orc in (None, 0):
        return None
    return real / orc - 1


def _cel(valor, cls=""):
    return f'<td class="{cls}">{valor}</td>'


def _celulas_delta(real, orc, formato, eh_canc, fonte):
    """Δ (%) e Δ (R$) do realizado contra um orçado. `fonte` liga as células ao filtro Referência."""
    dec = 2 if formato == "dec" else 0
    d = None if real is None or orc is None else real - orc
    pct = _pct(real, orc)

    def neg(v):
        return "neg" if (v is not None and v < -(0.005 if dec else 0.5) and not eh_canc) else ""
    src = html.escape(fonte, quote=True)
    return (f'<td class="num {neg(pct)}" data-src="{src}" data-tipo="dreal">{"-" if pct is None else fmt_num(pct * 100, 1) + "%"}</td>',
            f'<td class="num {neg(d)}" data-src="{src}" data-tipo="dreal">{"-" if d is None else fmt_num(d, dec)}</td>')


def _fontes(ctx):
    """Planilhas de orçado: RFs primeiro, depois RF SUP. E as combinações RF × RF SUP (comparação entre orçados)."""
    fontes = fontes_rf(ctx) + fontes_sup(ctx)
    combos = []                 # sem comparativo entre orçados: só orçado × realizado
    return fontes, combos


def _linha_dre(rotulo, formato, negrito, orc, real, eh_canc, fontes, combos, classe=""):
    """`orc`: {fonte: valor}. Colunas: orçados | realizado | Δ por orçado | Δ entre RF e RF SUP (R$ e %)."""
    dec = 2 if formato == "dec" else 0
    e = lambda v: html.escape(v, quote=True)
    cels = [f'<td class="dre-rotulo">{html.escape(rotulo)}</td>']
    for f in fontes:
        cels.append(f'<td class="num" data-src="{e(f)}" data-tipo="orc">{_fmt(orc.get(f), formato)}</td>')
    cels.append(f'<td class="num col-real" data-real="1">{_fmt(real, formato)}</td>')
    for f in fontes:
        cels.extend(_celulas_delta(real, orc.get(f), formato, eh_canc, f))
    for r, sp in combos:
        a, b = orc.get(r), orc.get(sp)
        pct = _pct(a, b)
        cels.append(f'<td class="num" data-combo="{e(r + "|" + sp)}">{"-" if a is None or b is None else fmt_num(a - b, dec)}</td>')
        cels.append(f'<td class="num" data-combo="{e(r + "|" + sp)}">{"-" if pct is None else fmt_num(pct * 100, 1) + "%"}</td>')
    return f'<tr class="{"dre-forte" if negrito else classe}">' + "".join(cels) + "</tr>"


def _cabecalho(ctx, primeira, fontes, combos):
    e = lambda v: html.escape(v, quote=True)
    ths = [f"<th>{primeira}</th>"]
    ths += [f'<th data-src="{e(f)}" data-tipo="orc">Orçado<br>{html.escape(f)}</th>' for f in fontes]
    ths.append('<th class="col-real" data-real="1">Realizado</th>')
    for f in fontes:
        ths.append(f'<th data-src="{e(f)}" data-tipo="dreal">Δ %<br>vs {html.escape(f)}</th>'
                   f'<th data-src="{e(f)}" data-tipo="dreal">Δ R$<br>vs {html.escape(f)}</th>')
    for r, sp in combos:
        ths.append(f'<th data-combo="{e(r + "|" + sp)}">Δ R$<br>{html.escape(r)} − {html.escape(sp)}</th>'
                   f'<th data-combo="{e(r + "|" + sp)}">Δ %<br>{html.escape(r)} vs {html.escape(sp)}</th>')
    return "<thead><tr>" + "".join(ths) + "</tr></thead>"


def _orcados_do_mes(ctx, sup, ref, fontes):
    return {f: orcado(ctx, f, sup, ref) for f in fontes}


def tabela_dre(ctx, sup, ref):
    real = realizado(ctx, sup, ref)
    fontes, combos = _fontes(ctx)
    orc = _orcados_do_mes(ctx, sup, ref, fontes)
    ncol = 2 + len(fontes) * 3 + len(combos) * 2
    linhas = []
    for chave, rotulo, formato, negrito in LINHAS:
        if chave is None:
            linhas.append(f'<tr class="dre-vazia"><td colspan="{ncol}"></td></tr>')
        else:
            linhas.append(_linha_dre(rotulo, formato, negrito, {f: orc[f].get(chave) for f in fontes}, real.get(chave),
                                     chave == "canc", fontes, combos))
    return ('<div class="tabela-wrap"><table class="tabela-dre">' + _cabecalho(ctx, "Projeto/Linha", fontes, combos)
            + "<tbody>" + "".join(linhas) + "</tbody></table></div>")


def _avisos_html(ctx):
    if not ctx.avisos_dre:
        return ""
    itens = "".join(f"<li>{html.escape(a)}</li>" for a in ctx.avisos_dre)
    return f'<div class="card avisos-card"><h2>Avisos</h2><ul class="avisos-dre">{itens}</ul></div>'


def _nome_sup(sup):
    return "Todas as superintendências (Interior)" if sup == TODAS else sup


def _bloco(sup, ref, conteudo):
    return f'<div class="sup-bloco" data-sup="{html.escape(sup, quote=True)}" data-mes="{ref}">{conteudo}</div>'


def gera_aba_dre_html(ctx):
    prepara(ctx)
    arquivos = [html.escape(i["arquivo"]) for i in ctx.orcado.values()]
    nota = ("Orçado: " + " · ".join(arquivos)) if arquivos else "Sem planilhas de orçado na pasta"
    blocos = []
    for ref in lista_meses(ctx):
        for sup in lista_sups(ctx):
            blocos.append(_bloco(sup, ref, (
                f'<div class="card"><h2>DRE — {html.escape(_nome_sup(sup))} — {nome_mes(ref)}</h2>'
                f'<p class="nota-secao">{nota}. Em Referência: compare o realizado com cada RF ou com o RF SUP.</p>'
                f'{tabela_dre(ctx, sup, ref)}</div>')))
    return "".join(blocos)


# ---------- Indiretas ----------
def _indiretas_mes(ctx, sup, ref):
    """{classe: (qtd, valor)} do serviço avulso no mês (sem as rubricas excluídas)."""
    av = _filtra(ctx.avulso, sup)
    if av is None or not len(av) or "Referencia" not in av.columns:
        return {cl: (0, 0.0) for cl in CLASSES_ORDEM}
    av = av[(av["Referencia"] == ref) & (av["Classe"] != "EXCLUIR")]
    g = av.groupby("Classe")["Valor Parcela"].agg(["size", "sum"])
    return {cl: (int(g.loc[cl, "size"]), float(g.loc[cl, "sum"])) if cl in g.index else (0, 0.0) for cl in CLASSES_ORDEM}


def grafico_evolucao(ctx, sup, ref, meses):
    """Só o gráfico de barras empilhadas da evolução mensal por classe (largura inteira)."""
    por_mes = {m: _indiretas_mes(ctx, sup, m) for m in meses}
    dados = {"meses": [nome_mes(m) for m in meses],
             "series": [{"classe": NOME_CLASSE[cl], "valores": [round(por_mes[m][cl][1], 2) for m in meses]} for cl in CLASSES_ORDEM]}
    return (f'<div class="grafico-area grafico-indiretas grafico-largo"><canvas class="canvas-indiretas" '
            f'data-dados="{html.escape(json.dumps(dados), quote=True)}" data-mes="{html.escape(nome_mes(ref))}"></canvas></div>')


def gera_aba_indiretas_html(ctx):
    from .previsao import indiretas_previsao_html
    prepara(ctx)
    if not len(ctx.avulso):
        return '<div class="card"><h2>Indiretas</h2><p>Nenhum arquivo de serviço avulso encontrado na pasta (o nome precisa conter "avulso").</p></div>'
    meses_av = sorted(set(ctx.avulso["Referencia"].dropna()), key=lambda r: (r[3:], r[:2]))
    blocos = []
    for ref in lista_meses(ctx):
        for sup in lista_sups(ctx):
            nome = html.escape(_nome_sup(sup))
            fin, eventos, ev, no_mes = indiretas_previsao_html(ctx, sup, ref)
            acoes = ('<span class="prev-acoes"><button type="button" class="btn-just btn-prev-restaurar" '
                     'onclick="previsaoRestaurar(this)">↺ Restaurar automático</button>'
                     '<button type="button" class="btn-just btn-prev-toggle" onclick="previsaoAlternar(this)">Ocultar forecast</button>'
                     '</span>') if no_mes else ""
            fc = (" <b>Clique em um valor da coluna Forecast ✎ para editar.</b>" if no_mes
                  else " Mês fechado: o fechamento é o próprio realizado (sem forecast).")
            meses_tk = ", ".join(nome_mes(m) for m in ev["meses_ticket"])
            blocos.append(_bloco(sup, ref, (
                f'<div class="card prev-card"><h2 class="prev-titulo">Indiretas — financeiro (R$) — {nome} — {nome_mes(ref)}{acoes}</h2>'
                '<p class="nota-secao prev-nota">Realizado = valor do serviço avulso do mês até D-1, por classe. Forecast = o mesmo da aba '
                'Forecast (ritmo por dia útil × dias úteis que faltam; Cortes pelos dias de corte) — editar aqui muda lá também.'
                f'{fc}</p>{fin}</div>'
                f'<div class="card prev-card"><h2 class="prev-titulo">Indiretas — eventos faturados — {nome} — {nome_mes(ref)}{acoes}</h2>'
                f'<p class="nota-secao prev-nota">Eventos = quantidade de lançamentos do serviço avulso. Orçado em eventos = orçado (R$) ÷ '
                f'ticket médio da classe nos 3 meses fechados anteriores ({meses_tk}). Forecast = eventos até D-1 ÷ dias úteis '
                f'decorridos × dias úteis que faltam (Cortes pelos dias de corte).{fc}</p>{eventos}</div>'
                f'<div class="card"><h2>Evolução mensal por classe — {nome}</h2>{grafico_evolucao(ctx, sup, ref, meses_av)}</div>')))
    return "".join(blocos)


def opcoes_referencia(ctx):
    """[(valor, rótulo)]: cada RF, o RF SUP e as comparações RF × RF SUP. O valor lista as planilhas mostradas."""
    rfs, sups = fontes_rf(ctx), fontes_sup(ctx)
    itens = [(r + "|" + s, f"{r} × {s} (com realizado)") for r in rfs for s in sups]
    itens += [("cmp:" + r + "|" + s, f"{r} × {s} (só orçados)") for r in rfs for s in sups]
    itens += [(r, r) for r in rfs] + [(s, s) for s in sups]
    return itens


def gera_filtros_dre_html(ctx):
    """Seletores para quando o relatório é aberto sozinho (no site, o cabeçalho cuida disso)."""
    def opcoes(itens):
        return "".join(f'<option value="{html.escape(v, quote=True)}">{html.escape(t)}</option>' for v, t in itens)
    sups = opcoes([(s, _nome_sup(s) if s == TODAS else s) for s in lista_sups(ctx)])
    meses = opcoes([(m, nome_mes(m)) for m in lista_meses(ctx)])
    refs = opcoes(opcoes_referencia(ctx))
    return ('<span class="seletor-sup" id="seletorSup" hidden>'
            f'<label>Superintendência <select id="selSup" onchange="definirFiltros({{sup:this.value}})">{sups}</select></label>'
            f'<label>Mês <select id="selMes" onchange="definirFiltros({{mes:this.value}})">{meses}</select></label>'
            f'<label>Referência <select id="selRef" onchange="definirFiltros({{ref:this.value}})">{refs}</select></label></span>')


def gera_info_filtros_json(ctx):
    refs = opcoes_referencia(ctx)
    info = {"sups": lista_sups(ctx), "meses": [{"ref": m, "label": nome_mes(m)} for m in lista_meses(ctx)],
            "mesAtual": ctx.ref_atual, "fontes": fontes_rf(ctx) + fontes_sup(ctx), "refs": [{"valor": v, "rotulo": t} for v, t in refs],
            "refPadrao": refs[0][0] if refs else "",
            "grupoSup": grupos_da_sup(ctx, sorted({str(g).strip() for g in ctx.fatura_total["Grupo"].dropna()} - {"nan", "None", ""}))
            if getattr(ctx, "fatura_total", None) is not None else {}}
    return '<script type="application/json" id="info-filtros">' + json.dumps(info).replace("<", "\\u003c") + "</script>"
