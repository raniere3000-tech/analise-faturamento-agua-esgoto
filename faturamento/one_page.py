# -*- coding: utf-8 -*-
"""Aba One page: acompanhamento do faturamento numa folha vertical, que lê bem no celular — destaque do realizado contra
o orçado e a tendência, orçados do mês, faturamento aberto e indiretas por classe (realizado, forecast e tendência),
acompanhamento por grupo (tabela e gráfico), mês contra o anterior e Top 5 clientes — baixado em PDF de uma página.

Aqui só a estrutura da aba; os números são montados no navegador (relatorio.js) a partir da DRE (realizado e orçado
de cada mês e superintendência), das Diretas (orçado por ciclo) e do Resumo (grupos), seguindo os filtros do cabeçalho.
A tendência (realizado + forecast) acompanha as edições do forecast feitas nas abas Forecast e Indiretas.
"""
import html
import json

from .previsao import data_corte


def gera_aba_onepage_html(ctx):
    e = lambda v: html.escape(str(v), quote=True)
    corte = data_corte(ctx)
    # primeira data de leitura de cada grupo no mês vigente: separa os grupos por semana no acompanhamento
    from .situacao_grupo import _datas_de_leitura
    datas = {g: ini.isoformat() for g, (ini, _fim) in _datas_de_leitura(ctx, ctx.ref_atual).items()}
    datas_json = json.dumps(datas, ensure_ascii=False).replace("</", "<\\/")
    return f"""
<div class="card op-editor" id="opEditor" data-ref="{e(ctx.ref_atual)}" data-mes="{e(ctx.mes_atual)}" data-corte="{e(corte.strftime('%d/%m/%Y'))}">
  <div class="gar-topo">
    <h2>One page</h2>
    <span class="gar-espaco"></span>
    <button type="button" class="btn-just op-btn-pdf" id="opPdf" title="Baixa a folha abaixo em PDF, numa página só">&#128196; Baixar PDF</button>
  </div>
  <p class="nota-secao">Segue os filtros do cabeçalho: <b>superintendência</b>, <b>mês</b> e <b>grupos</b>; o realizado é comparado com o <b>orçado SUP</b>. No acompanhamento por semana, clique
  na semana para abrir ou fechar os grupos lidos nela. A <b>tendência</b> é o realizado + o <b>forecast</b>: ajuste o forecast nas abas
  Forecast ou Indiretas e a folha se atualiza. No Top 5 clientes, a chave <b>Somente liberadas</b> deixa só as matrículas cuja conta do mês
  não está <b>Em análise</b> (fica salva no seu navegador e vale também para o PDF).</p>
</div>
<script type="application/json" id="opDatasLeitura">{datas_json}</script>
<div class="op-folha" id="opFolha"></div>
"""
