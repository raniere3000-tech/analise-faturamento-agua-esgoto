# -*- coding: utf-8 -*-
"""Export "Acompanhamento Mensal": tabelas da planilha semanal e indiretas divididas por semana."""
import datetime as dt
import io
import os

import openpyxl
import pytest

from dados_sinteticos import gera_pasta
from faturamento import Sessao
from faturamento.acompanhamento import calendario, dados_acompanhamento, distribui, gera_xlsx, nome_arquivo


def test_calendario_corte_sem_sextas_e_vesperas():
    dias = calendario("10/2026")
    assert len(dias) == 21                                        # 12/10 é feriado
    corte = {d: c for d, c in dias}
    assert corte[dt.date(2026, 10, 2)] is False                    # sexta
    assert corte[dt.date(2026, 10, 9)] is False                    # sexta (e véspera do fim de semana do feriado)
    assert corte[dt.date(2026, 10, 1)] is True


def test_realizado_da_semana_dividido_pelos_dias_e_resto_pelos_dias_que_faltam():
    dias = calendario("10/2026")
    corte = dt.date(2026, 10, 8)
    fotos = [(dt.date(2026, 10, 2), 300.0)]                        # export da 1ª semana: 300 acumulados até 02/10
    r = distribui(dias, corte, fotos, 1000.0, 5000.0, so_corte=False)
    assert r[dt.date(2026, 10, 1)] == (150.0, 150.0) and r[dt.date(2026, 10, 2)] == (150.0, 150.0)   # 300 ÷ 2 dias
    assert r[dt.date(2026, 10, 5)][1] == pytest.approx(700 / 4)    # 2ª semana: 700 ÷ 4 dias (05 a 08)
    futuros = [d for d, _ in dias if d > corte]
    assert r[futuros[0]] == (pytest.approx(4000 / len(futuros)), None)
    assert sum(o for o, _ in r.values()) == pytest.approx(5000)   # orçado do mês preservado
    rc = distribui(dias, corte, [], 500.0, 2000.0, so_corte=True)
    assert rc[dt.date(2026, 10, 2)] == (0.0, 0.0) and rc[dt.date(2026, 10, 16)][0] == 0.0     # sexta não tem corte


@pytest.fixture(scope="module")
def sessao(tmp_path_factory):
    pasta = str(tmp_path_factory.mktemp("acomp"))
    gera_pasta(pasta, com_dre=True, n_meses=3)
    s = Sessao(pasta, progresso=lambda p, t: None)
    s.ctx.data_corte = dt.date(2026, 9, 10)
    s.preparar()
    s.continuar()
    return s


def test_arquivo_com_uma_aba_por_tabela(sessao):
    dados = dados_acompanhamento(sessao.ctx, "INTERIOR")
    assert dados["fonte"] and dados["linhas"]
    conteudo, foto = gera_xlsx(dados, [])
    wb = openpyxl.load_workbook(io.BytesIO(conteudo))
    assert wb.sheetnames == ["Leia-me", "1 Faturamento", "2 Cancelamento", "3 Economias Água", "4 Volume Água",
                             "5 Economias Esgoto", "6 Volume Esgoto", "7 Indiretas R$", "8 Indiretas Qtd"]
    assert foto["ate"] == "2026-09-10" and set(foto["valor"]) == {"CORTE", "RELIGAÇÃO", "LNA", "SANÇÃO", "LNE"}
    assert nome_arquivo(dados) == "Acompanhamento_Interior_09-2026_ate_10-09.xlsx"
    worker = open(os.path.join(os.path.dirname(__file__), "..", "analisador.worker.js"), encoding="utf-8").read()
    assert '"faturamento/acompanhamento.py"' in worker and 'fase === "acompanhamento"' in worker
    site = open(os.path.join(os.path.dirname(__file__), "..", "index.html"), encoding="utf-8").read()
    assert 'id="btnAcomp"' in site and "d.acompanhamento" in site


def test_faturamento_por_ciclo_usa_o_rf_mais_recente(sessao):
    from faturamento.acompanhamento import rf_mais_recente
    from faturamento.dre import orcado
    assert rf_mais_recente(["RF01T26", "RF02T26", "RF3T25"]) == "RF02T26"
    dados = dados_acompanhamento(sessao.ctx, "INTERIOR")
    assert dados["fonte_rf"] == "RF01T26"                         # nos dados de teste: RF01T26 e RF3T25
    rf = orcado(sessao.ctx, "RF01T26", "INTERIOR")
    assert sum(l["orcA"] for l in dados["linhas"]) == pytest.approx(rf["dA"])
    assert sum(l["orcE"] for l in dados["linhas"]) == pytest.approx(rf["dE"])
