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
    for trecho in ('data-gar-aba="top"', 'data-gar-aba="analise"', 'data-gar-aba="resumo"', 'id="garSoAnalise"', 'id="garEmail"',
                   'id="garantia-resumo-card"', 'id="garantia-dados" data-gz="1"', 'id="tarifa-dados"',
                   "var syncGarantia = criaSync('garantia'", "raiz.Tarifa = { valor, minimo, norm }",
                   "['Garantia — Resumo de Ganhos', [q('#garantia-resumo-card')]]"):
        assert trecho in html, trecho
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
