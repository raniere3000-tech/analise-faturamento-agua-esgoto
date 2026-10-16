# -*- coding: utf-8 -*-
"""Estrutura tarifária (mesma regra da planilha da Análise de Garantia), aba Garantia e tarifa na etapa 2."""
import json
import os
import re

import openpyxl
import pandas as pd
import pytest

from dados_sinteticos import gera_pasta
from faturamento import Sessao
from faturamento.config import REGRAS
from faturamento.tarifa import minimo_ligacao, valor_pela_media

TAB = dict(REGRAS["estrutura_tarifaria"])


def test_valor_pela_media_igual_a_planilha():
    # Resumo de Ganhos da planilha: PÚBLICA, 1 economia pública, só água
    assert valor_pela_media(TAB, 1405, "PUBLICA", {"pub": 1}) == pytest.approx(26605.0435, abs=1e-4)
    assert valor_pela_media(TAB, 394, "PUBLICA", {"pub": 1}) == pytest.approx(7348.1221, abs=1e-4)
    # abaixo do mínimo cobra o mínimo (3 economias residenciais = 45 m³), com esgoto dobra
    assert valor_pela_media(TAB, 30, "RESIDENCIAL", {"res": 3}, esgoto=True) == pytest.approx(45 * 5.6941 * 2)
    assert minimo_ligacao(TAB, "RESIDENCIAL", {"res": 3}) == 45
    assert minimo_ligacao(TAB, "COMERCIAL", {"res": 1, "com": 2}) == 15 + 40     # mista: cada tipo com o seu mínimo


def _planilha_tarifa(pasta, residencial_minimo=15, tarifa1=5.6941):
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "tblTarifas"
    ws.append(["Categoria", "Limite Inicial", "Limite Final", "Tarifa Normal", "Tarifa Progressiva"])
    for f in TAB["faixas"]:
        f = list(f)
        if f[0] == "RESIDENCIAL" and f[1] == 0:
            f[3] = tarifa1
        ws.append(f)
    m = wb.create_sheet("tblMinimo")
    m.append(["Categoria", "Limite por economia"])
    for k, v in TAB["minimos"].items():
        m.append([k, residencial_minimo if k == "RESIDENCIAL" else v])
    wb.save(os.path.join(pasta, "Estrutura Tarifaria.xlsx"))


@pytest.fixture(scope="module")
def sessao(tmp_path_factory):
    pasta = str(tmp_path_factory.mktemp("garantia"))
    gera_pasta(pasta, com_dre=True, n_meses=4, grupos_faltando=2)
    s = Sessao(pasta, progresso=lambda p, t: None)
    s.preparar()
    s.continuar()
    return s


def test_top1000_pela_media_dos_meses_fechados(sessao):
    ctx = sessao.ctx
    g = ctx.resultados["garantia"]
    b = ctx.base_completa
    fechados = sorted({r for r in b["Referencia de Leitura"].unique() if (r[3:], r[:2]) < (ctx.ref_atual[3:], ctx.ref_atual[:2])})
    assert len(fechados) == 3
    lig = g.iloc[0]["lig"]
    x = b[(b["N. Ligação"].astype(str) == lig) & b["__serv"].isin(["A", "E"])]
    por_mes = x.groupby("Referencia de Leitura")["Valor (R$)"].sum()
    assert g.iloc[0]["mVal"] == pytest.approx(por_mes[por_mes.index.isin(fechados)].mean())
    assert g.iloc[0]["val"] == pytest.approx(por_mes.get(ctx.ref_atual, float("nan")), nan_ok=True)
    assert g["mVal"].dropna().is_monotonic_decreasing and list(g["rank"].dropna()[:3]) == [1, 2, 3]
    assert set(g["sit"].dropna()) <= {"EM ANALISE", "LIBERADA"}


def test_aba_garantia_no_relatorio(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert 'id="view-garantia"' in html and 'id="btn-garantia"' in html
    for trecho in ('data-gar-aba="top"', 'data-gar-aba="analise"', 'data-gar-aba="resumo"', 'id="garSoAnalise"', 'id="garEmail"', 'id="garBuscaLig"',
                   'id="garantia-resumo-card"', 'id="garantia-dados" data-gz="1"', 'id="tarifa-dados"',
                   "var syncGarantia = criaSync('garantia'", "raiz.Tarifa = { valor, minimo, norm }"):
        assert trecho in html, trecho
    assert "['Garantia — Resumo de Ganhos'" not in html        # a garantia não vai para o PDF executivo
    tarifa = json.loads(re.search(r'<script type="application/json" id="tarifa-dados">(.*?)</script>', html, re.S).group(1))
    assert tarifa["fonte"].startswith("padrão") and len(tarifa["faixas"]) == len(TAB["faixas"])


def test_planilha_de_tarifa_na_pasta(tmp_path):
    from faturamento import analises
    pasta = str(tmp_path)
    gera_pasta(pasta, n_meses=2)
    _planilha_tarifa(pasta, residencial_minimo=10_000, tarifa1=9.99)
    s = Sessao(pasta, progresso=lambda p, t: None)
    resultado = s.preparar()
    ctx = s.ctx
    assert ctx.tarifa["fonte"] == "Estrutura Tarifaria.xlsx"
    assert [f for f in ctx.tarifa["faixas"] if f[0] == "RESIDENCIAL"][0][3] == pytest.approx(9.99)
    assert ctx.tarifa["minimos"]["RESIDENCIAL"] == 10_000
    assert analises.CONSUMO_MINIMO_POR_CATEGORIA["RESIDENCIAL"] == 10_000          # vale para o painel todo
    assert resultado["tarifa"]["minimos"]["RESIDENCIAL"] == 10_000                 # e vai para a etapa 2
    assert not any("Estrutura" in str(i.get("arquivo")) for i in ctx.classificacao["ignorados"])
    # análise seguinte sem a planilha: volta ao regras.json
    os.remove(os.path.join(pasta, "Estrutura Tarifaria.xlsx"))
    s2 = Sessao(pasta, progresso=lambda p, t: None); s2.preparar()
    assert analises.CONSUMO_MINIMO_POR_CATEGORIA["RESIDENCIAL"] == 15 and s2.ctx.tarifa["fonte"].startswith("padrão")


def test_etapa2_recebe_economias_por_tipo_e_esgoto(sessao):
    from faturamento.top20 import calcula_top20_maior_consumo
    r = calcula_top20_maior_consumo(sessao.ctx)
    assert r["tarifa"]["faixas"] and r["linhas"]
    l = r["linhas"][0]
    assert {"eco_res", "eco_com", "eco_ind", "eco_pub", "esgoto"} <= set(l)
    assert l["eco_res"] + l["eco_com"] + l["eco_ind"] + l["eco_pub"] == pytest.approx(l["economias"])
    site = open(os.path.join(os.path.dirname(__file__), "..", "index.html"), encoding="utf-8").read()
    assert '<script src="faturamento/assets/tarifa.js"></script>' in site and 'id="chkMinTodos"' in site
    assert 'data-view="garantia"' in site


def test_os_e_email_no_layout_pedido(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert 'id="garAvisoOS"' in html and "const OS_ABRIR = 'Abrir O.S.', OS_NAO = 'Não abrir O.S.', OS_PRAZO_DIAS = 10;" in html
    assert "const cols = ['Grupo', 'Nº da Ligação', 'Superintendência', 'Motivo', 'Retorno Superintendência'];" in html
    # o aviso de O.S. fica fora do card do resumo (não vai para o PDF)
    assert html.index('id="garAvisoOS"') < html.index('id="garantia-resumo-card"')


def test_email_formatado_e_rascunho_eml(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert "const AZUL = '#333F4F'" in html and "tit('Email'" not in html and "font-size:14pt" in html and "border:none" in html
    assert "function garBaixarEml(html, assunto, nome)" in html and "'X-Unsent: 1'" in html


def test_importar_planilha_de_garantia(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert "function garImportarExcel(texto)" in html and "function garLerTSV(texto)" in html
    assert "if (t.includes('\\t') && garImportarExcel(t))" in html and "Antes do painel (planilha)" in html
    assert 'data-campo="os_num"' in html and "<th>Nº O.S.</th>" in html


def test_justificativas_agua_e_esgoto_por_grupo(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    info = json.loads(re.search(r'<script type="application/json" id="just-grupos">(.*?)</script>', html, re.S).group(1))
    assert info["grupos"] and set(info["esgoto"]) <= set(info["grupos"])
    assert "function justBloco(g, agua, esgoto)" in html and "function justConverterAntigo(lista)" in html


def test_analitico_diretas_conta_cada_mes_pelo_grupo_daquele_mes(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert "porMes: [[`Grupo ${rn}`, [eAnt, cAnt, vAnt]], [`Grupo ${ra}`, [eAt, cAt, vAt]]]" in html
    assert "const leitor = (l) =>" in html


def test_icone_da_aba(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,' in html


def test_copia_para_celular_le_ajustes_embutidos(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert "function ajustesCopia()" in html and "return ajustesCopia() ? COPIA_LEITURA : null;" in html
    site = open(os.path.join(os.path.dirname(__file__), "..", "index.html"), encoding="utf-8").read()
    assert 'const ARQ_COPIA = "Relatorio_Faturamento.html";' in site and 'id="btnAbrirRel"' in site and "@media (max-width: 760px)" in site


def test_aba_plano_de_acao(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    for trecho in ('id="view-plano"', 'id="btn-plano"', 'id="planoColar"', 'id="plano-card"', "var syncPlano = criaSync('plano'",
                   "['Plano de Ação', [q('#plano-card.tem-dados')]]"):
        assert trecho in html, trecho
    worker = open(os.path.join(os.path.dirname(__file__), "..", "analisador.worker.js"), encoding="utf-8").read()
    assert '"faturamento/plano_acao.py"' in worker


def test_analise_so_economias_que_faturam_esgoto(sessao):
    """A versão "só esgoto" das tabelas da aba Análise conta só as ligações com esgoto faturado no mês."""
    import re as _re
    from faturamento.tabelas_html import tabelas_so_esgoto
    ctx = sessao.ctx
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert html.count('class="vista-serv"') == 6 and 'data-vista-btn="esgoto"' in html
    b = ctx.base_final
    ligs = sorted(b["N. Ligação"].astype(str).str.strip().unique())
    sem_esgoto = set(ligs[::3])                                   # um terço das ligações deixa de ter esgoto
    tira = (b["__serv"] == "E") & b["N. Ligação"].astype(str).str.strip().isin(sem_esgoto)
    original = ctx.base_final
    try:
        ctx.base_final = b[~tira]
        c, _, _ = tabelas_so_esgoto(ctx, "", "", "")
    finally:
        ctx.base_final = original
    total = lambda seg: [int(x.replace(".", "")) for x in _re.findall(r">(-?[\d.]+)<", _re.search(r'class="linha-total".*?</tr>', seg, _re.S).group(0))]
    so = total(c[c.index('data-vista="esgoto"'):])
    agua = b[(b["__serv"] == "A") & (b["Referencia de Leitura"] == ctx.ref_atual) & (b["Consumo Faturado"] > 0)
             & ~b["N. Ligação"].astype(str).str.strip().isin(sem_esgoto)]
    ativa = agua[agua["Situacao Ligacao"].astype(str).str.upper().str.contains("ATIV")]["Economias_Totais"].sum()
    assert so[0] == int(ativa)
    assert ctx.base_final is original                            # a base do resto do relatório não muda


def test_pdf_justificativas_um_bloco_por_grupo(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert "const separaGrupos = (c) =>" in html and "flatMap(separaGrupos)" in html
    assert "if (M + LH - y < LH * 0.3) novaPagina();" in html              # quadro grande começa abaixo do título


def test_top1000_filtro_de_categoria(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert 'id="garCatBtn"' in html and 'id="garCatLista"' in html
    assert "(!GAR.cats || GAR.cats.has(garCat(d)))" in html and "function garMontarCategorias()" in html


def test_filtros_padrao_e_pessoais(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert "window.aplicarGruposPadrao = function ()" in html and "v === 'Liberado' || v === 'Em Análise'" in html
    site = open(os.path.join(os.path.dirname(__file__), "..", "index.html"), encoding="utf-8").read()
    assert "lerFiltrosSalvos()" in site and '"INTERIOR"' in site and "salvaFiltros({ grupos:" in site


def test_analise_de_garantia_ordenavel(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert "const GAR_COLS_ANALISE = [" in html and "function garOrdenarAnalise(itens)" in html and 'data-ord-an="${c}"' in html


def test_aba_one_page(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    for trecho in ('id="view-onepage"', 'id="btn-onepage"', 'id="opEditor"', 'id="opFolha"', "var syncOnePage = criaSync('onepage'",
                   "function gerarOnePage(libs)", 'onclick="gerarOnePage()"', 'id="opDatasLeitura"'):
        assert trecho in html, trecho
    raiz = os.path.join(os.path.dirname(__file__), "..")
    worker = open(os.path.join(raiz, "analisador.worker.js"), encoding="utf-8").read()
    assert '"faturamento/one_page.py"' in worker
    site = open(os.path.join(raiz, "index.html"), encoding="utf-8").read()
    assert 'id="btnOnePage"' in site and "w.gerarOnePage(await libsPdf())" in site and 'data-view="onepage"' in site
