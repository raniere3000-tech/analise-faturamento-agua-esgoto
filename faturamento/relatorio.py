# -*- coding: utf-8 -*-
"""Montagem do relatório HTML (CSS e JavaScript ficam em `assets/`)."""
import html
import os

_DIR = os.path.dirname(os.path.abspath(__file__))


def carrega_asset(nome):
    with open(os.path.join(_DIR, "assets", nome), encoding="utf-8") as f:
        return f.read()


def gera_justificativa_html(ctx, texto_justificativa):
    return f"""
<div class="card" id="card-justificativa">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
        <h2 style="margin:0;">Justificativas e observações — {ctx.mes_atual}</h2>
        <div>
            <button class="btn-just" onclick="adicionarJustificativa()">Adicionar</button>
            <button class="btn-just" id="btnEditarJust" onclick="toggleEdicaoJustificativa()">Editar</button>
            <button class="btn-just" onclick="limparJustificativas()" style="color:#C2560C;">Limpar</button>
        </div>
    </div>
    <div id="lista-justificativas" style="font-size:0.9em; color:#1A2740; line-height:1.6;">
        {texto_justificativa}
    </div>
</div>
"""


def gera_filtro_html(ctx):
    grupos_disponiveis = (
        ctx.fatura_total["Grupo"]
        .dropna()
        .astype(str).str.strip()
        .unique()
    )
    grupos_disponiveis = sorted([g for g in grupos_disponiveis if g not in ("nan", "None", "")])

    checkboxes_html = ""
    for g in grupos_disponiveis:
        check = html.escape(g, quote=True)
        checkboxes_html += f"<label class='check-item'><input class='chk-grupo' type='checkbox' value='{check}' checked onchange='filtrarPorGrupo()'><span>{html.escape(g)}</span></label>"

    return f"""
<div class="filtro-wrap">
<button id="btnFiltro" class="btn-filtro" onclick="toggleFiltro(event)">
    <span>Filtrar grupos</span>
    <span id="badgeFiltro" class="badge">{len(grupos_disponiveis)}</span>
</button>
<div id="painelFiltro" class="painel-filtro">
<div class="painel-acoes">
<button class="mini-btn" onclick="marcarTodos(true)">Marcar todos</button>
<button class="mini-btn" onclick="marcarTodos(false)">Limpar</button>
</div>
<div class="check-list">{checkboxes_html}</div>
</div>
</div>
"""


def monta_html(ctx, *, alerta_minimo_html, aviso_ajustes_html, filtro_html, cards_kpis_html,
               grafico_faturamento_html, card_leitura_html, cards_insights_html, tabela_dados_resumo_html,
               justificativa_html, tabela_agua_html, tabela_esgoto_html, tabelas_orcado_ciclo_html, quadro_ciclos_html, matriz_html,
               tabela_minimo_html, tabela_top100_agua_html, tabela_top100_esgoto_html,
               tabela_aumento_agua_html, tabela_aumento_esgoto_html,
               aba_dre_html, aba_indiretas_html, aba_dados_html, aba_forecast_html, filtros_dre_html, info_filtros_json):
    chave_justificativa = "justificativas_" + ctx.mes_atual.replace(" ", "_").replace("/", "_")
    html_style = "\n<style>\n" + carrega_asset("relatorio.css") + "</style>\n"
    script_js = "\n<script>\n" + carrega_asset("relatorio.js").replace("__CHAVE_JUSTIFICATIVA__", chave_justificativa) + "</script>\n"
    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Relatório Comparativo Água x Esgoto</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
{html_style}
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
<a class="pular-conteudo" href="#view-resumo">Ir para o conteúdo</a>
<div class="header-exec">
  <div class="header-inner">
    <div class="header-badge">Águas do Rio · Relatório Executivo</div>
    <h1>Comparativo de Água e Esgoto — {ctx.mes_atual} vs {ctx.mes_anterior}</h1>
    <p>Faturamento, economias, volumes e migração de ciclo{f" · grupos até o {ctx.ultimo_grupo}" if ctx.ultimo_grupo else ""}</p>
  </div>
</div>

<div class="toolbar">
  <div class="toggle" role="tablist" aria-label="Visualização">
    <button id="btn-dre" onclick="mostrarView('dre')">DRE</button>
    <button id="btn-resumo" class="active" onclick="mostrarView('resumo')">Resumo</button>
    <button id="btn-tabelas" onclick="mostrarView('tabelas')">Diretas</button>
    <button id="btn-indiretas" onclick="mostrarView('indiretas')">Indiretas</button>
    <button id="btn-forecast" onclick="mostrarView('forecast')">Forecast</button>
    <button id="btn-dados" onclick="mostrarView('dados')">Dados</button>
  </div>
  {filtros_dre_html}
  <button class="btn-filtro btn-imprimir" type="button" onclick="gerarExecutivo()" aria-label="Gerar o relatório executivo em PDF" title="PDF com KPIs, gráfico, forecast, orçado por ciclo, comparativos, indiretas e justificativas, conforme os filtros da tela">Executivo (PDF)</button>
  {filtro_html}
</div>

<div id="view-resumo" class="ativo">
    <div class="kpis-grid">{cards_kpis_html}</div>
    {grafico_faturamento_html}
    {card_leitura_html}
    <div class="card"><h2>Destaques do mês — {ctx.mes_atual}</h2>{cards_insights_html}</div>
    {tabela_dados_resumo_html}
    {justificativa_html}
</div>

<div id="view-dre">
    {aba_dre_html}
</div>

<div id="view-forecast">
    {aba_forecast_html}
</div>

<div id="view-dados">
    {aba_dados_html}
</div>

<div id="view-indiretas">
    {aba_indiretas_html}
</div>

<div id="view-tabelas" class="compacto">
    <div class="barra-diretas"><button type="button" class="btn-filtro" id="btn-colunas" onclick="alternarColunas()">Mostrar todas as colunas</button></div>
    {tabela_agua_html}
    {tabela_esgoto_html}
    {tabelas_orcado_ciclo_html}
    {quadro_ciclos_html}
    {matriz_html}
    {tabela_minimo_html}
    {tabela_top100_agua_html}
    {tabela_top100_esgoto_html}
    {tabela_aumento_agua_html}
    {tabela_aumento_esgoto_html}
</div>

{info_filtros_json}
{script_js}
</body>
</html>
"""
