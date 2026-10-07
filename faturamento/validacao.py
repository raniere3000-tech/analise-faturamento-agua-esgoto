# -*- coding: utf-8 -*-
"""Aba Dados — "Validação dos cálculos": para cada tabela e gráfico, aba por aba (na ordem de navegação), descreve o que mostra,
quais bases e colunas entram, o cálculo passo a passo e como é montado; mostra uma amostra e permite baixar a tabela (Excel)
e as bases usadas (CSV, embutidas uma vez e referenciadas pelos botões de cada item)."""
import html

import pandas as pd

from .config import COLUNAS_ECONOMIA_TODAS
from .dre import LINHAS, TODAS, _fontes, orcado, realizado
from .formatacao import fmt_num
from .tabelas_html import botao_download_xlsx, botoes_por_sup, filtra_sup, xlsx_bytes

LIMITE_BASE = 300000         # linhas por base para download (o Excel aceita até ~1 milhão)
COLUNAS_BASE = ["N. Ligação", "Grupo", "Rubrica", "Referencia de Leitura", "Valor (R$)", "Consumo Faturado", "Economias_Totais",
                "Qts. Dias", "Situacao Ligacao", "Situacao Lancamento", "Categoria", "Cidade"]


def _amostra(df, n=10):
    if df is None or not len(df):
        return '<p class="nota-secao">Sem dados para amostra.</p>'
    d = df.head(n)
    cab = "".join(f"<th>{html.escape(str(c))}</th>" for c in d.columns)
    def cel(v):
        if isinstance(v, float):
            return "—" if pd.isna(v) else fmt_num(v, 2)
        return html.escape("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))
    corpo = "".join("<tr>" + "".join(f"<td>{cel(v)}</td>" for v in linha) + "</tr>" for linha in d.itertuples(index=False))
    return (f'<div class="tabela-wrap"><table class="tabela-dados"><thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table></div>'
            f'<p class="nota-secao">Amostra: {len(d)} de {len(df)} linha(s).</p>')


def _lista(itens):
    return "<ul>" + "".join(f"<li>{i}</li>" for i in itens) + "</ul>"


def _bloco(titulo, descricao, formulas, colunas, abas, slug, bases=(), montagem=(), ctx=None):
    """Um item (tabela ou gráfico) da validação.
    abas: {nome: DataFrame} — a primeira aparece como amostra; todas vão no Excel "Baixar tabela".
      Ou função(sup) -> {nome: DataFrame} (com ctx): um Excel por superintendência, que segue o filtro Superintendência;
      a amostra é a de Todas.
    bases: [(chave, filtro)] — bases para baixar (CSV) e o filtro a aplicar nelas para chegar ao resultado.
    montagem: como a tabela/gráfico é construído na tela (linhas, colunas, cores, totais)."""
    if callable(abas):
        botao = botoes_por_sup(ctx, "Baixar tabela (Excel)", f"validacao_{slug}.xlsx", abas)
        abas = abas(TODAS) or {}
    else:
        botao = None
    abas = {k: v for k, v in abas.items() if v is not None and len(v)}
    primeira = next(iter(abas.values()), None)
    if botao is None:
        botao = botao_download_xlsx("Baixar tabela (Excel)", f"validacao_{slug}.xlsx", xlsx_bytes(abas)) if abas else ""
    itens_base = [f'{_botao_base(ch)} <span class="val-filtro">{filtro}</span>' for ch, filtro in bases if ch in BASES]
    secao_bases = (f'<p class="val-rot">Bases utilizadas (baixe e aplique o filtro indicado para chegar ao resultado)</p>'
                   f'<ul class="val-bases">{"".join(f"<li>{i}</li>" for i in itens_base)}</ul>') if itens_base else ""
    secao_montagem = f'<p class="val-rot">Como a tabela / o gráfico é montado</p>{_lista(montagem)}' if montagem else ""
    return (f'<div class="val-bloco"><h4>{html.escape(titulo)} {botao}</h4><p><b>O que mostra:</b> {descricao}</p>'
            f'{secao_bases}<p class="val-rot">Colunas utilizadas</p>{_lista(colunas)}'
            f'<p class="val-rot">Cálculo passo a passo</p>{_lista(formulas)}{secao_montagem}'
            f'<p class="val-rot">Amostra do resultado</p>{_amostra(primeira)}</div>')


def _aba(titulo, blocos, aberto=False):
    return f'<details class="val-aba"{" open" if aberto else ""}><summary>{html.escape(titulo)}</summary>{"".join(blocos)}</details>'


def _dre_df(ctx, sup=TODAS):
    fontes, _ = _fontes(ctx)
    real = realizado(ctx, sup, ctx.ref_atual)
    orc = {f: orcado(ctx, f, sup, ctx.ref_atual) for f in fontes}
    linhas = []
    for chave, rotulo, formato, negrito in LINHAS:
        if chave is None:
            continue
        r = {"Rubrica": rotulo, "Realizado": real.get(chave)}
        for f in fontes:
            o = orc[f].get(chave)
            r[f"Orçado {f}"] = o
            r[f"Δ R$ vs {f}"] = None if o is None or r["Realizado"] is None else r["Realizado"] - o
            r[f"Δ % vs {f}"] = None if not o or r["Realizado"] is None else (r["Realizado"] / o - 1) * 100
        linhas.append(r)
    return pd.DataFrame(linhas)


def _indiretas_df(ctx):
    """Mesma ordem da tela: Fat. de água - Indireto, aberturas RI, Fat. de esgoto - Indireto e Total indiretas."""
    d = _dre_df(ctx).set_index("Rubrica")
    ordem = [rot for ch in ("iA", "ri_CORTE", "ri_RELIGAÇÃO", "ri_LNA", "ri_SANÇÃO", "ri_OUTROS", "iE")
             for c, rot, _, _ in LINHAS if c == ch]
    d = d.loc[[r for r in ordem if r in d.index]]
    tot = d.loc[[r for r in (ordem[0], ordem[-1]) if r in d.index]].sum(min_count=1)
    tot.name = "Total indiretas"
    for col in [c for c in d.columns if c.startswith("Δ % vs ")]:          # % do total recalculado, não somado
        f = col[len("Δ % vs "):]
        o = tot.get(f"Orçado {f}")
        tot[col] = (tot["Realizado"] / o - 1) * 100 if o else None
    return pd.concat([d, tot.to_frame().T]).rename_axis("Rubrica").reset_index()


def _forecast_df(ctx, sup=TODAS, dados=None):
    from .dre import completa
    from .previsao import LINHAS_BASICAS, calcula_previsao
    dados = dados or calcula_previsao(ctx, sup)
    if not dados:
        return None
    atual, falta = dados["atual"], dados["falta"]
    fech = completa({k: (atual.get(k) or 0.0) + (falta.get(k) or 0.0) for k in LINHAS_BASICAS})
    razoes = {"vmA", "vmE", "tarA", "tarE", "tickA", "tickE"}      # médias: refeitas no fechamento, sem forecast próprio
    linhas = []
    for chave, rotulo, formato, negrito in LINHAS:
        if chave is None or atual.get(chave) is None:
            continue
        real, f = atual.get(chave), fech.get(chave)
        fc = None if chave in razoes or f is None else f - real
        linhas.append({"Rubrica": rotulo, "Realizado": real, "Forecast": fc, "Realizado + Forecast": f})
    return pd.DataFrame(linhas)


def _orcado_ciclo_dfs(ctx):
    from .orcado_ciclo import RUBRICAS, comparativo_orcado
    fontes, _ = _fontes(ctx)
    abas = {}
    for f in fontes:
        orc = orcado(ctx, f, TODAS, ctx.ref_atual)
        if not orc:
            continue
        for rotulo, rub, kf, kv, ke in RUBRICAS:
            comp = comparativo_orcado(ctx, rotulo, rub, kf, kv, ke, orc)
            if len(comp):
                comp = comp.rename(columns=lambda c: c.replace("_atual", "_realizado").replace("_anterior", "_orcado"))
                abas[f"{rotulo} x {f}"] = comp
    return abas


# ---------- bases para download (CSV, embutidas uma vez e referenciadas pelos botões de cada item) ----------
BASES = {}          # chave -> {"nome", "descricao", "df", "truncada"} (preenchido por monta_bases a cada relatório)
NOMES_BASES = {
    "fatura": "Fatura detalhada — água e esgoto (mês atual e anterior)",
    "fatura_mensal": "Fatura resumida por mês × grupo × serviço (todos os meses)",
    "avulso": "Serviço avulso (indiretas)",
    "cancelamento": "Cancelamentos da fatura",
    "orcado": "Orçado (planilhas RF e RF SUP)",
}


def _sup(df):
    return df.rename(columns={"__sup": "Superintendência", "__cidade": "Cidade (SUP)"})


def monta_bases(ctx):
    """Prepara as bases que alimentam os cálculos, no formato para conferência."""
    from .dre import linha_do_orcado
    from .config import chave_texto
    BASES.clear()
    fat = ctx.base_final
    fat = fat[fat["Referencia de Leitura"].isin([ctx.ref_anterior, ctx.ref_atual])]
    fat = fat[(fat["__serv"] != "") if "__serv" in fat.columns else fat["Rubrica"].str.contains("AGUA|ESGOTO", case=False, na=False)]
    cols = [c for c in COLUNAS_BASE + COLUNAS_ECONOMIA_TODAS + ["Situacao Conta", "Nome da Localidade", "__sup"] if c in fat.columns]
    total_fat = len(fat)
    fat = _sup(fat[list(dict.fromkeys(cols))].head(LIMITE_BASE)).copy()      # só as linhas que vão para o CSV
    fat["Entra em economias/volume"] = (fat["Consumo Faturado"] > 0).map({True: "Sim", False: "Não"})
    BASES["fatura"] = {"df": fat, "truncada": total_fat > LIMITE_BASE, "total": total_fat}

    comp = getattr(ctx, "base_completa", None)
    comp = ctx.base_final if comp is None else comp
    cols_m = [c for c in ("Referencia de Leitura", "Grupo", "Rubrica", "Valor (R$)", "Consumo Faturado", "Economias_Totais",
                          "__sup", "__serv") if c in comp.columns]
    d = comp[cols_m]                                   # só as colunas da soma (não copia a base inteira)
    d = d[(d["__serv"] != "") if "__serv" in d.columns else d["Rubrica"].str.contains("AGUA|ESGOTO", case=False, na=False)].copy()
    d["Serviço"] = (d["__serv"] == "E" if "__serv" in d.columns
                    else d["Rubrica"].str.contains("ESGOTO", case=False, na=False)).map({True: "Esgoto", False: "Água"})
    d["Grupo"] = d["Grupo"].astype(str).str.strip()
    pos = d["Consumo Faturado"] > 0
    d["Volume (Consumo>0)"] = d["Consumo Faturado"].where(pos, 0)
    d["Economias (Consumo>0)"] = d["Economias_Totais"].where(pos, 0)
    chaves = ["Referencia de Leitura", "Grupo", "Serviço"] + (["__sup"] if "__sup" in d.columns else [])
    mensal = d.groupby(chaves).agg(**{"Valor (R$)": ("Valor (R$)", "sum"), "Volume faturado": ("Volume (Consumo>0)", "sum"),
                                     "Economias faturadas": ("Economias (Consumo>0)", "sum"),
                                     "Linhas": ("Valor (R$)", "size")}).reset_index()
    mensal["_ord"] = mensal["Referencia de Leitura"].map(lambda r: (r[3:], r[:2]))
    mensal = _sup(mensal.sort_values(["_ord", "Grupo", "Serviço"]).drop(columns="_ord"))
    BASES["fatura_mensal"] = {"df": mensal, "truncada": False, "total": len(mensal)}

    # só as colunas que interessam para conferir (o arquivo embutido no relatório fica bem menor)
    cols_av = ["N. da Ligacao", "Grupo", "Rubrica", "Classe", "Valor Parcela", "Referencia de Leitura", "Referencia",
               "Nome da Localidade", "__sup"]
    cols_canc = ["N. da Ligacao", "Grupo", "Rubrica", "Valor Parcela", "Referencia de Leitura", "Nome da Localidade", "__sup"]
    for chave, df, cols in (("avulso", ctx.avulso, cols_av), ("cancelamento", ctx.cancelamento, cols_canc)):
        if df is not None and len(df):
            parte = df[[c for c in cols if c in df.columns]].head(LIMITE_BASE)
            BASES[chave] = {"df": _sup(parte), "truncada": len(df) > LIMITE_BASE, "total": len(df)}

    linhas = []
    nomes = {"bruto": "Faturamento Bruto", "dA": "DIRETAS ÁGUA", "dE": "DIRETAS ESGOTO", "iA": "Fat. de água - Indireto",
             "iE": "Fat. de esgoto - Indireto", "canc": "Cancelamento", "ecoA": "Economias de Água", "ecoE": "Economias de Esgoto",
             "volA": "Volume de Água", "volE": "Volume de Esgoto"}
    for nome, info in ctx.orcado.items():
        o = info["dados"].copy()
        o.insert(0, "Arquivo", info["arquivo"])
        o.insert(0, "Planilha", nome)
        o["Linha da DRE"] = o["Rubrica"].map(lambda r: (lambda k: nomes.get(k, NOME_BASICA.get(k, "não usada")) if k else "não usada")(
            linha_do_orcado(chave_texto(r))))
        linhas.append(o)
    if linhas:
        orc = pd.concat(linhas, ignore_index=True)
        if "Sup" in orc.columns:                       # SUP padronizada (Interior → LAGOS) para o filtro Superintendência
            from .dre import _sup_orcado
            orc["Superintendência"] = orc["Sup"].map(_sup_orcado)
        BASES["orcado"] = {"df": orc, "truncada": False, "total": len(orc)}


def _csv_b64(df):
    """CSV comprimido (gzip) em base64: o relatório fica bem menor (abre mais rápido); o navegador descompacta ao baixar."""
    import base64
    import gzip
    texto = "\ufeff" + df.to_csv(sep=";", decimal=",", index=False)
    return base64.b64encode(gzip.compress(texto.encode("utf-8"), 3)).decode("ascii")


def _botao_base(chave):
    return (f'<button type="button" class="btn-just btn-baixar-base" data-ref="{chave}">&#11015; Base: '
            f'{html.escape(NOMES_BASES[chave])} (CSV)</button>')


def _secao_bases(ctx):
    """Lista das bases com botão de download + os dados embutidos (uma vez só)."""
    if not BASES:
        return ""
    linhas = []
    for ch, info in BASES.items():
        obs = (f" — <b>limitada às primeiras {fmt_num(LIMITE_BASE)} de {fmt_num(info['total'])} linhas</b>" if info["truncada"]
               else f" — {fmt_num(info['total'])} linhas")
        linhas.append(f"<li>{_botao_base(ch)}{obs}. {DESCRICAO_BASES[ch]}</li>")
    dados = "".join(f'<script type="application/octet-stream" id="base-dl-{ch}" data-gz="1" data-arquivo="base_{ch}.csv">{_csv_b64(i["df"])}</script>'
                    for ch, i in BASES.items())
    return ('<p class="val-rot">Bases para download</p>'
            '<p>Arquivos CSV (separador ";" e vírgula decimal — abrem direto no Excel). Cada item abaixo indica qual base usar e o filtro '
            'que leva ao resultado da tela. Todos os downloads (bases e tabelas) seguem o filtro <b>Superintendência</b> do cabeçalho: '
            f'com LAGOS ou LESTE escolhida, só as linhas daquela superintendência vêm no arquivo.</p><ul class="val-bases">{"".join(linhas)}</ul>{dados}')


DESCRICAO_BASES = {
    "fatura": "Uma linha por ligação × rubrica (VALOR DE AGUA / VALOR DE ESGOTO) × mês, já cruzada com o consumo (Consumo Faturado, "
              "economias) e o cronograma (Qts. Dias), só grupos até o último faturado. Alimenta Resumo, Diretas e o realizado das diretas na DRE.",
    "fatura_mensal": "Soma por mês, grupo, serviço e superintendência (valor, volume e economias só onde Consumo Faturado &gt; 0), "
                     "com todos os meses e grupos. Alimenta o orçado por ciclo e o forecast das diretas.",
    "avulso": "Lançamentos do serviço avulso com a classe da rubrica (CORTE, RELIGAÇÃO, LNA, SANÇÃO, OUTROS, LNE). Alimenta a aba Indiretas, "
              "as linhas RI da DRE e o forecast das indiretas.",
    "cancelamento": "Linhas da fatura com rubricas de cancelamento. Alimenta a linha Cancelamento da DRE e do forecast.",
    "orcado": "Planilhas de orçado no formato longo (uma linha por planilha × Sup × rubrica × mês) e a linha da DRE em que cada rubrica entra.",
}


NOME_BASICA = {"dA": "DIRETAS ÁGUA", "dE": "DIRETAS ESGOTO", "ecoA": "Economias de Água", "ecoE": "Economias de Esgoto",
               "volA": "Volume de Água (m³)", "volE": "Volume de Esgoto (m³)", "iE": "Fat. de esgoto - Indireto (LNE)",
               "ri_CORTE": "RI Cortes/Recorte", "ri_RELIGAÇÃO": "RI Religações", "ri_LNA": "RI Ligações - Água",
               "ri_SANÇÃO": "RI Fiscalização", "ri_OUTROS": "RI Outros - Água", "canc": "Cancelamento"}


def _moeda(v):
    return "-" if v is None else "R$ " + fmt_num(v, 2)


def _tab(cab, linhas, classes=None, classe_tabela="tabela-dados"):
    th = "".join(f"<th>{c}</th>" for c in cab)
    corpo = "".join("<tr" + (f' class="{classes[k]}"' if classes and classes[k] else "") + ">"
                    + "".join(f"<td>{c}</td>" for c in l) + "</tr>" for k, l in enumerate(linhas))
    return f'<div class="tabela-wrap"><table class="{classe_tabela}"><thead><tr>{th}</tr></thead><tbody>{corpo}</tbody></table></div>'


def _forecast_geral():
    """Parte da explicação que não depende dos dados: resumo, os três métodos e o passo a passo."""
    resumo = (
        '<div class="fc-formula"><b>Fechamento do mês = Realizado + Forecast</b><br>'
        '<span>Realizado = o que já foi faturado até ontem (D-1) · Forecast = estimativa do que ainda falta faturar até o fim do mês</span></div>')
    metodos = _tab(["Linhas da DRE", "Método", "Fórmula do forecast", "Por que assim"], [
        ["Diretas Água e Esgoto, economias e volume", "<b>1. Grupo × tendência do mês</b>",
         "Para cada grupo que falta: economias × volume por economia × tarifa do próprio grupo (até 6 meses, média ponderada), "
         "corrigidos pelos fatores de tendência dos grupos que já faturaram",
         "As diretas são faturadas por grupo; os grupos já lidos mostram se o mês está caindo ou subindo em economias, consumo e tarifa"],
        ["Indiretas (RI Cortes, Religações, Ligações de água, Fiscalização, Outros e Fat. de esgoto - Indireto)", "<b>2. Ritmo por dia útil</b>",
         "(Realizado ÷ dias úteis decorridos) × dias úteis que faltam",
         "O serviço avulso acontece todo dia útil; Cortes usam só os dias de corte (sem sextas e vésperas de feriado)"],
        ["Cancelamento", "<b>3. Completar até a média</b>",
         "Média dos últimos 3 meses − realizado (zero se o realizado já atingiu a média)",
         "Não tem ritmo diário previsível: espera-se que o mês chegue pelo menos à média"],
        ["Totais, Fat. de água - Indireto, médias, tarifa e ticket", "Calculadas", "Refeitas a partir de Realizado + Forecast das linhas acima",
         "Mantém a DRE coerente: total = soma das partes; médias = razão das somas (não média das médias)"],
    ], classe_tabela="tabela-dados fc-metodos")
    passos = _lista([
        "<b>Data de corte e histórico.</b> A data de corte é ontem (D-1), porque os arquivos são atualizados até o dia anterior. "
        "O histórico das diretas usa até 6 meses anteriores ao mês projetado (cancelamento: até 3).",
        "<b>Grupos faturados × grupos que faltam.</b> Grupos com linhas na fatura do mês já estão no Realizado. Grupos que faturaram "
        "no histórico e ainda não no mês são os que faltam.",
        "<b>Tendência do mês.</b> Compara-se o que os grupos já faturados realizaram com o que o método previa para eles: "
        "fator de economias, de volume por economia e de tarifa (separados para água e esgoto).",
        "<b>Forecast de cada linha.</b> Aplica-se o método da tabela acima (grupo × tendência, ritmo por dia útil ou completar até a média). "
        "As diretas ganham também uma faixa provável (pessimista–otimista).",
        "<b>Conferência do método (backtest).</b> O mesmo cálculo é refeito nos meses passados, como se os últimos grupos ainda não "
        "tivessem faturado, e o erro é comparado com o da média simples.",
        "<b>Linhas calculadas.</b> Diretas Totais, Fat. de água - Indireto, Faturamento Bruto, volume médio, tarifa e ticket são refeitos a partir do fechamento.",
        "<b>Comparação com o orçado.</b> Δ R$ = Fechamento − Orçado; Δ % = Fechamento ÷ Orçado − 1, para cada planilha (RF ou RF SUP).",
        "<b>Ajuste manual (opcional).</b> Na aba Forecast, clique em um valor da coluna Forecast ✎ para trocá-lo; fechamento, totais e Δ "
        "são refeitos na hora e a edição fica salva neste navegador. \"↺ Restaurar automático\" volta ao cálculo.",
    ]).replace("<ul>", '<ol class="fc-passos">').replace("</ul>", "</ol>")
    return (f'<p class="val-rot">Em resumo</p>{resumo}<p class="val-rot">Os três métodos</p>{metodos}'
            f'<p class="val-rot">Passo a passo</p>{passos}')


def _fmt_k(k, v):
    return _moeda(v) if k in ("dA", "dE") else fmt_num(v, 0)


def _explica_forecast(ctx, sup):
    """Memória de cálculo do forecast de uma superintendência, com os números do mês."""
    from .formatacao import nome_mes
    from .previsao import CLASSES_POR_DIA_UTIL, MESES_BASE, MESES_HIST, calcula_previsao
    d = calcula_previsao(ctx, sup)
    if not d:
        return '<p>Sem meses anteriores na base: não há como projetar o fechamento.</p>'
    refs, du, atual, falta = d["refs"], d["dias"], d["atual"], d["falta"]
    corte = d["corte"].strftime("%d/%m/%Y")
    faturados = d["faturados"]

    parametros = _tab(["Parâmetro", "Valor", "De onde vem"], [
        ["Mês projetado", html.escape(ctx.mes_atual), "Última referência com linhas na fatura"],
        ["Histórico das diretas", html.escape(", ".join(nome_mes(r) for r in d["refs_hist"])),
         f"Até {MESES_HIST} meses anteriores ao mês projetado que existem na base (aqui: {len(d['refs_hist'])})"],
        ["Histórico do cancelamento", html.escape(", ".join(nome_mes(r) for r in refs)),
         f"Até {MESES_BASE} meses anteriores (aqui: {len(refs)})"],
        ["Data de corte (D-1)", corte, "Arquivos atualizados até ontem: hoje ainda não conta como decorrido"],
        ["Grupos já faturados", html.escape(", ".join(faturados) or "nenhum"), "Têm linhas na fatura do mês: já estão no Realizado"],
        ["Grupos que faltam", html.escape(", ".join(d["faltam"]) or "nenhum"), "Faturaram no histórico e ainda não no mês"],
        ["Dias úteis do mês", f"{du['uteis']} (decorridos {du['uteis_decorridos']}, faltam {du['uteis_faltam']})",
         "Seg. a sex., sem feriados nacionais, Sexta-feira Santa, São Jorge (23/04) e feriados_extras de regras.json; pontos facultativos contam como úteis"],
        ["Dias de corte", f"{du['corte']} (decorridos {du['corte_decorridos']}, faltam {du['corte_faltam']})",
         "Dias úteis sem as sextas-feiras e sem as vésperas de feriado"],
    ])

    # método 1
    proj, refs_h = d["projecao"], d["refs_hist"]
    nomes_s = {"A": "Água", "E": "Esgoto"}
    pct = lambda f: ("+" if f >= 1 else "−") + fmt_num(abs(f - 1) * 100, 1) + "%"
    linhas_f = []
    for s in ("A", "E"):
        f = proj["fatores"].get(s)
        if not f:
            continue
        for k, nome in (("eco", "Economias"), ("vme", "Volume por economia"), ("tar", "Tarifa (R$/m³)")):
            linhas_f.append([nomes_s[s], nome, fmt_num(f["bruto"][k], 4) + f" ({pct(f['bruto'][k])})",
                             fmt_num(f["confianca"] * 100, 0) + "%", f"<b>{fmt_num(f['aplicado'][k], 4)} ({pct(f['aplicado'][k])})</b>"])
    tabela_f = _tab(["Serviço", "Fator", "Medido nos grupos já faturados", "Confiança", "Fator aplicado"], linhas_f)
    linhas_g = []
    for g, info in proj["grupos"].items():
        for s in ("A", "E"):
            x = info.get(s)
            if not x:
                continue
            b = x["base"]
            if b["simples"]:
                linhas_g.append([html.escape(g), nomes_s[s], str(len(info["meses"])), "—", "—", "—",
                                 fmt_num(x["eco"], 0), fmt_num(x["vol"], 0), f"<b>{_moeda(x['valor'])}</b> (média ponderada do valor)"])
            else:
                linhas_g.append([html.escape(g), nomes_s[s], str(len(info["meses"])), fmt_num(b["eco"], 0), fmt_num(b["vme"], 2),
                                 fmt_num(b["tar"], 2), fmt_num(x["eco"], 0), fmt_num(x["vol"], 0), f"<b>{_moeda(x['valor'])}</b>"])
    fx = proj["faixa"]
    linhas_fx = [[NOME_BASICA[k], _fmt_k(k, fx[k][0]), f"<b>{_fmt_k(k, falta[k])}</b>", _fmt_k(k, fx[k][1]),
                  _fmt_k(k, (atual.get(k) or 0) + fx[k][0]) + " – " + _fmt_k(k, (atual.get(k) or 0) + fx[k][1])]
                 for k in ("dA", "dE", "ecoA", "ecoE", "volA", "volE")]
    if proj["grupos"]:
        g, info = next(iter(proj["grupos"].items()))
        x, fa = info["A"], proj["fatores"]["A"]["aplicado"]
        if x["base"]["simples"]:
            exemplo = (f'<p class="fc-exemplo"><b>Exemplo — grupo {html.escape(g)}, Água:</b> sem economias/volume no histórico; '
                       f'entra a média ponderada do valor: <b>{_moeda(x["valor"])}</b>.</p>')
        else:
            b = x["base"]
            exemplo = (
                f'<p class="fc-exemplo"><b>Exemplo — grupo {html.escape(g)}, Água:</b> '
                f'economias = {fmt_num(b["eco"], 0)} (média ponderada) × {fmt_num(fa["eco"], 4)} = <b>{fmt_num(x["eco"], 0)}</b>; '
                f'volume = {fmt_num(x["eco"], 0)} × {fmt_num(b["vme"], 2)} m³/economia × {fmt_num(fa["vme"], 4)} = <b>{fmt_num(x["vol"], 0)} m³</b>; '
                f'faturamento = {fmt_num(x["vol"], 0)} m³ × R$ {fmt_num(b["tar"], 2)}/m³ × {fmt_num(fa["tar"], 4)} = <b>{_moeda(x["valor"])}</b>.</p>')
        corpo1 = (
            "<p><b>1º — Base de cada grupo</b> (do próprio histórico, separada para água e esgoto): economias, volume por economia "
            "(volume ÷ economias) e tarifa (valor ÷ volume), cada um pela média ponderada dos meses — o mais antigo pesa 1 e o mais "
            "recente pesa " + str(len(refs_h)) + ", então os meses recentes contam mais.</p>"
            "<p><b>2º — Tendência do mês</b>: nos grupos que já faturaram, compara-se o realizado com o que essa base previa para eles. "
            "Fator de economias = economias reais ÷ economias-base; fator de volume = volume real ÷ (economias reais × volume por economia-base); "
            "fator de tarifa = valor real ÷ (volume real × tarifa-base), que capta um reajuste de tarifa no mês. No começo do mês há poucos grupos, então o fator é puxado para 1 "
            "conforme a <b>confiança</b> (parte das economias-base que já faturou): fator aplicado = 1 + confiança × (fator medido − 1).</p>"
            + tabela_f +
            "<p><b>3º — Forecast do grupo</b> = economias-base × fator de economias × volume por economia × fator de volume × tarifa × fator de tarifa.</p>"
            + exemplo
            + _tab(["Grupo", "Serviço", "Meses", "Economias-base", "m³/economia", "Tarifa R$/m³", "Economias prev.", "Volume prev. (m³)", "Faturamento prev."], linhas_g)
            + "<p><b>4º — Faixa provável (~80%)</b>: usa a oscilação histórica de cada grupo (desvio padrão ÷ média) aplicada à previsão. "
            "Pessimista = forecast − 1,28 × desvio combinado; otimista = forecast + 1,28 × desvio combinado.</p>"
            + _tab(["Linha", "Forecast pessimista", "Forecast", "Forecast otimista", "Fechamento provável"], linhas_fx))
    else:
        corpo1 = '<p>Todos os grupos já faturaram: o forecast de diretas, economias e volume é zero.</p>'
    bt = d["backtest"]
    if bt:
        linhas_bt, erros = [], {"novo": [], "antigo": []}
        for l in bt:
            for c, nome in (("dA", "Água"), ("dE", "Esgoto")):
                en, ea = l["erro_novo"][c], l["erro_antigo"][c]
                if en is not None:
                    erros["novo"].append(abs(en)); erros["antigo"].append(abs(ea))
                fmt_e = lambda e: "—" if e is None else ("+" if e >= 0 else "−") + fmt_num(abs(e) * 100, 1) + "%"
                linhas_bt.append([nome_mes(l["mes"]), html.escape(", ".join(l["faltam"])), nome, _moeda(l["real"][c]),
                                  _moeda(l["novo"][c]), fmt_e(en), _moeda(l["antigo"][c]), fmt_e(ea)])
        mn = sum(erros["novo"]) / len(erros["novo"]) if erros["novo"] else None
        ma = sum(erros["antigo"]) / len(erros["antigo"]) if erros["antigo"] else None
        resumo_bt = ("" if mn is None else
                     f'<p class="fc-exemplo">Erro médio absoluto: <b>método atual {fmt_num(mn * 100, 1)}%</b> × média simples de 3 meses '
                     f'{fmt_num(ma * 100, 1)}%. Quanto menor, melhor.</p>')
        corpo_bt = ("<p>Para conferir o método, cada mês do histórico é refeito como se os últimos grupos ainda não tivessem faturado "
                    "(mesma quantidade de grupos que falta agora), usando só os meses anteriores a ele. A previsão é comparada com o que "
                    "esses grupos realmente faturaram.</p>" + resumo_bt
                    + _tab(["Mês testado", "Grupos simulados como faltantes", "Serviço", "Real", "Método atual", "Erro",
                            "Média simples 3 meses", "Erro"], linhas_bt))
    else:
        corpo_bt = "<p>Histórico insuficiente para o backtest (são necessários pelo menos 3 meses na base).</p>"

    # método 2
    linhas_i = []
    for k in CLASSES_POR_DIA_UTIL:
        tipo = "corte" if k == "ri_CORTE" else "uteis"
        dec, fal = du[tipo + "_decorridos"], du[tipo + "_faltam"]
        real = atual.get(k) or 0.0
        linhas_i.append([NOME_BASICA[k], _moeda(real), str(dec), _moeda(real / dec if dec else 0.0), str(fal),
                         f"<b>{_moeda(falta[k])}</b>", _moeda(real + falta[k]), "dias de corte" if tipo == "corte" else "dias úteis"])
    k0 = "ri_RELIGAÇÃO"
    r0, d0, f0 = atual.get(k0) or 0.0, du["uteis_decorridos"], du["uteis_faltam"]
    corpo2 = (f'<p class="fc-exemplo"><b>Exemplo — RI Religações:</b> {_moeda(r0)} ÷ {d0} dias úteis decorridos = '
              f'{_moeda(r0 / d0 if d0 else 0)} por dia; × {f0} dias úteis que faltam = <b>{_moeda(falta[k0])}</b>.</p>'
              + _tab(["Linha", "Realizado até D-1", "Dias decorridos", "Ritmo por dia", "Dias que faltam", "Forecast", "Fechamento", "Calendário"], linhas_i))

    # método 3
    med, rc = d["medias"].get("canc", 0.0), atual.get("canc") or 0.0
    hist = " + ".join(_moeda(d["meses"][r].get("canc") or 0) for r in refs)
    corpo3 = (f'<p class="fc-exemplo">Média = ({hist}) ÷ {len(refs)} = {_moeda(med)}. Forecast = {_moeda(med)} − {_moeda(rc)} '
              f'= <b>{_moeda(falta.get("canc"))}</b> (zero se o realizado já atingiu a média).</p>')

    df = _forecast_df(ctx, sup, d)
    abas = {"Forecast": df}
    if proj["grupos"]:
        abas["Grupos que faltam"] = pd.DataFrame(
            [{"Grupo": g, "Serviço": nomes_s[s], "Meses usados": ", ".join(i["meses"]),
              "Economias-base": i[s]["base"]["eco"], "m3 por economia": i[s]["base"]["vme"], "Tarifa R$/m3": i[s]["base"]["tar"],
              "Economias prev.": i[s]["eco"], "Volume prev.": i[s]["vol"], "Faturamento prev.": i[s]["valor"]}
             for g, i in proj["grupos"].items() for s in ("A", "E") if s in i])
        abas["Fatores de tendencia"] = pd.DataFrame(
            [{"Serviço": nomes_s[s], "Fator": k, "Medido": f["bruto"][k], "Confiança": f["confianca"], "Aplicado": f["aplicado"][k]}
             for s, f in proj["fatores"].items() for k in ("eco", "vme", "tar")])
    if bt:
        abas["Backtest"] = pd.DataFrame([{"Mês": l["mes"], "Grupos": ", ".join(l["faltam"]), "Serviço": c, "Real": l["real"][c],
                                          "Método atual": l["novo"][c], "Erro atual": l["erro_novo"][c],
                                          "Média simples": l["antigo"][c], "Erro média simples": l["erro_antigo"][c]}
                                         for l in bt for c in ("dA", "dE")])
    abas["Indiretas por dia util"] = pd.DataFrame([{
        "Linha": NOME_BASICA[k], "Realizado": atual.get(k) or 0.0,
        "Dias decorridos": du[("corte" if k == "ri_CORTE" else "uteis") + "_decorridos"],
        "Dias que faltam": du[("corte" if k == "ri_CORTE" else "uteis") + "_faltam"], "Forecast": falta[k]} for k in CLASSES_POR_DIA_UTIL])
    abas = {k: v for k, v in abas.items() if v is not None and len(v)}
    slug = "".join(c for c in sup.lower() if c.isalnum())
    botao = botao_download_xlsx("Baixar memória de cálculo (Excel)", f"validacao_forecast_{slug}.xlsx", xlsx_bytes(abas))

    return (f'<p>{botao}</p>'
            f'<h5 class="fc-titulo">A. Parâmetros do mês</h5>{parametros}'
            f'<h5 class="fc-titulo">B. Método 1 — Diretas, economias e volume (grupo × tendência do mês)</h5>{corpo1}'
            f'<h5 class="fc-titulo">B2. Conferência do método 1 nos meses anteriores (backtest)</h5>{corpo_bt}'
            f'<h5 class="fc-titulo">C. Método 2 — Indiretas (ritmo por dia útil)</h5>{corpo2}'
            f'<h5 class="fc-titulo">D. Método 3 — Cancelamento (completar até a média)</h5>{corpo3}'
            f'<h5 class="fc-titulo">E. Resultado: Realizado + Forecast</h5>{_amostra(df, n=40)}')


def _bloco_forecast(ctx):
    """Seção "4. Forecast" da aba Dados: explicação geral + memória de cálculo por superintendência (seletor próprio)."""
    from .dre import _nome_sup, lista_sups
    titulo = f"Forecast de fechamento — como é calculado ({html.escape(ctx.mes_atual)})"
    if getattr(ctx, "base_completa", None) is None:
        return f'<div class="val-bloco"><h4>{titulo}</h4>{_forecast_geral()}</div>'
    sups = lista_sups(ctx)
    e = lambda v: html.escape(v, quote=True)
    opcoes = "".join(f'<option value="{e(s)}">{html.escape(_nome_sup(s))}</option>' for s in sups)
    blocos = "".join(f'<div class="fc-sup" data-fc-sup="{e(s)}"{"" if k == 0 else " hidden"}>{_explica_forecast(ctx, s)}</div>'
                     for k, s in enumerate(sups))
    ra = ctx.ref_atual
    bases = [(ch, filtro) for ch, filtro in (
        ("fatura_mensal", f"histórico (até 6 meses antes de {ra}) e {ra}: valor, volume e economias por Grupo e Serviço"),
        ("avulso", f"Referencia = {ra}; some Valor Parcela por Classe (realizado das indiretas até D-1)"),
        ("cancelamento", "últimos 3 meses e o mês atual; some Valor Parcela por mês"),
        ("orcado", f"Referencia = {ra}: orçado para os Δ")) if ch in BASES]
    lista_bases = ('<p class="val-rot">Bases utilizadas</p><ul class="val-bases">'
                   + "".join(f'<li>{_botao_base(ch)} <span class="val-filtro">{f}</span></li>' for ch, f in bases) + "</ul>") if bases else ""
    return (f'<div class="val-bloco"><h4>{titulo}</h4>{_forecast_geral()}{lista_bases}'
            '<p class="val-rot">Memória de cálculo com os números do mês</p>'
            '<p class="fc-seletor"><label>Superintendência <select onchange="'
            "this.closest('.val-bloco').querySelectorAll('.fc-sup').forEach(b => b.hidden = b.dataset.fcSup !== this.value)"
            f'">{opcoes}</select></label></p>{blocos}</div>')


def _kpis_df(resumo):
    if resumo is None or not len(resumo):
        return None
    s = {c: resumo[c].sum() for c in resumo.columns if c != "Grupo"}
    div = lambda a, b: a / b if b else 0.0
    itens = [
        ("Faturamento Total", s["Fat_Atual"], s["Fat_Anterior"], "Água + Esgoto"),
        ("Faturamento Água", s["FatAgua_Atual"], s["FatAgua_Anterior"], "soma de Valor (R$) da rubrica de água"),
        ("Faturamento Esgoto", s["FatEsgoto_Atual"], s["FatEsgoto_Anterior"], "soma de Valor (R$) da rubrica de esgoto"),
        ("Economias Faturadas", s["Eco_Atual"], s["Eco_Anterior"], "soma, por grupo, do maior valor entre economias de água e de esgoto"),
        ("Volume Faturado (m³)", s["VolFat_Atual"], s["VolFat_Anterior"], "soma do Consumo Faturado de água (Consumo > 0)"),
        ("Tarifa Média (R$/m³)", div(s["Fat_Atual"], s["VolFat_Atual"]), div(s["Fat_Anterior"], s["VolFat_Anterior"]), "(Água + Esgoto) ÷ volume"),
        ("Volume Médio (m³/economia)", div(s["VolFat_Atual"], s["Eco_Atual"]), div(s["VolFat_Anterior"], s["Eco_Anterior"]), "volume ÷ economias"),
        ("Ticket Médio (R$/economia)", div(s["Fat_Atual"], s["Eco_Atual"]), div(s["Fat_Anterior"], s["Eco_Anterior"]), "(Água + Esgoto) ÷ economias"),
    ]
    return pd.DataFrame([{"KPI": k, "Mês atual": a, "Mês anterior": b, "Variação %": (a / b - 1) * 100 if b else None, "Fórmula": f}
                         for k, a, b, f in itens])


def _grafico_df(resumo):
    if resumo is None or not len(resumo):
        return None
    from .config import ALERTA_VARIACAO_GRAFICO
    d = resumo[["Grupo", "Fat_Atual", "Fat_Anterior"]].copy()
    d["Variação %"] = (d["Fat_Atual"] / d["Fat_Anterior"].where(d["Fat_Anterior"] != 0) - 1) * 100
    d["Cor da barra (mês atual)"] = d["Variação %"].map(
        lambda v: "laranja (queda > 40%)" if pd.notna(v) and v < -ALERTA_VARIACAO_GRAFICO * 100
        else "azul médio (alta > 40%)" if pd.notna(v) and v > ALERTA_VARIACAO_GRAFICO * 100 else "azul marinho (normal)")
    return d.rename(columns={"Fat_Atual": "Faturamento mês atual", "Fat_Anterior": "Faturamento mês anterior"})


def _dias_df(resumo):
    if resumo is None or not len(resumo):
        return None
    d = resumo[["Grupo", "Dias_Leitura_Atual", "Dias_Leitura_Anterior"]].copy()
    from .painel_html import media_dias
    d.loc[len(d)] = ["Média (só grupos com leitura no mês)", media_dias(d["Dias_Leitura_Atual"]), media_dias(d["Dias_Leitura_Anterior"])]
    return d


def _destaques_df(ctx, sup=TODAS):
    r = ctx.resultados
    linhas = []
    ciclos = filtra_sup(ctx, r.get("ciclos"), sup)
    if ciclos is not None and len(ciclos):
        for k, nome in (("Cortada", "Ligações cortadas"), ("Ativa", "Ligações ativas")):
            linhas.append({"Card": "Cortes", "Item": nome, "Mês atual": ciclos[k + "_Atual"].sum(), "Mês anterior": ciclos[k + "_Ant"].sum()})
    for serv, comp in (("Água", ctx.comp_agua), ("Esgoto", ctx.comp_esgoto)):
        c = filtra_sup(ctx, comp, sup).assign(Delta=comp["Faturamento_atual"] - comp["Faturamento_anterior"])
        for titulo, asc in (("Crescimento", False), ("Queda", True)):
            for _, x in c.sort_values("Delta", ascending=asc).head(3).iterrows():
                linhas.append({"Card": f"{titulo} — {serv}", "Item": f"Grupo {x['Grupo']}", "Mês atual": x["Faturamento_atual"],
                               "Mês anterior": x["Faturamento_anterior"], "Diferença": x["Delta"]})
    tops = (r.get("top_sup") or {}).get(sup) or (r.get("top_agua"), r.get("top_esgoto"))
    for serv, top in zip(("Água", "Esgoto"), tops[:2]):
        if top is not None and len(top):
            for _, x in top.head(2).iterrows():
                linhas.append({"Card": f"Top 100 — {serv}", "Item": f"{x['Ranking']}ª maior queda: {x['N. Ligação']} (grupo {x['Grupo']})",
                               "Diferença": -x["Queda_Consumo"]})
    return pd.DataFrame(linhas) if linhas else None


def _indiretas_forecast_df(ctx, sup=TODAS):
    """Tabelas da aba Indiretas (uma superintendência, mês atual): financeiro e eventos, com forecast automático."""
    from .previsao import LINHAS_IND_EV, LINHAS_IND_FIN, CLASSE_DA_LINHA, _valor_linha, calcula_previsao, eventos_indiretas
    from .dre import _orcados_do_mes
    d = calcula_previsao(ctx, sup) if getattr(ctx, "base_completa", None) is not None else None
    real = d["atual"] if d else realizado(ctx, sup, ctx.ref_atual)
    falta = dict(d["falta"]) if d else {}
    falta["iA"] = sum(falta.get(k, 0.0) for k in CLASSE_DA_LINHA if k != "iE")
    falta["tot"] = falta["iA"] + falta.get("iE", 0.0)
    fontes, _ = _fontes(ctx)
    ev = eventos_indiretas(ctx, sup, ctx.ref_atual)
    fev = dict(ev["falta"])
    fev["ev_iA"] = sum(fev.get("ev_" + k, 0.0) for k in CLASSE_DA_LINHA if k != "iE")
    fev["ev_tot"] = fev["ev_iA"] + fev.get("ev_iE", 0.0)
    saida = {}
    for nome, defs, r_, f_, orc in (("Financeiro", LINHAS_IND_FIN, real, falta, _orcados_do_mes(ctx, sup, ctx.ref_atual, fontes)),
                                     ("Eventos", LINHAS_IND_EV, ev["real"], fev, ev["orcado"])):
        linhas = []
        for chave, rotulo, *_ in defs:
            r = _valor_linha(r_, chave)
            fc = f_.get(chave, 0.0)
            fech = None if r is None else r + fc
            l = {"Classe": rotulo}
            if nome == "Eventos":
                base = chave[3:]
                l["Ticket médio 3 meses"] = ev["ticket"].get(base)
            l.update({f"Orçado {f}": _valor_linha(orc[f], chave) for f in fontes})
            l.update({"Realizado": r, "Forecast": fc, "Realizado + Forecast": fech})
            for f in fontes:
                o = _valor_linha(orc[f], chave)
                l[f"Δ % vs {f}"] = (fech / o - 1) * 100 if o and fech is not None else None
                l[f"Δ vs {f}"] = fech - o if o is not None and fech is not None else None
            linhas.append(l)
        saida[nome] = pd.DataFrame(linhas)
    return saida


def _evolucao_df(ctx, sup=TODAS):
    from .dre import CLASSES_ORDEM, NOME_CLASSE, _indiretas_mes, prepara
    from .formatacao import nome_mes
    prepara(ctx)
    if ctx.avulso is None or not len(ctx.avulso):
        return None
    meses = sorted(set(ctx.avulso["Referencia"].dropna()), key=lambda r: (r[3:], r[:2]))
    por_mes = {m: _indiretas_mes(ctx, sup, m) for m in meses}
    linhas = [{"Classe": NOME_CLASSE[cl], **{nome_mes(m): por_mes[m][cl][1] for m in meses}} for cl in CLASSES_ORDEM]
    linhas.append({"Classe": "Total", **{nome_mes(m): sum(v[1] for v in por_mes[m].values()) for m in meses}})
    return pd.DataFrame(linhas)


def gera_validacao_html(ctx):
    passo = ctx.progresso.atualiza
    passo(94.5, "Criando aba Dados: bases para download")
    monta_bases(ctx)
    r = ctx.resultados
    mes, ant = html.escape(ctx.mes_atual), html.escape(ctx.mes_anterior)
    ra, rn = ctx.ref_atual, ctx.ref_anterior
    ult = html.escape(str(ctx.ultimo_grupo or "—"))
    fontes, _ = _fontes(ctx)
    fonte_txt = ", ".join(html.escape(f) for f in fontes) or "nenhuma planilha de orçado"
    comum_fatura = ["<b>Grupo</b>, <b>Rubrica</b> (somente VALOR DE AGUA e VALOR DE ESGOTO), <b>Referencia de Leitura</b>",
                    "<b>Valor (R$)</b> = coluna Valor Parcela da fatura",
                    "<b>Consumo Faturado</b> e <b>Economias_Totais</b> (soma das categorias de economia, vindas do arquivo de consumo)"]
    f_atual_ant = f"Referencia de Leitura = {ra} (atual) e {rn} (anterior)"
    f_atual = f"Referencia de Leitura = {ra}"

    # ---------------- 1. DRE ----------------
    passo(95, "Criando aba Dados: explicação da DRE")
    dre = _aba("5. DRE", [_bloco(
        f"Tabela DRE — Realizado × Orçado ({mes})",
        f"o realizado do mês, linha a linha da DRE, contra cada planilha de orçado ({fonte_txt}), com Δ % e Δ R$. "
        "Os números da amostra são de Todas as superintendências; na tela, os filtros Superintendência e Mês escolhem o bloco "
        "(o Excel baixado é o da superintendência escolhida no filtro).",
        ["Diretas Água / Esgoto = soma de Valor (R$) das linhas cuja rubrica contém AGUA / ESGOTO",
         "Economias = soma de Economias_Totais e Volume = soma de Consumo Faturado, só onde Consumo Faturado &gt; 0",
         "Volume médio = volume ÷ economias; Tarifa média = valor ÷ volume; Ticket médio = valor ÷ economias",
         "Indiretas = soma do Valor Parcela do serviço avulso por classe (Corte, Religação, LNA, Sanção, Outros); LNE vai para Fat. de esgoto - Indireto",
         "Diretas Totais = Água + Esgoto; Faturamento Bruto = Diretas + Indiretas; Cancelamento = soma das rubricas de cancelamento",
         "Orçado = valor do mês na planilha (linhas reconhecidas pelo nome da rubrica); Δ R$ = Realizado − Orçado; Δ % = Realizado ÷ Orçado − 1",
         "Superintendência: vem da cidade (Nome da Localidade) pela relação em regras.json; sem cidade → SEM SUP"],
        comum_fatura + ["Serviço avulso: <b>Rubrica</b> (classe), <b>Valor Parcela</b>, <b>Referencia</b>",
                        "Planilhas de orçado: <b>Sup</b>, <b>Rubrica</b> e a coluna do mês"],
        lambda sup: {"DRE": _dre_df(ctx, sup)}, "dre", ctx=ctx,
        bases=[("fatura", f"{f_atual}; some Valor (R$) por Serviço; economias/volume só onde 'Entra em economias/volume' = Sim"),
               ("avulso", f"Referencia = {ra}; some Valor Parcela por Classe"),
               ("cancelamento", f"{f_atual}; some Valor Parcela"),
               ("orcado", f"Referencia = {ra}; some Valor por Planilha e Linha da DRE")],
        montagem=["Uma linha por item da DRE (Faturamento Bruto, Diretas, Indiretas, economias, volumes, médias, cancelamento)",
                  "Colunas: Orçado de cada planilha · Realizado · Δ % e Δ R$ contra cada planilha",
                  "Células de Δ em vermelho quando o realizado está abaixo do orçado (no cancelamento, o sinal é invertido)",
                  "Um bloco pronto por superintendência × mês; os filtros do cabeçalho só mostram o bloco escolhido"])],
        aberto=False)

    # ---------------- 2. Resumo ----------------
    passo(95.5, "Criando aba Dados: explicação do Resumo (KPIs, gráfico, tabelas)")
    rs = lambda sup: filtra_sup(ctx, r.get("resumo"), sup)          # resumo por grupo só com os grupos da SUP
    base_resumo = [("fatura", f"{f_atual_ant}; some por mês (e por Grupo para a tabela e o gráfico)")]
    resumo = _aba("1. Resumo", [
        _bloco(f"KPIs (8 cards) — {mes} × {ant}",
               f"os totais do mês nos grupos já faturados (até o grupo {ult}) e a variação contra os mesmos grupos no mês anterior.",
               ["Cada card soma os grupos da tabela 'Resumo consolidado por grupo'",
                "Economias faturadas = por grupo, o maior valor entre economias de água e de esgoto; depois soma dos grupos",
                "Volume faturado = soma do Consumo Faturado da rubrica de água (só Consumo &gt; 0)",
                "Tarifa, volume médio e ticket = razões das somas (não média das médias)",
                "Variação % = (atual ÷ anterior) − 1; seta ▲/▼ e cor laranja quando cai"],
               comum_fatura, lambda sup: {"KPIs": _kpis_df(rs(sup))}, "kpis", bases=base_resumo, ctx=ctx,
               montagem=["8 cards lado a lado: valor do mês atual em destaque e a variação vs mês anterior embaixo",
                         "O filtro Grupo refaz os cards somando só os grupos marcados"]),
        _bloco(f"Gráfico — Faturamento total por grupo ({mes} × {ant})",
               "barras do faturamento (água + esgoto) de cada grupo nos dois meses.",
               ["Faturamento do grupo = Valor (R$) de água + Valor (R$) de esgoto do grupo no mês",
                "Variação % = atual ÷ anterior − 1, usada só para a cor da barra"],
               comum_fatura, lambda sup: {"Grafico": _grafico_df(rs(sup))}, "grafico_faturamento", bases=base_resumo, ctx=ctx,
               montagem=["Eixo X: grupos; duas barras por grupo — cinza = mês anterior, cor = mês atual",
                         "Cor da barra do mês atual: laranja se caiu mais de 40%, azul médio se subiu mais de 40%, azul marinho nos demais",
                         "Rótulo em cima da barra do mês atual (valor compacto: mil / mi); valor exato ao passar o mouse"]),
        _bloco("Dias de leitura (média)",
               "a média de dias de leitura dos grupos nos dois meses e a diferença.",
               ["Dias de leitura do grupo = média de Qts. Dias (cronograma) das linhas de água e esgoto do grupo",
                "Média = média simples entre os grupos que tiveram leitura no mês (grupo ainda sem leitura não entra como 0); Δ = atual − anterior",
                "Os grupos são os da análise: em cada superintendência, até o último grupo já faturado no mês atual",
                "O filtro Superintendência / Grupo refaz a média só com os grupos marcados"],
               comum_fatura + ["<b>Qts. Dias</b> (cronograma: cruzado por grupo e mês pela Data da Leitura; sem o mês, usa a última linha do grupo)"], lambda sup: {"Dias de leitura": _dias_df(rs(sup))},
               "dias_leitura", ctx=ctx, bases=[("fatura", f"{f_atual_ant}; média de Qts. Dias por Grupo")],
               montagem=["Faixa com os dois meses e o Δ em dias (laranja quando diminui)"]),
        _bloco(f"Destaques do mês — {mes}",
               "um quadro por superintendência (LAGOS, LESTE), cada um com os principais movimentos só daquela SUP: cortes, grupos que "
               "mais cresceram e mais caíram (água e esgoto) e o Top 100. O filtro Superintendência mostra o quadro escolhido.",
               ["Cortes: total de ligações cortadas e ativas (tabela 'Economias faturadas por ciclo — ativas × cortadas') e a diferença vs mês anterior",
                "Crescimento / Queda: os 3 grupos com maior diferença de faturamento (atual − anterior), por serviço",
                "Top 100: as 2 maiores quedas de consumo e o total de clientes com queda"],
               comum_fatura + ["<b>Situacao Ligacao</b>", "<b>N. Ligação</b>"], lambda sup: {"Destaques": _destaques_df(ctx, sup)}, "destaques", ctx=ctx,
               bases=base_resumo,
               montagem=["Um card por tema, com até 3 itens cada"]),
        _bloco("Tabela — Resumo consolidado por grupo",
               "por grupo, faturamento atual e anterior, economias e volume faturado do mês atual — é a base dos KPIs e do gráfico.",
               ["Faturamento = Água + Esgoto; Economias = maior entre água e esgoto; Volume = Consumo Faturado de água (Consumo &gt; 0)",
                "Acima do mínimo vem da tabela de consumo mínimo (Diretas)"],
               comum_fatura, lambda sup: {"Resumo por grupo": rs(sup)}, "resumo", bases=base_resumo, ctx=ctx,
               montagem=["Uma linha por grupo; o filtro Grupo esconde as linhas desmarcadas"]),
    ])

    # ---------------- 3. Diretas ----------------
    passo(96, "Criando aba Dados: explicação das Diretas")
    top = lambda sup: (r.get("top_sup") or {}).get(sup) or (r.get("top_agua"), r.get("top_esgoto"), r.get("aumento_agua"), r.get("aumento_esgoto"))
    base_dir = [("fatura", f"{f_atual_ant}; separe por Serviço e some por Grupo")]
    dir_blocos = [
        _bloco("Tabelas — Comparativo Água / Esgoto Mês a Mês",
               f"por grupo, {mes} × {ant}: faturamento, economias, volume, volume médio, tarifa e ticket, com as diferenças.",
               ["Faturamento = soma de Valor (R$) da rubrica; Economias e Volume só onde Consumo Faturado &gt; 0",
                "Dias de leitura = média de Qts. Dias; Δ = atual − anterior (Δ % sobre o anterior)",
                "Volume médio = volume ÷ economias; Tarifa = faturamento ÷ volume; Ticket = faturamento ÷ economias",
                "Total / Média: somas e razões recalculadas no total (não é média das médias)"],
               comum_fatura + ["<b>Qts. Dias</b>"], lambda sup: {"Agua": filtra_sup(ctx, ctx.comp_agua, sup), "Esgoto": filtra_sup(ctx, ctx.comp_esgoto, sup)},
               "comparativo_mes", ctx=ctx,
               bases=base_dir,
               montagem=["Uma tabela para Água e outra para Esgoto; uma linha por grupo e a linha Total / Média (fundo marinho)",
                         "Pares de colunas mês atual / mês anterior e colunas de Δ; Δ Fat. sem casas decimais",
                         "Valores negativos em laranja; o botão 'Mostrar todas as colunas' exibe dias de leitura e Δ absolutos",
                         "O filtro Grupo esconde linhas e refaz o total"]),
        _bloco("Tabelas — Orçado por ciclo (Água / Esgoto)",
               "o orçado do mês dividido pelos grupos de leitura, contra o realizado de cada grupo. O seletor \"comparar com\" escolhe a planilha.",
               ["Cada métrica tem o seu peso por ciclo, separado para água e para esgoto (média dos últimos 3 meses da participação do grupo no total do mês)",
                "Peso do faturamento = valor do grupo ÷ valor total do mês → Orçado Diretas do ciclo = peso × orçado Diretas Água (ou Esgoto)",
                "Peso do volume = volume do grupo ÷ volume total (Consumo &gt; 0) → Orçado Volume do ciclo = peso × orçado Volume",
                "Peso das economias = economias do grupo ÷ economias totais (Consumo &gt; 0) → Orçado Economias do ciclo = peso × orçado Economias",
                "Volume médio, tarifa e ticket orçados = razões dos orçados do ciclo"],
               comum_fatura + ["Planilhas de orçado (linhas Diretas Água/Esgoto, Volume e Economias faturadas)"],
               lambda sup, o=_orcado_ciclo_dfs(ctx): {k: filtra_sup(ctx, v, sup) for k, v in o.items()}, "orcado_ciclo", ctx=ctx,
               bases=[("fatura_mensal", "os 3 meses antes do atual: participação de cada Grupo no total do mês, por Serviço; média dos 3"),
                      ("fatura", f"{f_atual}: realizado por Grupo"),
                      ("orcado", f"Referencia = {ra}; Planilha escolhida; linhas DIRETAS, Volume e Economias")],
               montagem=["Mesmo formato do comparativo: Realizado no lugar do mês atual e Orçado no lugar do mês anterior",
                         "Só o par (Água e Esgoto) da planilha escolhida aparece; as outras ficam prontas e escondidas"]),
        _bloco("Tabela — Economias faturadas por ciclo (ativas × cortadas)",
               "quantidade de economias de água por grupo, separadas pela situação da ligação.",
               ["Soma de Economias_Totais por grupo e Situacao Ligacao (ativa/cortada), só rubrica de água e Consumo Faturado &gt; 0"],
               ["<b>Grupo</b>, <b>Situacao Ligacao</b>, <b>Economias_Totais</b>, <b>Rubrica</b>"], lambda sup: {"Ativas x cortadas": filtra_sup(ctx, r.get("ciclos"), sup)},
               "ativas_cortadas", ctx=ctx, bases=[("fatura", f"{f_atual_ant}; Serviço = Água; some economias por Grupo e Situacao Ligacao")],
               montagem=["Uma linha por grupo; colunas ativas e cortadas nos dois meses e a diferença; linha Total"]),
        _bloco("Tabela — Matriz de migração de grupos",
               f"para onde foram, em {mes}, as economias que faturaram em {ant}.",
               ["Cada ligação (N. Ligação) é comparada nos dois meses: grupo anterior × grupo atual; valor = economias",
                "Quem faturou no mês anterior e não no atual entra em 'Sem Faturamento Atual' (lista para baixar na própria tela)"],
               ["<b>N. Ligação</b>, <b>Grupo</b>, <b>Economias_Totais</b>, <b>Consumo Faturado</b>, <b>Referencia de Leitura</b> (rubrica de água)"],
               lambda sup: {"Matriz": filtra_sup(ctx, r.get("matriz"), sup), "Sem faturamento": filtra_sup(ctx, r.get("sem_faturamento"), sup)},
               "matriz", ctx=ctx,
               bases=[("fatura", f"{f_atual_ant}; Serviço = Água; cruze N. Ligação entre os dois meses")],
               montagem=["Linhas = grupo no mês anterior; colunas = grupo no mês atual; diagonal = permaneceu no grupo",
                         "Cores destacam desvios fora da diagonal; coluna e linha de totais"]),
        _bloco("Tabela — Economias acima × abaixo do consumo mínimo",
               "compara o consumo faturado de cada ligação com o mínimo da sua categoria.",
               ["Mínimo da matrícula = consumo mínimo da categoria × quantidade de economias (ligação mista soma cada tipo)",
                "Acima = consumo faturado maior que o mínimo; Abaixo = igual ou menor", "Diferença = mês atual − mês anterior"],
               ["<b>Categoria</b>, <b>Consumo Faturado</b>, quantidades de economia por tipo (Qtd. Economia …), <b>Grupo</b>"],
               lambda sup: {"Minimo": filtra_sup(ctx, r.get("minimo"), sup)}, "minimo", ctx=ctx,
               bases=[("fatura", f"{f_atual_ant}; Serviço = Água; compare Consumo Faturado com o mínimo da Categoria (regras.json)")],
               montagem=["Uma linha por grupo: acima e abaixo nos dois meses e as diferenças; linha Total"]),
        _bloco("Cards — Situação de lançamento",
               "um card por código da coluna Situacao Lancamento da fatura de ciclo (como o consumo da conta foi apurado: leitura real, "
               "média, mínimo, estimado...), com ligações, participação, volume, valor e o motivo para analisar cada situação.",
               ["Uma ligação por linha da rubrica de água; a situação é a da conta no mês (a primeira, se houver mais de uma)",
                "Ligações = quantidade de ligações na situação; % = ligações da situação ÷ total de ligações do mês; Δ p.p. = % atual − % anterior",
                "Volume e economias = soma de Consumo Faturado e Economias_Totais só onde Consumo Faturado &gt; 0; Vol./economia = volume ÷ economias",
                "Valor = Valor (R$) de água + esgoto da ligação; Δ valor = atual − anterior",
                "Leitura da situação e 'Por que analisar' vêm de palavras-chave no código (MEDIA, MINIMO, ESTIMADO, NORMAL, CANCEL...); "
                "código sem palavra conhecida recebe a explicação genérica"],
               comum_fatura + ["<b>Situacao Lancamento</b> (fatura de ciclo; se só o consumo tiver, usa a do consumo)", "<b>N. Ligação</b>"],
               lambda sup: {"Situacao Lancamento": (r.get("situacao_lancamento") or {}).get(sup)}, "situacao_lancamento", ctx=ctx,
               bases=[("fatura", f"{f_atual_ant}; Serviço = Água: conte N. Ligação por Situacao Lancamento; some volume/valor")],
               montagem=["Um card por situação, da mais frequente para a menos frequente",
                         "A seta ⬇ ao lado do código baixa (CSV) as ligações do mês atual nessa situação — da SUP do quadro —, "
                         "com a situação do mês anterior, volume e valor dos dois meses",
                         "Variações em azul quando sobem e em laranja quando caem; o filtro Superintendência mostra o quadro da SUP"]),
        _bloco("Tabelas — Top 100 clientes com maior queda de consumo (Água / Esgoto)",
               "as ligações que consumiam no mês anterior e consumiram menos no atual.",
               ["Queda de consumo = consumo anterior − consumo atual (só quedas positivas); Queda % = queda ÷ anterior",
                "Queda de valor = valor anterior − valor atual; ordenado pela maior queda de consumo, 100 primeiros"],
               ["<b>N. Ligação</b>, <b>Nome Cliente</b>, <b>Grupo</b>, <b>Categoria</b>, <b>Consumo Faturado</b>, <b>Valor (R$)</b>"],
               lambda sup: dict(zip(("Top100 Agua", "Top100 Esgoto"), top(sup)[:2])), "top100", ctx=ctx,
               bases=[("fatura", f"{f_atual_ant}; por Serviço, some Consumo Faturado e Valor por N. Ligação e compare os meses")],
               montagem=["Uma linha por ligação, do 1º ao 100º; Queda % em laranja quando ≥ o limite de destaque",
                         "Mostra 15 linhas e o botão 'Mostrar todos'; o Excel completo está no botão da tabela"]),
        _bloco("Tabelas — Top 100 clientes com maior aumento de consumo (Água / Esgoto)",
               "as ligações que faturaram nos dois meses e consumiram mais no atual.",
               ["Aumento de consumo = consumo atual − consumo anterior (só aumentos positivos); Aumento % = aumento ÷ anterior (vazio se o anterior era 0)",
                "Aumento de valor = valor atual − valor anterior; ordenado pelo maior aumento de consumo, 100 primeiros"],
               ["<b>N. Ligação</b>, <b>Nome Cliente</b>, <b>Grupo</b>, <b>Categoria</b>, <b>Consumo Faturado</b>, <b>Valor (R$)</b>"],
               lambda sup: dict(zip(("Top100 Aumento Agua", "Top100 Aumento Esgoto"), top(sup)[2:])), "top100_aumento", ctx=ctx,
               bases=[("fatura", f"{f_atual_ant}; por Serviço, some Consumo Faturado e Valor por N. Ligação e compare os meses")],
               montagem=["Uma linha por ligação; Aumento % em azul quando ≥ o limite de destaque; botão para baixar os dois rankings"]),
    ]

    # ---------------- 4. Indiretas ----------------
    passo(96.5, "Criando aba Dados: explicação das Indiretas")
    base_av = ("avulso", "Referencia = mês; some Valor Parcela (e conte as linhas) por Classe")
    ind_cache = {}
    ind_dfs = lambda sup: ind_cache.get(sup) or ind_cache.setdefault(sup, _indiretas_forecast_df(ctx, sup))
    calc_comum = ["Forecast (mês atual) = o mesmo da aba Forecast: realizado até D-1 ÷ dias úteis decorridos × dias úteis que faltam; "
                  "Cortes pelos dias de corte (sem sextas e vésperas de feriado)",
                  "Fat. de água - Indireto = soma das aberturas RI; Total indiretas = água + esgoto (realizado, forecast e orçado)",
                  "Realizado + Forecast = fechamento projetado; Δ % = fechamento ÷ orçado − 1; Δ = fechamento − orçado",
                  "Meses anteriores (mês fechado): sem forecast; o fechamento é o próprio realizado"]
    montagem_comum = ["Linhas: Fat. de água - Indireto (negrito), aberturas RI recuadas, Fat. de esgoto - Indireto (LNE) e Total indiretas",
                      "Forecast editável no mês atual: clique, digite e Enter; \"↺ Restaurar automático\" volta ao cálculo",
                      "Δ em vermelho quando o fechamento fica abaixo do orçado"]
    indiretas = _aba("3. Indiretas", [
        _bloco(f"Tabela — Indiretas: financeiro em R$ ({mes})",
               "por classe, o orçado de cada planilha (RF e RF SUP), o realizado em R$, o forecast, o fechamento e as diferenças.",
               ["Realizado = soma do Valor Parcela do serviço avulso por classe no mês, até D-1",
                "Orçado = linhas do RF pelos nomes CORTE, RELIGAÇÃO, LNA, SANÇÃO, OUTROS (ou RI Cortes/Recorte etc.)"] + calc_comum,
               ["Serviço avulso: <b>Rubrica</b> (classe), <b>Valor Parcela</b>, <b>Referencia</b>", "Orçado: <b>Sup</b>, <b>Rubrica</b>, coluna do mês"],
               lambda sup: {"Financeiro": ind_dfs(sup)["Financeiro"]}, "indiretas_financeiro", ctx=ctx,
               bases=[base_av, ("orcado", f"Referencia = {ra}; linhas RI / CORTE / RELIGAÇÃO / LNA / SANÇÃO / OUTROS")],
               montagem=["Colunas: Classe · Orçado de cada planilha · Realizado · Forecast ✎ · Realizado + Forecast · Δ % e Δ R$ contra cada planilha",
                         "A edição do forecast é a mesma da aba Forecast (mudou numa, muda na outra)"] + montagem_comum),
        _bloco(f"Tabela — Indiretas: eventos faturados ({mes})",
               "por classe, a quantidade de eventos (lançamentos do serviço avulso): orçado em eventos de cada planilha, realizado, "
               "forecast, fechamento e as diferenças.",
               ["Realizado = quantidade de lançamentos do serviço avulso por classe no mês, até D-1",
                f"Ticket médio da classe = valor ÷ lançamentos dos {3} meses fechados anteriores ao mês",
                "Orçado em eventos = orçado em R$ da classe ÷ ticket médio da classe (sem ticket no histórico → sem orçado)"] + calc_comum,
               ["Serviço avulso: <b>Rubrica</b> (classe), <b>Valor Parcela</b>, <b>Referencia</b> (contagem de linhas)",
                "Orçado: <b>Sup</b>, <b>Rubrica</b>, coluna do mês"],
               lambda sup: {"Eventos": ind_dfs(sup)["Eventos"]}, "indiretas_eventos", ctx=ctx,
               bases=[("avulso", "Referencia = mês: conte as linhas por Classe; 3 meses anteriores: some Valor Parcela ÷ linhas = ticket"),
                      ("orcado", f"Referencia = {ra}; orçado da classe ÷ ticket")],
               montagem=["Colunas: Classe · Ticket médio 3 meses · Orçado (eventos) de cada planilha · Realizado · Forecast ✎ · "
                         "Realizado + Forecast · Δ % e Δ (eventos) contra cada planilha"] + montagem_comum),
        _bloco("Gráfico — Evolução mensal por classe",
               "o valor do serviço avulso por classe em cada mês do arquivo, no fim da aba (abaixo das duas tabelas).",
               ["Para cada mês e classe: soma do Valor Parcela (rubricas marcadas para excluir ficam de fora)",
                "Total = soma das classes no mês"],
               ["Serviço avulso: <b>Rubrica</b> (classe), <b>Valor Parcela</b>, <b>Referencia</b>"],
               lambda sup: {"Evolucao": _evolucao_df(ctx, sup)}, "evolucao_indiretas", bases=[base_av], ctx=ctx,
               montagem=["Barras empilhadas, largura inteira: uma barra por mês, uma cor por classe; valor de cada faixa dentro dela e total em cima"]),
    ])

    passo(97, "Criando aba Dados: memória de cálculo do Forecast")
    forecast = _aba("4. Forecast", [_bloco_forecast(ctx)])

    # cada tópico é recolhível (fechado ao abrir a aba); quem monta o cartão da aba Dados é dados.py
    return (_aba("Bases para download", [f'<div class="val-bloco">{_secao_bases(ctx)}</div>'])
            + resumo + _aba("2. Diretas", dir_blocos) + indiretas + forecast + dre)
