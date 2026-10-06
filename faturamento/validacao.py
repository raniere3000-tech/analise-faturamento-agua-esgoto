# -*- coding: utf-8 -*-
"""Aba Dados — "Validação dos cálculos": descreve, aba por aba (na ordem de navegação), como cada tabela é calculada,
quais colunas dos arquivos entram, mostra uma amostra do resultado e permite baixar o resultado inteiro em Excel."""
import html

import pandas as pd

from .config import CHAVES_CANCELAMENTO
from .dre import LINHAS, TODAS, _fontes, orcado, realizado
from .formatacao import fmt_num
from .tabelas_html import botao_download_xlsx, xlsx_bytes

LIMITE_BASE = 50000
COLUNAS_BASE = ["N. Ligação", "Grupo", "Rubrica", "Referencia de Leitura", "Valor (R$)", "Consumo Faturado", "Economias_Totais",
                "Qts. Dias", "Situacao Ligacao", "Categoria", "Cidade"]


def _amostra(df, n=6):
    if df is None or not len(df):
        return '<p class="nota-secao">Sem dados para amostra.</p>'
    d = df.head(n)
    cab = "".join(f"<th>{html.escape(str(c))}</th>" for c in d.columns)
    def cel(v):
        if isinstance(v, float):
            return fmt_num(v, 2)
        return html.escape("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))
    corpo = "".join("<tr>" + "".join(f"<td>{cel(v)}</td>" for v in linha) + "</tr>" for linha in d.itertuples(index=False))
    return (f'<div class="tabela-wrap"><table class="tabela-dados"><thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table></div>'
            f'<p class="nota-secao">Amostra: {len(d)} de {len(df)} linha(s).</p>')


def _lista(itens):
    return "<ul>" + "".join(f"<li>{i}</li>" for i in itens) + "</ul>"


def _bloco(titulo, descricao, formulas, colunas, abas, slug):
    """abas: {nome: DataFrame}; a primeira é a que aparece como amostra."""
    abas = {k: v for k, v in abas.items() if v is not None and len(v)}
    primeira = next(iter(abas.values()), None)
    botao = botao_download_xlsx("Baixar para validar (Excel)", f"validacao_{slug}.xlsx", xlsx_bytes(abas)) if abas else ""
    return (f'<div class="val-bloco"><h4>{html.escape(titulo)} {botao}</h4><p>{descricao}</p>'
            f'<p class="val-rot">Cálculo</p>{_lista(formulas)}<p class="val-rot">Colunas utilizadas</p>{_lista(colunas)}'
            f'<p class="val-rot">Amostra do resultado</p>{_amostra(primeira)}</div>')


def _aba(titulo, blocos, aberto=False):
    return f'<details class="val-aba"{" open" if aberto else ""}><summary>{html.escape(titulo)}</summary>{"".join(blocos)}</details>'


def _dre_df(ctx):
    fontes, _ = _fontes(ctx)
    real = realizado(ctx, TODAS, ctx.ref_atual)
    orc = {f: orcado(ctx, f, TODAS, ctx.ref_atual) for f in fontes}
    linhas = []
    for chave, rotulo, formato, negrito in LINHAS:
        if chave is None:
            continue
        r = {"Rubrica": rotulo, "Realizado": real.get(chave)}
        for f in fontes:
            o = orc[f].get(chave)
            r[f"Orçado {f}"] = o
            r[f"Δ R$ vs {f}"] = None if o is None or r["Realizado"] is None else r["Realizado"] - o
            r[f"Δ % vs {f}"] = None if not o or r["Realizado"] is None else r["Realizado"] / o - 1
        linhas.append(r)
    return pd.DataFrame(linhas)


def _indiretas_df(ctx):
    d = _dre_df(ctx)
    chaves = {rot for ch, rot, _, _ in LINHAS if ch in ("ri_CORTE", "ri_RELIGAÇÃO", "ri_LNA", "ri_SANÇÃO", "ri_OUTROS", "iA", "iE")}
    return d[d["Rubrica"].isin(chaves)].reset_index(drop=True)


def _forecast_df(ctx):
    from .previsao import calcula_previsao
    dados = calcula_previsao(ctx, TODAS)
    if not dados:
        return None
    linhas = []
    for chave, rotulo, formato, negrito in LINHAS:
        if chave is None or dados["atual"].get(chave) is None:
            continue
        real = dados["atual"].get(chave)
        fc = dados["falta"].get(chave)
        linhas.append({"Rubrica": rotulo, "Realizado": real, "Forecast": fc, "Realizado + Forecast": None if fc is None else real + fc})
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


def _base_utilizada(ctx):
    base = ctx.base_final
    b = base[base["Referencia de Leitura"].isin([ctx.ref_atual, ctx.ref_anterior])]
    cols = [c for c in COLUNAS_BASE if c in b.columns]
    b = b[cols]
    truncada = len(b) > LIMITE_BASE
    abas = {"Fatura (agua+esgoto)": b.head(LIMITE_BASE)}
    if ctx.avulso is not None and len(ctx.avulso):
        abas["Servico avulso"] = ctx.avulso.drop(columns=[c for c in ctx.avulso.columns if c.startswith("__")], errors="ignore").head(LIMITE_BASE)
    if ctx.cancelamento is not None and len(ctx.cancelamento):
        abas["Cancelamento"] = ctx.cancelamento.head(LIMITE_BASE)
    botao = botao_download_xlsx("Baixar base utilizada (Excel)", "validacao_base_utilizada.xlsx", xlsx_bytes(abas))
    aviso = f" Limitado às primeiras {fmt_num(LIMITE_BASE)} linhas de cada aba." if truncada else ""
    return (f'<p>A base abaixo são as linhas que alimentam todos os cálculos (últimas duas referências, grupos até o '
            f'{html.escape(str(ctx.ultimo_grupo or "—"))}).{aviso} {botao}</p>')


def gera_validacao_html(ctx):
    r = ctx.resultados
    mes, ant = html.escape(ctx.mes_atual), html.escape(ctx.mes_anterior)
    fontes, _ = _fontes(ctx)
    fonte_txt = ", ".join(html.escape(f) for f in fontes) or "nenhuma planilha de orçado"
    comum_fatura = ["<b>Grupo</b>, <b>Rubrica</b> (somente VALOR DE AGUA e VALOR DE ESGOTO), <b>Referencia de Leitura</b>",
                    "<b>Valor (R$)</b> = coluna Valor Parcela da fatura", "<b>Consumo Faturado</b> e <b>Economias_Totais</b> (soma das categorias de economia, vindas do arquivo de consumo)"]

    dre = _aba("1. DRE", [_bloco(
        f"DRE — Realizado × Orçado ({mes})",
        f"Compara o realizado do mês com cada planilha de orçado ({fonte_txt}). Os valores abaixo são de Todas as superintendências; "
        "a tela permite filtrar por superintendência (a cidade do cliente define a SUP).",
        ["Diretas Água / Esgoto = soma de Valor (R$) das linhas cuja rubrica contém AGUA / ESGOTO",
         "Economias = soma de Economias_Totais e Volume = soma de Consumo Faturado, só onde Consumo Faturado &gt; 0",
         "Volume médio = volume ÷ economias; Tarifa média = valor ÷ volume; Ticket médio = valor ÷ economias",
         "Indiretas = soma do Valor Parcela do serviço avulso por classe (Corte, Religação, LNA, Sanção, Outros); LNE vai para Fat. de esgoto - Indireto",
         "Faturamento Bruto = Diretas + Indiretas; Cancelamento = soma das rubricas de cancelamento",
         "Orçado = valor do mês na planilha (linhas reconhecidas pelo nome da rubrica); Δ R$ = Realizado − Orçado; Δ % = Realizado ÷ Orçado − 1"],
        comum_fatura + ["Serviço avulso: <b>Rubrica</b> (classe), <b>Valor Parcela</b>, <b>Referencia de Leitura</b>",
                        "Planilhas de orçado: <b>Sup</b>, <b>Rubrica</b> e a coluna do mês"],
        {"DRE": _dre_df(ctx)}, "dre")], aberto=True)

    resumo = _aba("2. Resumo", [_bloco(
        f"KPIs, gráfico e tabela por grupo — {mes} × {ant}",
        "Os cards, o gráfico de barras por grupo e a tabela de dados somam os grupos já faturados na última referência "
        f"(até o grupo {html.escape(str(ctx.ultimo_grupo or '—'))}) e comparam com os mesmos grupos do mês anterior.",
        ["Faturamento Total = Água + Esgoto; Água e Esgoto = soma de Valor (R$) das rubricas de cada um",
         "Economias faturadas = maior valor entre as economias de água e de esgoto do grupo (soma entre grupos)",
         "Volume faturado = soma do Consumo Faturado de água; Tarifa média = (Água + Esgoto) ÷ volume",
         "Volume médio = volume ÷ economias; Ticket médio = (Água + Esgoto) ÷ economias",
         "Acima do mínimo = economias com consumo acima do mínimo da categoria (ver Diretas)",
         "Variação % = (atual − anterior) ÷ anterior; barras laranja = queda acima de 40%, azul = alta acima de 40%"],
        comum_fatura + ["<b>Qts. Dias</b> (dias de leitura, vindo do cronograma)"],
        {"Resumo por grupo": r.get("resumo")}, "resumo")])

    dir_blocos = [
        _bloco("Comparativo Água / Esgoto Mês a Mês",
               f"Por grupo, {mes} × {ant}: faturamento, economias, volume, volume médio, tarifa e ticket.",
               ["Faturamento = soma de Valor (R$) da rubrica; Economias e Volume só onde Consumo Faturado &gt; 0",
                "Dias de leitura = média de Qts. Dias; Δ = atual − anterior (Δ % sobre o anterior)",
                "Total / Média: somas e razões recalculadas no total (não é média das médias)"],
               comum_fatura + ["<b>Qts. Dias</b>"], {"Agua": ctx.comp_agua, "Esgoto": ctx.comp_esgoto}, "comparativo_mes"),
        _bloco("Orçado por ciclo (Água / Esgoto × RF e SUP)",
               "Orçado de cada ciclo (grupo) = peso do ciclo × orçado total do mês. As colunas *_realizado/*_orcado seguem o mesmo formato do comparativo.",
               ["Peso do ciclo = média, nos últimos 3 meses, de (valor de água ou esgoto do grupo ÷ total do mês)",
                "Orçado Diretas, Volume e Economias do ciclo = peso × orçado da DRE (linhas Diretas, Volume e Economias)",
                "Volume médio, tarifa e ticket orçados = razões dos orçados do ciclo"],
               comum_fatura + ["Planilhas de orçado (linhas Diretas Água/Esgoto, Volume e Economias faturadas)"],
               _orcado_ciclo_dfs(ctx), "orcado_ciclo"),
        _bloco("Economias faturadas por ciclo — ativas × cortadas",
               "Quantidade de economias de água por grupo, separadas pela situação da ligação.",
               ["Soma de Economias_Totais por grupo e Situacao Ligacao (ativa/cortada), só rubrica de água e Consumo Faturado &gt; 0"],
               ["<b>Grupo</b>, <b>Situacao Ligacao</b>, <b>Economias_Totais</b>, <b>Rubrica</b>"], {"Ativas x cortadas": r.get("ciclos")}, "ativas_cortadas"),
        _bloco("Matriz de migração de grupos",
               f"Para onde foram, em {mes}, as economias que faturaram em {ant}.",
               ["Cada ligação (N. Ligação) é comparada nos dois meses: grupo anterior × grupo atual; valor = economias",
                "Quem faturou no mês anterior e não no atual entra em 'Sem Faturamento Atual' (lista para baixar na própria tela)"],
               ["<b>N. Ligação</b>, <b>Grupo</b>, <b>Economias_Totais</b>, <b>Consumo Faturado</b>, <b>Referencia de Leitura</b> (rubrica de água)"],
               {"Matriz": r.get("matriz"), "Sem faturamento": r.get("sem_faturamento")}, "matriz"),
        _bloco("Economias acima × abaixo do consumo mínimo",
               "Compara o consumo faturado de cada ligação com o mínimo da sua categoria.",
               ["Mínimo da matrícula = consumo mínimo da categoria × quantidade de economias (ligação mista soma cada tipo)",
                "Acima = consumo faturado maior que o mínimo; Abaixo = igual ou menor",
                "Diferença = mês atual − mês anterior"],
               ["<b>Categoria</b>, <b>Consumo Faturado</b>, quantidades de economia por tipo, <b>Grupo</b>"], {"Minimo": r.get("minimo")}, "minimo"),
        _bloco("Top 100 clientes com maior queda de consumo",
               "Ligações que consumiam no mês anterior e consumiram menos no atual.",
               ["Queda de consumo = consumo anterior − consumo atual (só quedas positivas); Queda % = queda ÷ anterior",
                "Queda de valor = valor anterior − valor atual; ordenado pela maior queda de consumo, 100 primeiros"],
               ["<b>N. Ligação</b>, <b>Nome Cliente</b>, <b>Grupo</b>, <b>Categoria</b>, <b>Consumo Faturado</b>, <b>Valor (R$)</b>"],
               {"Top100 Agua": r.get("top_agua"), "Top100 Esgoto": r.get("top_esgoto")}, "top100"),
    ]
    indiretas = _aba("4. Indiretas", [_bloco(
        f"Orçado × Realizado das indiretas ({mes})",
        "Cada linha RI compara o serviço avulso executado com a meta do RF / RF SUP.",
        ["Realizado = soma do Valor Parcela do serviço avulso por classe (Cortes/Recorte, Religações, Ligações - Água, Fiscalização, Outros)",
         "Fat. de água - Indireto = soma das classes de água; Fat. de esgoto - Indireto = classe LNE",
         "Orçado = linhas do RF pelos nomes CORTE, RELIGAÇÃO, LNA, SANÇÃO, OUTROS (ou RI Cortes/Recorte etc.)",
         "Δ R$ = Realizado − Orçado; Δ % = Realizado ÷ Orçado − 1"],
        ["Serviço avulso: <b>Rubrica</b> (classe), <b>Valor Parcela</b>, <b>Referencia de Leitura</b>", "Orçado: <b>Sup</b>, <b>Rubrica</b>, coluna do mês"],
        {"Indiretas": _indiretas_df(ctx)}, "indiretas")])

    forecast = _aba("5. Forecast", [_bloco(
        f"Forecast de fechamento ({mes})",
        "Realizado até agora + o que ainda deve ser faturado. A coluna Forecast é editável na tela.",
        ["Diretas, economias e volume: cada grupo que ainda não faturou entra com a média do mesmo grupo nos últimos 3 meses",
         "Indiretas: ticket por dia útil (realizado ÷ dias úteis decorridos até D-1) × dias úteis que faltam; Cortes sem sextas e vésperas de feriado",
         "Cancelamento: média dos últimos 3 meses − realizado (mínimo zero)",
         "Realizado + Forecast = fechamento projetado; comparado com cada orçado (Δ % e Δ R$)"],
        comum_fatura + ["Serviço avulso (<b>Valor Parcela</b>, <b>Rubrica</b>) e feriados do código/regras.json"],
        {"Forecast": _forecast_df(ctx)}, "forecast")])

    return ('<div class="card val-card"><h2>Validação dos cálculos</h2>'
            '<p class="nota-secao">Explicação por aba, na ordem em que você navega. Cada item mostra o cálculo, as colunas utilizadas, uma amostra e um botão para baixar o resultado em Excel e conferir.</p>'
            + _base_utilizada(ctx) + dre + resumo
            + _aba("3. Diretas", dir_blocos) + indiretas + forecast + '</div>')
