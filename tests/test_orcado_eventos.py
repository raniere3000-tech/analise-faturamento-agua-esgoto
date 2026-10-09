# -*- coding: utf-8 -*-
"""Planilha de eventos faturados do orçado SUP (Sup, Rubrica, meses): quantidade informada no lugar de R$ ÷ ticket."""
import os

import openpyxl
import pytest

from dados_sinteticos import gera_pasta
from faturamento import Sessao


def _planilha_eventos(pasta):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Sup", "Rubrica", "set/26", "out/26"])
    ws.append(["LAGOS", "Fat. Bruto de água - Indireto", "=SUM(C3:C6)", None])     # total: ignorado (soma das classes)
    for rub, v in (("CORTE", 1544), ("RELIGAÇÃO", 1326), ("LNA", 197), ("SANÇÃO", 235)):
        ws.append(["LAGOS", rub, v, v * 2])
    ws.append(["LESTE", "CORTE", 100, None])
    wb.save(os.path.join(pasta, "Orçado SUP - Eventos Indiretos Faturados.xlsx"))


@pytest.fixture(scope="module")
def sessao(tmp_path_factory):
    pasta = str(tmp_path_factory.mktemp("eventos"))
    gera_pasta(pasta, com_dre=True)
    _planilha_eventos(pasta)
    s = Sessao(pasta, progresso=lambda p, t: None)
    s.preparar()
    s.continuar()
    return s


def test_planilha_de_eventos_e_reconhecida(sessao):
    ctx = sessao.ctx
    assert len(ctx.classificacao["orcado_eventos"]) == 1
    assert all("Eventos" not in nome for nome in ctx.orcado)              # não vira mais um orçado em R$
    assert any(b["tipo"] == "Orçado SUP — eventos" for b in ctx.bases_info)


def test_orcado_sup_em_eventos_usa_a_quantidade_da_planilha(sessao):
    from faturamento.previsao import eventos_indiretas
    ctx = sessao.ctx
    sup = [f for f, i in ctx.orcado.items() if i["tipo"] == "sup"][0]
    rf = [f for f, i in ctx.orcado.items() if i["tipo"] == "rf"][0]
    ev = eventos_indiretas(ctx, "LAGOS", "09/2026")
    o = ev["orcado"][sup]
    assert o["ev_ri_CORTE"] == 1544 and o["ev_ri_RELIGAÇÃO"] == 1326 and o["ev_ri_LNA"] == 197 and o["ev_ri_SANÇÃO"] == 235
    assert o["ev_iA"] == pytest.approx(1544 + 1326 + 197 + 235 + (o["ev_ri_OUTROS"] or 0))   # total = soma das classes
    # classe sem número na planilha e o orçado RF continuam com R$ ÷ ticket
    r = ev["orcado"][rf]
    assert r["ev_ri_CORTE"] != 1544
    # Todas as superintendências soma LAGOS + LESTE
    assert eventos_indiretas(ctx, "TODAS", "09/2026")["orcado"][sup]["ev_ri_CORTE"] == 1644


def test_nota_da_tabela_cita_a_planilha(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert "usam a quantidade da planilha" in html and "Eventos Indiretos Faturados" in html
