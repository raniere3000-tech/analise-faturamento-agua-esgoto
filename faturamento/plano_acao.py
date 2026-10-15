# -*- coding: utf-8 -*-
"""Aba Plano de ação: tabela colada da planilha (Excel) — fica no ajustes_relatorio.json da pasta (seção "plano") e
vai para o PDF executivo.

Aqui só a estrutura da aba; colar, salvar, filtrar e desenhar a tabela ficam no navegador (relatorio.js). Cada mês
(referência) tem o seu plano; sem plano no mês, aparece o último colado.
"""
import html


def gera_aba_plano_html(ctx):
    e = lambda v: html.escape(str(v), quote=True)
    return f"""
<div class="card plano-entrada" id="planoEntrada" data-ref="{e(ctx.ref_atual)}" data-mes="{e(ctx.mes_atual)}">
  <div class="gar-topo">
    <h2>Plano de ação — colar da planilha</h2>
    <span class="gar-espaco"></span>
    <button type="button" class="btn-just" id="planoBaixar" title="Baixar o plano na tela (CSV)" aria-label="Baixar o plano na tela (CSV)">&#11015;</button>
    <button type="button" class="btn-just" id="planoLimpar" style="color:#C2560C;" title="Apagar o plano de ação deste mês">Limpar</button>
  </div>
  <p class="nota-secao">Na planilha, selecione as linhas do plano <b>com o cabeçalho</b>, copie (Ctrl+C) e cole no campo abaixo (Ctrl+V).
  O plano colado substitui o do mês, fica salvo na pasta para todos e entra no <b>PDF executivo</b>. Colunas de
  <b>Status</b> ganham cor; <b>Prazo</b> vencido fica em destaque; colunas <b>SUP</b> e <b>Grupo</b> seguem os filtros do cabeçalho.</p>
  <textarea id="planoColar" class="plano-colar" rows="2" placeholder="Clique aqui e cole (Ctrl+V) as linhas copiadas da planilha, com o cabeçalho"></textarea>
  <span class="gar-msg" id="planoMsg"></span>
</div>
<div class="card" id="plano-card">
  <h2 id="planoTitulo">Plano de ação — {e(ctx.mes_atual)}</h2>
  <p class="nota-secao" id="planoInfo"></p>
  <div class="tabela-wrap"><table class="tabela-plano" id="planoTabela"><thead></thead><tbody></tbody></table></div>
</div>
"""
