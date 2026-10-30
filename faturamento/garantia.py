# -*- coding: utf-8 -*-
"""Aba Garantia: Top 1000 por média do faturado e base de consulta para a Análise de Garantia.

Para cada matrícula (base completa, todos os grupos):
  - média de todos os meses FECHADOS disponíveis (antes do mês atual): consumo medido, consumo faturado (água) e
    faturado em R$ (água + esgoto) — a lista atualiza sozinha a cada mês fechado que entra na pasta;
  - o mês atual: consumo faturado, faturado (R$), Situação Conta e Situação Lançamento;
  - dados cadastrais da linha mais recente: cliente, categoria, localidade, grupo, rota, SUP, economias por tipo e se
    tem esgoto (fator 2 na estrutura tarifária).
O ranking é pela média do faturado (R$). Vai embutido no relatório (JSON em gzip); a análise manual, o resumo de
ganhos e o e-mail ficam no navegador (relatorio.js), com as edições no ajustes_relatorio.json da pasta.
"""
import base64
import gzip
import html
import json

import numpy as np
import pandas as pd

from .config import REGRAS
from .formatacao import nome_mes, normaliza_texto

TOP = int(REGRAS.get("garantia_top", 1000))
COLUNAS = ["lig", "nome", "cat", "loc", "grupo", "rota", "sup", "res", "com", "ind", "pub", "esg", "sit", "lanc",
           "mMed", "mCons", "mVal", "n", "med", "cons", "val", "rank", "vAnt", "cAnt"]
_ECO = {"res": "Qtd. Economia Residencial", "com": "Qtd. Economia Comercial", "ind": "Qtd. Economia Industrial",
        "pub": "Qtd. Economia Publica"}


def _chave_ref(r):
    return (str(r)[3:], str(r)[:2])


def _col(df, prefixo):
    for c in df.columns:
        if normaliza_texto(c).startswith(prefixo):
            return c
    return None


def _num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)


def monta_garantia(ctx):
    """DataFrame (uma linha por matrícula, ordenado pelo ranking) com as colunas de COLUNAS + lista de meses fechados."""
    from .dre import prepara
    prepara(ctx)
    b = ctx.base_completa if getattr(ctx, "base_completa", None) is not None else ctx.base_final
    ra = ctx.ref_atual
    refs = sorted({r for r in b["Referencia de Leitura"].dropna().unique()}, key=_chave_ref)
    fechados = [r for r in refs if _chave_ref(r) < _chave_ref(ra)]
    serv = b["__serv"] if "__serv" in b.columns else b["Rubrica"].astype(str).str.upper().map(
        lambda r: "E" if "ESGOTO" in r else "A" if "AGUA" in r else "")
    ok = serv.isin(["A", "E"])
    b, serv = b[ok], serv[ok]
    lig = b["N. Ligação"].astype(str).str.strip()
    ref = b["Referencia de Leitura"]
    val = _num(b["Valor (R$)"])
    agua = serv == "A"
    col_med = "Consumo Medido" if "Consumo Medido" in b.columns else None
    # por matrícula × mês
    k = [lig, ref]
    pm_val = val.groupby(k).sum()
    pm_cons = _num(b.loc[agua, "Consumo Faturado"]).groupby([lig[agua], ref[agua]]).sum()
    pm_med = (_num(b.loc[agua, col_med]).groupby([lig[agua], ref[agua]]).sum() if col_med
              else pd.Series(dtype=float))

    def media(s):
        if not len(s):
            return pd.Series(dtype=float)
        s = s[s.index.get_level_values(1).isin(fechados)]
        return s.groupby(level=0).mean()

    def do_mes(s, r=None):
        if not len(s):
            return pd.Series(dtype=float)
        s = s[s.index.get_level_values(1) == (r or ra)]
        return s.droplevel(1)

    mVal, mCons, mMed = media(pm_val), media(pm_cons), media(pm_med)
    n_meses = (pm_val[pm_val.index.get_level_values(1).isin(fechados)].groupby(level=0).size()
               if len(pm_val) else pd.Series(dtype=float))
    aVal, aCons, aMed = do_mes(pm_val), do_mes(pm_cons), do_mes(pm_med)
    # cadastro: linha de água mais recente de cada matrícula (o mês atual primeiro)
    col_sit, col_lanc = _col(b, "SITUACAO CONTA"), _col(b, "SITUACAO LANCAMENTO")
    cols = {"nome": "Nome Cliente", "cat": "Categoria", "loc": "Nome da Localidade", "grupo": "Grupo", "rota": "Rota",
            "sup": "__sup", **_ECO, "sit": col_sit, "lanc": col_lanc}
    ba = b[agua]
    cad = pd.DataFrame({"lig": lig[agua].values, "ref": ref[agua].values,
                        "ordem": ref[agua].map({r: i for i, r in enumerate(refs)}).values})
    for nome, c in cols.items():
        cad[nome] = ba[c].values if c and c in ba.columns else None
    cad = cad.sort_values("ordem", ascending=False).drop_duplicates("lig").set_index("lig")
    # esgoto: a matrícula tem rubrica de esgoto no seu mês mais recente
    ult = cad["ref"]
    esg_lr = set(zip(lig[serv == "E"], ref[serv == "E"]))
    cad["esg"] = [(l, r) in esg_lr for l, r in zip(cad.index, ult)]
    # Situação Conta / Lançamento só valem para o mês atual (matrícula ainda sem fatura no mês = vazio)
    for c in ("sit", "lanc"):
        cad[c] = cad[c].where(ult == ra, None)
    d = cad.drop(columns=["ref", "ordem"])
    d["mVal"], d["mCons"], d["mMed"], d["n"] = mVal, mCons, mMed, n_meses
    d["val"], d["cons"], d["med"] = aVal, aCons, aMed
    rn = getattr(ctx, "ref_anterior", None)                       # mês anterior: sub-aba Aumentos e quedas
    d["vAnt"], d["cAnt"] = (do_mes(pm_val, rn), do_mes(pm_cons, rn)) if rn else (np.nan, np.nan)
    d = d.reset_index()
    d = d.sort_values(["mVal", "val"], ascending=False, na_position="last").reset_index(drop=True)
    d["rank"] = np.where(d["mVal"].notna(), np.arange(1, len(d) + 1), np.nan)
    for c in ("res", "com", "ind", "pub"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    return d[COLUNAS], fechados


def _limpa(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.floating, float)):
        return round(float(v), 2)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer, int)):
        return int(v)
    return str(v)


def gera_aba_garantia_html(ctx):
    """Aba Garantia (Top 1000 · Análise de Garantia · Resumo de Ganhos) + dados embutidos (matrículas e tarifa)."""
    d, fechados = monta_garantia(ctx)
    ctx.resultados["garantia"] = d
    linhas = [[_limpa(v) for v in r] for r in d.itertuples(index=False, name=None)]
    for r in linhas:                                      # ranking e economias como inteiros
        for i in (COLUNAS.index("rank"), COLUNAS.index("res"), COLUNAS.index("com"), COLUNAS.index("ind"), COLUNAS.index("pub")):
            if r[i] is not None:
                r[i] = int(round(r[i]))
    dados = {"refAtual": ctx.ref_atual, "mesAtual": ctx.mes_atual, "refs": fechados, "top": TOP, "colunas": COLUNAS, "linhas": linhas}
    b64 = base64.b64encode(gzip.compress(json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))).decode("ascii")
    tarifa = getattr(ctx, "tarifa", None) or {}
    meses = ", ".join(nome_mes(r) for r in fechados) or "nenhum mês fechado na pasta"
    e = lambda v: html.escape(str(v))
    fonte_tarifa = e(tarifa.get("fonte", "padrão"))
    return f"""
<div class="card gar-cabecalho">
  <div class="gar-topo">
    <h2>Garantia — {e(ctx.mes_atual)}</h2>
    <span class="gar-sub" role="tablist" aria-label="Partes da análise de garantia">
      <button type="button" data-gar-aba="top" class="ativo" aria-pressed="true">Top {TOP}</button><button type="button" data-gar-aba="variacao" aria-pressed="false">Aumentos e quedas</button><button type="button" data-gar-aba="analise" aria-pressed="false">Análise de Garantia</button><button type="button" data-gar-aba="resumo" aria-pressed="false">Resumo de Ganhos</button>
    </span>
  </div>
  <p class="nota-secao">Top {TOP} matrículas pela <b>média do faturado (água + esgoto)</b> dos meses fechados disponíveis ({e(meses)});
  a lista se refaz a cada mês fechado que entra na pasta. Valores do mês atual ({e(ctx.mes_atual)}) e Situação Conta pela fatura de ciclo.
  Variação acima de 30% (consumo faturado ou faturamento) em <b>negrito</b>. Estrutura tarifária: {fonte_tarifa}.</p>
</div>
<div class="gar-painel" data-gar="top">
  <div class="card">
    <div class="gar-barra">
      <span class="gar-contagem" id="garTopContagem"></span>
      <span class="gar-busca"><label for="garBuscaLig">Matrícula</label><input type="text" id="garBuscaLig" inputmode="numeric" autocomplete="off" placeholder="Filtrar por matrícula (uma ou várias)"><button type="button" class="btn-just" id="garLimparBusca" title="Limpar o filtro de matrícula" aria-label="Limpar o filtro de matrícula">✕</button></span>
      <span class="gar-dd" id="garCatDD"><span class="gar-dd-rot">Categoria</span><button type="button" class="gar-dd-btn" id="garCatBtn" aria-haspopup="true" aria-expanded="false" aria-controls="garCatLista" title="Filtrar por categoria (marque quantas quiser)">Todas ▾</button><div class="gar-dd-lista" id="garCatLista" role="group" aria-label="Categorias"></div></span>
      <button type="button" class="btn-just gar-filtro" id="garSoAnalise" aria-pressed="false">Somente em análise</button>
      <button type="button" class="btn-just btn-baixar-gar" id="garBaixarTop" title="Baixar a lista na tela (Excel)" aria-label="Baixar a lista na tela (Excel)">&#11015;</button>
    </div>
    <div class="tabela-wrap"><table class="tabela-garantia" id="garTabelaTop"><thead></thead><tbody></tbody></table></div>
  </div>
</div>
<div class="gar-painel" data-gar="variacao" hidden>
  <div class="card">
    <div class="gar-barra">
      <span class="gar-contagem" id="garVarContagem"></span>
      <span class="gar-busca"><label for="garVarBusca">Matrícula</label><input type="text" id="garVarBusca" inputmode="numeric" autocomplete="off" placeholder="Filtrar por matrícula (uma ou várias)"><button type="button" class="btn-just" id="garVarLimpar" title="Limpar o filtro de matrícula" aria-label="Limpar o filtro de matrícula">✕</button></span>
      <span class="gar-dd" id="garVcatDD"><span class="gar-dd-rot">Categoria</span><button type="button" class="gar-dd-btn" id="garVcatBtn" aria-haspopup="true" aria-expanded="false" aria-controls="garVcatLista" title="Filtrar por categoria (marque quantas quiser)">Todas ▾</button><div class="gar-dd-lista" id="garVcatLista" role="group" aria-label="Categorias"></div></span>
      <button type="button" class="btn-just gar-filtro" id="garVarSoAnalise" aria-pressed="false">Somente em análise</button>
    </div>
    <p class="nota-secao">Matrículas que faturaram nos dois meses ({e(nome_mes(ctx.ref_anterior)) if getattr(ctx, "ref_anterior", None) else "mês anterior"} e {e(ctx.mes_atual)}), pela variação do
    <b>faturado de água + esgoto</b> (R$). O ranking é refeito com os filtros (Superintendência, Grupo, Categoria e "Somente em análise");
    o filtro de matrícula só procura dentro do Top 100. A seta <b>⬇≡</b> baixa o analítico completo (todas as matrículas com aumento ou queda).</p>
  </div>
  <div class="card"><div class="gar-topo"><h2>Top 100 aumentos — {e(ctx.mes_atual)} × mês anterior</h2>
    <button type="button" class="btn-just" data-var-baixar="aumento" title="Baixar o analítico dos aumentos (Excel, todas as matrículas com aumento, com os filtros)" aria-label="Baixar o analítico dos aumentos">&#11015;&#8801;</button></div>
    <div class="tabela-wrap"><table class="tabela-garantia" id="garTabelaAumento"><thead></thead><tbody></tbody></table></div></div>
  <div class="card"><div class="gar-topo"><h2>Top 100 quedas — {e(ctx.mes_atual)} × mês anterior</h2>
    <button type="button" class="btn-just" data-var-baixar="queda" title="Baixar o analítico das quedas (Excel, todas as matrículas com queda, com os filtros)" aria-label="Baixar o analítico das quedas">&#11015;&#8801;</button></div>
    <div class="tabela-wrap"><table class="tabela-garantia" id="garTabelaQueda"><thead></thead><tbody></tbody></table></div></div>
</div>
<div class="gar-painel" data-gar="analise" hidden>
  <div class="card">
    <div class="gar-barra gar-entrada">
      <label for="garEntrada">Matrículas</label>
      <textarea id="garEntrada" rows="1" placeholder="Digite ou cole matrículas (uma por linha) — ou cole as linhas da planilha de garantia do Excel, com o cabeçalho"></textarea>
      <button type="button" class="btn-just" id="garAdicionar">Adicionar</button>
      <span class="gar-msg" id="garMsg"></span>
      <span class="gar-espaco"></span>
      <button type="button" class="btn-just" id="garEmail" title="Copia a tabela formatada para colar no e-mail e baixa um rascunho de e-mail (.eml) para abrir no Outlook">📧 Exportar para e-mail</button>
    </div>
    <p class="nota-secao">A linha traz os dados da matrícula no mês atual. Preencha a <b>média faturada</b> (a do sistema, em m³): o
    <b>Fat. calculado</b> sai pela estrutura tarifária. <b>Fat. anterior</b> é a foto do faturado no momento em que a matrícula entrou
    na análise; <b>Fat. ajustado</b> é o faturado atual (muda quando a fatura é liberada). Em <b>O.S.</b>, “Abrir O.S.” entra no controle
    de prazo (D+10 a partir do dia da análise) do Resumo de Ganhos. Tudo fica salvo na pasta para todos.
    <b>Análises feitas antes do painel:</b> no Excel, selecione as linhas da planilha de garantia <i>com o cabeçalho</i>, copie e cole no
    campo acima. Entram com o selo <b>Histórico</b>, o Fat. anterior da planilha, a média, o motivo, o retorno e a O.S. (“abrir O.S.” na
    observação).</p>
    <div class="tabela-wrap"><table class="tabela-garantia" id="garTabelaAnalise"><thead></thead><tbody></tbody></table></div>
  </div>
</div>
<div class="gar-painel" data-gar="resumo" hidden>
  <div class="card gar-aviso-os" id="garAvisoOS" hidden></div>
  <div class="card" id="garantia-resumo-card">
    <div class="gar-topo"><h2>Resumo de ganhos — garantia — {e(ctx.mes_atual)}</h2>
    <button type="button" class="btn-just gar-filtro" id="garSoLiberados" aria-pressed="false" title="Considerar só os grupos com situação Liberado (manual ou automática), sem mexer no filtro de grupos das outras abas">Somente grupos liberados</button></div>
    <p class="nota-secao"><b>Queda de consumo:</b> garantia = faturado ajustado (atual) − faturado anterior (foto).
    <b>Aumento de consumo:</b> garantia = faturado ajustado (atual) − valor pela média (estrutura tarifária), o que deixou de ser
    perdido com o desconto pela média. Em análise = Situação Conta EM ANALISE <b>ou</b> Situação Lançamento com “RETIDA” no nome; liberadas = as demais.</p>
    <div id="garResumo"></div>
  </div>
</div>
<script type="application/octet-stream" id="garantia-dados" data-gz="1">{b64}</script>
<script type="application/json" id="tarifa-dados">{json.dumps(tarifa, ensure_ascii=False).replace("</", "<\\/")}</script>
"""
