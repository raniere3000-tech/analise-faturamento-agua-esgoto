# -*- coding: utf-8 -*-
"""Aba "Dados": bases carregadas, mapeamento do orçado e avisos (os avisos aparecem só aqui)."""
import html

from .config import chave_texto
from .formatacao import nome_mes
from .dre import linha_do_orcado, prepara
from .validacao import gera_validacao_html

NOME_LINHA_DRE = {
    "bruto": "Faturamento Bruto", "dA": "DIRETAS ÁGUA", "dE": "DIRETAS ESGOTO", "iA": "Fat. de água - Indireto",
    "iE": "Fat. de esgoto - Indireto", "canc": "Cancelamento", "ecoA": "Economias de Água - Faturadas",
    "ecoE": "Economias de Esgoto - Faturadas", "volA": "Volume de Água - Faturado", "volE": "Volume de Esgoto - Faturado",
}


def _aviso_referencia_sem_fatura(ctx):
    """Avisa quando algum arquivo tem referência mais nova que a da fatura (o relatório só fatura o que está na fatura)."""
    mais_novas = {}
    for info in ctx.bases_info:
        if info["tipo"] not in ("Consumo", "Fatura", "Serviço avulso"):
            continue
        for m in str(info.get("periodo") or "").split(", "):
            if len(m) == 7 and (m[3:], m[:2]) > (ctx.ref_atual[3:], ctx.ref_atual[:2]):
                mais_novas.setdefault(m, []).append(f"{info['tipo']} {info['arquivo']}")
    return [f"Há dados de {nome_mes(m)} em {', '.join(sorted(set(arqs)))}, mas a fatura não tem linhas dessa referência: "
            f"o relatório usa {ctx.mes_atual} (última referência com fatura)." for m, arqs in sorted(mais_novas.items())]


def _avisos(ctx):
    avisos = list(ctx.avisos_dre) + list(ctx.avisos_base) + _aviso_referencia_sem_fatura(ctx)
    if ctx.ajustes_feitos:
        avisos.append(f"Este relatório usa {ctx.ajustes_feitos} ligação(ões) da conferência com valores ajustados manualmente "
                      f"(referência {ctx.ref_atual}).")
    for cat, qtd in sorted(ctx.categorias_sem_minimo.items()):
        avisos.append(f"Categoria sem consumo mínimo cadastrado: {cat} ({int(qtd):,} economias) — ficou fora da tabela de "
                      "consumo mínimo.".replace(",", "."))
    for ig in ctx.classificacao.get("ignorados", []):
        avisos.append(f"Arquivo ignorado: {ig['arquivo']} — {ig['motivo']}.")
    return avisos


def _tabela(cabecalho, linhas):
    cab = "".join(f"<th>{c}</th>" for c in cabecalho)
    corpo = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in l) + "</tr>" for l in linhas)
    return f'<div class="tabela-wrap"><table class="tabela-dados"><thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table></div>'


def _mapeamento_orcado(ctx):
    blocos = []
    for nome, info in ctx.orcado.items():
        d = info["dados"]
        d = d[d["Referencia"] == ctx.ref_atual]
        linhas = []
        vistos = set()
        for rub, sup, valor in zip(d["Rubrica"], d["Sup"], d["Valor"]):
            linha = linha_do_orcado(chave_texto(rub))
            destino = NOME_LINHA_DRE.get(linha, "Soma (calculada)" if linha and linha.startswith("ri_") else "não usada na DRE")
            if (rub, sup) in vistos:
                continue
            vistos.add((rub, sup))
            linhas.append([html.escape(str(sup)), html.escape(str(rub)), html.escape(destino), f"{valor:,.0f}".replace(",", ".")])
        blocos.append(f'<h3>{html.escape(nome)} — {html.escape(info["arquivo"])} — {ctx.mes_atual}</h3>'
                      + (_tabela(["Sup", "Rubrica na planilha", "Linha da DRE", "Valor"], linhas) if linhas
                         else '<p class="nota-secao">Sem valores neste mês.</p>'))
    return "".join(blocos)


def _conferencia_kpis(ctx):
    """De onde vêm os valores dos KPIs: soma de 'Valor (R$)' das rubricas de água e esgoto da última referência, por grupo."""
    from .formatacao import fmt_num

    def soma(df, rub):
        return float(df[df["Rubrica"].str.contains(rub, case=False, na=False)]["Valor (R$)"].sum())
    at = ctx.df_atual
    linhas = []
    for g, d in at.groupby("Grupo"):
        a, e = soma(d, "AGUA"), soma(d, "ESGOTO")
        linhas.append([html.escape(str(g)), f"{len(d):,}".replace(",", "."), "R$ " + fmt_num(a, 2), "R$ " + fmt_num(e, 2),
                       "R$ " + fmt_num(a + e, 2)])
    ta, te = soma(at, "AGUA"), soma(at, "ESGOTO")
    linhas.append(["<b>Total (KPIs)</b>", f"{len(at):,}".replace(",", "."), "<b>R$ " + fmt_num(ta, 2) + "</b>",
                   "<b>R$ " + fmt_num(te, 2) + "</b>", "<b>R$ " + fmt_num(ta + te, 2) + "</b>"])
    rubs = ", ".join(sorted({str(r) for r in at["Rubrica"].dropna().unique()})) or "—"
    comp = getattr(ctx, "base_completa", None)
    fora = ""
    if comp is not None and len(comp) > len(ctx.base_final):
        cm = comp[comp["Referencia de Leitura"] == ctx.ref_atual]
        extra = soma(cm, "AGUA") + soma(cm, "ESGOTO") - (ta + te)
        if abs(extra) > 0.005:
            fora = f' Grupos acima do {ctx.ultimo_grupo} (fora da análise): R$ {fmt_num(extra, 2)}.'
    return ('<p class="nota-secao">Os KPIs somam o campo "Valor (R$)" da fatura, só das rubricas de água e esgoto, nos grupos até o '
            f'{html.escape(str(ctx.ultimo_grupo or "—"))}. Rubricas presentes: {html.escape(rubs)}.{fora}</p>'
            + _tabela(["Grupo", "Linhas", "Valor de água", "Valor de esgoto", "Total"], linhas))


def gera_aba_dados_html(ctx):
    prepara(ctx)
    avisos = _avisos(ctx)
    lista = ("<ul class=\"avisos-dre\">" + "".join(f"<li>{html.escape(a)}</li>" for a in avisos) + "</ul>") if avisos \
        else '<p class="nota-secao">Nenhum aviso.</p>'
    linhas = [[html.escape(i["tipo"]), html.escape(i["arquivo"]), f"{i['linhas']:,}".replace(",", "."),
               html.escape(i["periodo"] or "—"), html.escape(i.get("extra", ""))] for i in ctx.bases_info]
    def topico(titulo, conteudo):
        return f'<details class="val-aba"><summary>{titulo}</summary><div class="val-bloco">{conteudo}</div></details>'
    orcado = ('<p class="nota-secao">Como cada linha da planilha de orçado entra na DRE (ex.: "Fat. Bruto de água - Direto" = DIRETAS ÁGUA). '
              'O orçado das linhas "RI" só existe se a planilha tiver linhas com esses nomes.</p>'
              + (_mapeamento_orcado(ctx) or '<p class="nota-secao">Nenhuma planilha de orçado carregada.</p>'))
    return ('<div class="card val-card"><h2>Dados e validação dos cálculos</h2>'
            '<p class="nota-secao">Clique em um tópico para abrir. Em 1 a 5, cada tabela e gráfico do relatório, aba por aba: o que mostra, '
            'quais bases e colunas entram, o cálculo passo a passo, como foi montado, uma amostra e botões para baixar a tabela (Excel) '
            'e a base usada (CSV).</p>'
            + topico(f"Avisos ({len(avisos)})", lista)
            + topico(f"Conferência dos KPIs — {html.escape(ctx.mes_atual)}", _conferencia_kpis(ctx))
            + topico("Bases carregadas", _tabela(["Tipo", "Arquivo", "Linhas", "Meses", "Observação"], linhas))
            + topico("Orçado: linhas reconhecidas", orcado)
            + gera_validacao_html(ctx) + '</div>')
