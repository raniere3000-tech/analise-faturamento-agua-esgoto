# -*- coding: utf-8 -*-
"""Aba "Dados": bases carregadas, mapeamento do orçado e avisos (os avisos aparecem só aqui)."""
import html

from .config import chave_texto
from .formatacao import nome_mes
from .dre import ROTULOS_ORCADO, prepara

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
            linha = ROTULOS_ORCADO.get(chave_texto(rub))
            destino = NOME_LINHA_DRE.get(linha, "Soma (calculada)" if linha and linha.startswith("ri_") else "não usada na DRE")
            if (rub, sup) in vistos:
                continue
            vistos.add((rub, sup))
            linhas.append([html.escape(str(sup)), html.escape(str(rub)), html.escape(destino), f"{valor:,.0f}".replace(",", ".")])
        blocos.append(f'<h3>{html.escape(nome)} — {html.escape(info["arquivo"])} — {ctx.mes_atual}</h3>'
                      + (_tabela(["Sup", "Rubrica na planilha", "Linha da DRE", "Valor"], linhas) if linhas
                         else '<p class="nota-secao">Sem valores neste mês.</p>'))
    return "".join(blocos)


def gera_aba_dados_html(ctx):
    prepara(ctx)
    avisos = _avisos(ctx)
    lista = ("<ul class=\"avisos-dre\">" + "".join(f"<li>{html.escape(a)}</li>" for a in avisos) + "</ul>") if avisos \
        else '<p class="nota-secao">Nenhum aviso.</p>'
    linhas = [[html.escape(i["tipo"]), html.escape(i["arquivo"]), f"{i['linhas']:,}".replace(",", "."),
               html.escape(i["periodo"] or "—"), html.escape(i.get("extra", ""))] for i in ctx.bases_info]
    return (f'<div class="card"><h2>Avisos</h2>{lista}</div>'
            f'<div class="card"><h2>Bases carregadas</h2>'
            + _tabela(["Tipo", "Arquivo", "Linhas", "Meses", "Observação"], linhas) + '</div>'
            f'<div class="card"><h2>Orçado: linhas reconhecidas</h2>'
            '<p class="nota-secao">Como cada linha da planilha de orçado entra na DRE (ex.: "Fat. Bruto de água - Direto" = DIRETAS ÁGUA). '
            'O orçado das linhas "RI" só existe se a planilha tiver linhas com esses nomes.</p>'
            + (_mapeamento_orcado(ctx) or '<p class="nota-secao">Nenhuma planilha de orçado carregada.</p>') + '</div>')
