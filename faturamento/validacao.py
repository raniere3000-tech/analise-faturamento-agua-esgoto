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
            return "—" if pd.isna(v) else fmt_num(v, 2)
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
        ["Diretas Água e Esgoto, economias e volume", "<b>1. Média do grupo</b>",
         "Soma, para cada grupo que ainda não faturou, da média desse grupo nos últimos 3 meses",
         "As diretas são faturadas por grupo (ciclo de leitura): o que falta são os grupos que ainda não foram lidos"],
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
        "O histórico são os até 3 meses imediatamente anteriores ao mês projetado que existem na base.",
        "<b>Grupos faturados × grupos que faltam.</b> Grupos com linhas na fatura do mês já estão no Realizado. Grupos que faturaram "
        "no histórico e ainda não no mês são os que faltam.",
        "<b>Forecast de cada linha.</b> Aplica-se o método da tabela acima (média do grupo, ritmo por dia útil ou completar até a média).",
        "<b>Linhas calculadas.</b> Diretas Totais, Fat. de água - Indireto, Faturamento Bruto, volume médio, tarifa e ticket são refeitos a partir do fechamento.",
        "<b>Comparação com o orçado.</b> Δ R$ = Fechamento − Orçado; Δ % = Fechamento ÷ Orçado − 1, para cada planilha (RF ou RF SUP).",
        "<b>Ajuste manual (opcional).</b> Na aba Forecast, clique em um valor da coluna Forecast ✎ para trocá-lo; fechamento, totais e Δ "
        "são refeitos na hora e a edição fica salva neste navegador. \"↺ Restaurar automático\" volta ao cálculo.",
    ]).replace("<ul>", '<ol class="fc-passos">').replace("</ul>", "</ol>")
    return (f'<p class="val-rot">Em resumo</p>{resumo}<p class="val-rot">Os três métodos</p>{metodos}'
            f'<p class="val-rot">Passo a passo</p>{passos}')


def _explica_forecast(ctx, sup):
    """Memória de cálculo do forecast de uma superintendência, com os números do mês."""
    from .formatacao import nome_mes
    from .previsao import CLASSES_POR_DIA_UTIL, LINHAS_POR_GRUPO, MESES_BASE, calcula_previsao
    d = calcula_previsao(ctx, sup)
    if not d:
        return '<p>Sem meses anteriores na base: não há como projetar o fechamento.</p>'
    refs, du, atual, falta = d["refs"], d["dias"], d["atual"], d["falta"]
    corte = d["corte"].strftime("%d/%m/%Y")
    from .dre import _filtra
    base = ctx.base_completa
    faturados = sorted(set(_filtra(base[base["Referencia de Leitura"] == ctx.ref_atual], sup)["Grupo"].astype(str).str.strip()))

    parametros = _tab(["Parâmetro", "Valor", "De onde vem"], [
        ["Mês projetado", html.escape(ctx.mes_atual), "Última referência com linhas na fatura"],
        ["Histórico (meses-base)", html.escape(", ".join(nome_mes(r) for r in refs)),
         f"Até {MESES_BASE} meses anteriores ao mês projetado que existem na base (aqui: {len(refs)})"],
        ["Data de corte (D-1)", corte, "Arquivos atualizados até ontem: hoje ainda não conta como decorrido"],
        ["Grupos já faturados", html.escape(", ".join(faturados) or "nenhum"), "Têm linhas na fatura do mês: já estão no Realizado"],
        ["Grupos que faltam", html.escape(", ".join(d["faltam"]) or "nenhum"), "Faturaram no histórico e ainda não no mês"],
        ["Dias úteis do mês", f"{du['uteis']} (decorridos {du['uteis_decorridos']}, faltam {du['uteis_faltam']})",
         "Seg. a sex., sem feriados nacionais, Sexta-feira Santa, São Jorge (23/04) e feriados_extras de regras.json; pontos facultativos contam como úteis"],
        ["Dias de corte", f"{du['corte']} (decorridos {du['corte_decorridos']}, faltam {du['corte_faltam']})",
         "Dias úteis sem as sextas-feiras e sem as vésperas de feriado"],
    ])

    # método 1
    nomes_g = ["dA", "dE", "ecoA", "ecoE", "volA", "volE"]
    fmt_g = lambda k, v: _moeda(v) if k in ("dA", "dE") else fmt_num(v, 0)
    if d["grupos"]:
        linhas_g = [[html.escape(g), html.escape(", ".join(nome_mes(r) for r in i["meses"]))] + [fmt_g(k, i["media"][k]) for k in nomes_g]
                    for g, i in d["grupos"].items()]
        linhas_g.append(["<b>Forecast (soma)</b>", ""] + [f"<b>{fmt_g(k, falta[k])}</b>" for k in nomes_g])
        g, info = next(iter(d["grupos"].items()))
        partes = " + ".join(f"{_moeda(info['por_mes'][r]['dA'])} ({nome_mes(r)})" for r in info["meses"])
        corpo1 = (f'<p class="fc-exemplo"><b>Exemplo — grupo {html.escape(g)}, Diretas Água:</b> ({partes}) ÷ {len(info["meses"])} = '
                  f'<b>{_moeda(info["media"]["dA"])}</b>. Somando todos os grupos que faltam: forecast de <b>{_moeda(falta["dA"])}</b>; '
                  f'fechamento = {_moeda(atual.get("dA"))} + {_moeda(falta["dA"])} = <b>{_moeda((atual.get("dA") or 0) + falta["dA"])}</b>.</p>'
                  + _tab(["Grupo que falta", "Meses usados"] + [NOME_BASICA[k] for k in nomes_g], linhas_g))
    else:
        corpo1 = '<p>Todos os grupos já faturaram: o forecast de diretas, economias e volume é zero.</p>'

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
    if d["grupos"]:
        abas["Grupos que faltam"] = pd.DataFrame(
            [{"Grupo": g, "Meses usados": ", ".join(i["meses"]), **{NOME_BASICA[k]: i["media"][k] for k in LINHAS_POR_GRUPO}}
             for g, i in d["grupos"].items()])
    abas["Indiretas por dia util"] = pd.DataFrame([{
        "Linha": NOME_BASICA[k], "Realizado": atual.get(k) or 0.0,
        "Dias decorridos": du[("corte" if k == "ri_CORTE" else "uteis") + "_decorridos"],
        "Dias que faltam": du[("corte" if k == "ri_CORTE" else "uteis") + "_faltam"], "Forecast": falta[k]} for k in CLASSES_POR_DIA_UTIL])
    abas = {k: v for k, v in abas.items() if v is not None and len(v)}
    slug = "".join(c for c in sup.lower() if c.isalnum())
    botao = botao_download_xlsx("Baixar memória de cálculo (Excel)", f"validacao_forecast_{slug}.xlsx", xlsx_bytes(abas))

    return (f'<p>{botao}</p>'
            f'<h5 class="fc-titulo">A. Parâmetros do mês</h5>{parametros}'
            f'<h5 class="fc-titulo">B. Método 1 — Diretas, economias e volume (média do grupo)</h5>{corpo1}'
            f'<h5 class="fc-titulo">C. Método 2 — Indiretas (ritmo por dia útil)</h5>{corpo2}'
            f'<h5 class="fc-titulo">D. Método 3 — Cancelamento (completar até a média)</h5>{corpo3}'
            f'<h5 class="fc-titulo">E. Resultado: Realizado + Forecast</h5>{_amostra(df, n=40)}')


def _bloco_forecast(ctx):
    """Seção "5. Forecast" da aba Dados: explicação geral + memória de cálculo por superintendência (seletor próprio)."""
    from .dre import _nome_sup, lista_sups
    titulo = f"Forecast de fechamento — como é calculado ({html.escape(ctx.mes_atual)})"
    if getattr(ctx, "base_completa", None) is None:
        return f'<div class="val-bloco"><h4>{titulo}</h4>{_forecast_geral()}</div>'
    sups = lista_sups(ctx)
    e = lambda v: html.escape(v, quote=True)
    opcoes = "".join(f'<option value="{e(s)}">{html.escape(_nome_sup(s))}</option>' for s in sups)
    blocos = "".join(f'<div class="fc-sup" data-fc-sup="{e(s)}"{"" if k == 0 else " hidden"}>{_explica_forecast(ctx, s)}</div>'
                     for k, s in enumerate(sups))
    return (f'<div class="val-bloco"><h4>{titulo}</h4>{_forecast_geral()}'
            '<p class="val-rot">Memória de cálculo com os números do mês</p>'
            '<p class="fc-seletor"><label>Superintendência <select onchange="'
            "this.closest('.val-bloco').querySelectorAll('.fc-sup').forEach(b => b.hidden = b.dataset.fcSup !== this.value)"
            f'">{opcoes}</select></label></p>{blocos}</div>')


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
               "Duas tabelas (Água e Esgoto). O seletor \"comparar com\" acima delas escolhe a planilha de orçado (qualquer RF ou o RF SUP). "
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
        _bloco("Top 100 clientes com maior aumento de consumo",
               "Ligações que faturaram nos dois meses e consumiram mais no atual.",
               ["Aumento de consumo = consumo atual − consumo anterior (só aumentos positivos); Aumento % = aumento ÷ anterior",
                "Aumento de valor = valor atual − valor anterior; ordenado pelo maior aumento de consumo, 100 primeiros"],
               ["<b>N. Ligação</b>, <b>Nome Cliente</b>, <b>Grupo</b>, <b>Categoria</b>, <b>Consumo Faturado</b>, <b>Valor (R$)</b>"],
               {"Top100 Aumento Agua": r.get("aumento_agua"), "Top100 Aumento Esgoto": r.get("aumento_esgoto")}, "top100_aumento"),
    ]
    indiretas = _aba("4. Indiretas", [_bloco(
        f"Orçado × Realizado das indiretas ({mes})",
        "Cada linha RI compara o serviço avulso executado com a meta do RF / RF SUP. Ordem na tela: Fat. de água - Indireto "
        "(soma das aberturas), as aberturas RI (Cortes, Religações, Ligações de água, Fiscalização, Outros), Fat. de esgoto - Indireto e Total indiretas.",
        ["Realizado = soma do Valor Parcela do serviço avulso por classe (Cortes/Recorte, Religações, Ligações - Água, Fiscalização, Outros)",
         "Fat. de água - Indireto = soma das classes de água; Fat. de esgoto - Indireto = classe LNE",
         "Orçado = linhas do RF pelos nomes CORTE, RELIGAÇÃO, LNA, SANÇÃO, OUTROS (ou RI Cortes/Recorte etc.)",
         "Total indiretas = Fat. de água - Indireto + Fat. de esgoto - Indireto",
         "Δ R$ = Realizado − Orçado; Δ % = Realizado ÷ Orçado − 1",
         "Quantidade e ticket médio: Lanç. = número de lançamentos do serviço avulso no mês; Ticket = valor ÷ lançamentos; Δ ticket = ticket do mês − ticket do mês anterior"],
        ["Serviço avulso: <b>Rubrica</b> (classe), <b>Valor Parcela</b>, <b>Referencia de Leitura</b>", "Orçado: <b>Sup</b>, <b>Rubrica</b>, coluna do mês"],
        {"Indiretas": _indiretas_df(ctx)}, "indiretas")])

    forecast = _aba("5. Forecast", [_bloco_forecast(ctx)])

    return ('<div class="card val-card"><h2>Validação dos cálculos</h2>'
            '<p class="nota-secao">Explicação por aba, na ordem em que você navega. Cada item mostra o cálculo, as colunas utilizadas, uma amostra e um botão para baixar o resultado em Excel e conferir.</p>'
            + _base_utilizada(ctx) + dre + resumo
            + _aba("3. Diretas", dir_blocos) + indiretas + forecast + '</div>')
