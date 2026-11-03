# -*- coding: utf-8 -*-
"""Aba Fechamento: o fechamento do mês pelos números do BI (não a prévia da fatura de ciclo).

Os números entram no navegador: a pessoa cola o print do Power BI (Ctrl+V) ou escolhe a imagem, o painel lê o texto da
imagem (OCR) e mostra todos os campos para conferir e corrigir antes de salvar — com as somas checadas (diretas, bruto,
líquido). O fechamento salvo fica no ajustes_relatorio.json da pasta (seção "fechamento", por mês × superintendência).
As tabelas (DRE no formato Orçado | Realizado | Dif | % e as indiretas em R$ e em eventos, sem forecast) são montadas
em relatorio.js com os orçados embutidos aqui (todas as planilhas da pasta, todos os meses que elas têm).
"""
import html
import json

from .formatacao import nome_mes

CHAVES_ORC = ("dA", "dE", "iE", "ri_CORTE", "ri_RELIGAÇÃO", "ri_LNA", "ri_SANÇÃO", "ri_OUTROS", "ecoA", "ecoE", "volA", "volE", "canc")


def dados_fechamento(ctx):
    from .comparativo import _chave_ref
    from .dre import TODAS, _fontes, fonte_substituta, lista_meses, lista_sups, orcado
    from .previsao import eventos_orcados
    fontes, _ = _fontes(ctx)
    fontes = [f for f in fontes if "SUP" not in f.upper()] + [f for f in fontes if "SUP" in f.upper()]
    meses = set(lista_meses(ctx))
    for f in fontes:
        meses |= set(ctx.orcado[f]["dados"]["Referencia"].dropna().unique())
    meses = sorted((m for m in meses if _chave_ref(m)), key=_chave_ref)
    sups = lista_sups(ctx)
    orc, ev = {}, {}
    for f in fontes:
        refs = set(ctx.orcado[f]["dados"]["Referencia"].dropna().unique())
        for r in meses:
            if r not in refs or fonte_substituta(ctx, f, r):
                continue
            for sp in sups:
                v = orcado(ctx, f, sp, r)
                if any(v.get(k) is not None for k in CHAVES_ORC):
                    orc.setdefault(f, {}).setdefault(r, {})[sp] = {k: v.get(k) for k in CHAVES_ORC if v.get(k) is not None}
    for r in meses:
        for sp in sups:
            e = eventos_orcados(ctx, sp, r)
            if e:
                ev.setdefault(r, {})[sp] = e
    padrao = next((f for f in fontes if "SUP" in f.upper()), fontes[0] if fontes else "")
    return {"fontes": [f for f in fontes if f in orc], "padrao": padrao, "meses": meses, "rotulos": {m: nome_mes(m) for m in meses},
            "sups": sups, "orc": orc, "ev": ev, "mesAtual": ctx.ref_atual, "todas": TODAS}


def gera_aba_fechamento_html(ctx):
    d = dados_fechamento(ctx)
    dados = json.dumps(d, ensure_ascii=False).replace("</", "<\\/")
    return f"""
<div class="card fech-entrada" id="fechEntrada">
  <div class="gar-topo">
    <h2>Fechamento do mês — números do BI</h2>
    <span class="gar-espaco"></span>
    <label class="fech-sel">Mês <select id="fechMes"></select></label>
    <label class="fech-sel">Orçado <select id="fechOrcado"></select></label>
    <button type="button" class="btn-just" id="fechEditar" title="Conferir ou corrigir os números salvos deste mês">✎ Editar números</button>
    <button type="button" class="btn-just" id="fechLimpar" style="color:#C2560C;" title="Apagar o fechamento deste mês e superintendência">Limpar</button>
  </div>
  <p class="nota-secao">No Power BI, use <b>Copiar visual</b> (ou tire um print da tela) com as três tabelas: indiretas em R$, eventos faturados
  (Faturadas) e a linha das diretas. Depois clique no campo abaixo e cole (<b>Ctrl+V</b>), ou escolha o arquivo da imagem. O painel lê os
  números e mostra tudo para <b>conferir antes de salvar</b> (as somas são checadas). O fechamento vale para a <b>Superintendência do
  cabeçalho</b> e fica salvo na pasta para todos.</p>
  <div class="fech-colar" id="fechColar" tabindex="0" role="button" aria-label="Cole aqui o print do BI (Ctrl+V)">
    📋 Clique aqui e cole o print do BI (Ctrl+V) — ou <label class="fech-arq">escolha a imagem<input type="file" id="fechArquivo" accept="image/*" hidden></label>
  </div>
  <span class="gar-msg" id="fechMsg"></span>
  <div id="fechConferir" hidden></div>
</div>
<div id="fechTabelas"></div>
<script type="application/json" id="fechamento-dados">{dados}</script>
"""
