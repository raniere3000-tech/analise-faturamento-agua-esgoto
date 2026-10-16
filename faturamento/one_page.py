# -*- coding: utf-8 -*-
"""Aba One page: painel executivo de faturamento numa folha 16:9 — KPIs, evolução (realizado × orçado), composição
(natureza e serviço), indicadores operacionais, análise crítica e projetos/oportunidades — baixado em PDF de uma página.

Aqui só a estrutura da aba; os números são montados no navegador (relatorio.js) a partir da DRE (realizado e orçado
de cada mês e superintendência) e do Resumo (grupos), seguindo os filtros do cabeçalho. O título, a análise crítica
e os projetos são editados na própria folha e ficam no ajustes_relatorio.json da pasta (seção "onepage").
"""
import html

from .previsao import data_corte


def gera_aba_onepage_html(ctx):
    e = lambda v: html.escape(str(v), quote=True)
    corte = data_corte(ctx)
    return f"""
<div class="card op-editor" id="opEditor" data-ref="{e(ctx.ref_atual)}" data-mes="{e(ctx.mes_atual)}" data-corte="{e(corte.strftime('%d/%m/%Y'))}">
  <div class="gar-topo">
    <h2>One page executivo</h2>
    <label class="op-titulo-campo">Título <input type="text" id="opTitulo" maxlength="120"></label>
    <span class="gar-espaco"></span>
    <button type="button" class="btn-just op-btn-pdf" id="opPdf" title="Baixa a folha abaixo em PDF, numa página 16:9">&#128196; Baixar PDF</button>
  </div>
  <p class="nota-secao">Os números seguem os filtros do cabeçalho: <b>superintendência</b>, <b>mês</b> (competência),
  <b>Comparar</b> (o primeiro orçado escolhido) e <b>grupos</b> (economias acima do mínimo). Escreva a <b>análise crítica</b>
  e os <b>projetos</b> direto na folha (clique no quadro; nos projetos também dá para colar da planilha). Eles ficam
  salvos na pasta para todos: a análise por mês e superintendência, os projetos por superintendência.</p>
  <span class="gar-msg" id="opEscala"></span>
</div>
<div class="op-palco" id="opPalco"><div class="op-folha" id="opFolha"></div></div>
"""
