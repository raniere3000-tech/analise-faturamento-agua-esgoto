# -*- coding: utf-8 -*-
"""Forecast das diretas por grupo: economias × volume por economia × tarifa, com tendência do mês e backtest."""
import datetime as dt

import pytest

from dados_sinteticos import gera_pasta
from faturamento import Sessao
from faturamento.projecao_grupos import base_do_grupo, projeta


def _h(d, eco, vol):
    return {"dA": d, "ecoA": eco, "volA": vol, "dE": d * 0.8, "ecoE": eco, "volE": vol}


def test_base_do_grupo_media_ponderada():
    b = base_do_grupo([_h(100, 10, 20), _h(300, 20, 60)], "A")      # pesos 1/3 (mais antigo) e 2/3 (mais recente)
    assert b["eco"] == pytest.approx(10 / 3 + 20 * 2 / 3)
    assert b["vme"] == pytest.approx(2 / 3 + 3 * 2 / 3)               # m³/economia: 2 e 3
    assert b["tar"] == pytest.approx(5.0)                               # R$/m³: 5 e 5


def test_tendencia_dos_grupos_lidos_vai_para_os_que_faltam():
    hist = {"07/2026": {"01": _h(100, 10, 20), "02": _h(100, 10, 20)},
            "08/2026": {"01": _h(100, 10, 20), "02": _h(100, 10, 20)}}
    atual = {"01": _h(90, 10, 18)}                       # grupo 01 caiu 10% no volume
    r = projeta(hist, ["07/2026", "08/2026"], atual, ["02"], ["01"])
    f = r["fatores"]["A"]
    assert f["bruto"]["vme"] == pytest.approx(0.9) and f["confianca"] == pytest.approx(0.5)
    assert f["aplicado"]["vme"] == pytest.approx(0.95)    # puxado para 1 pela confiança
    assert r["total"]["volA"] == pytest.approx(20 * 0.95) and r["total"]["dA"] == pytest.approx(100 * 0.95)
    lo, hi = r["faixa"]["dA"]
    assert lo <= r["total"]["dA"] <= hi


@pytest.fixture(scope="module")
def seis_meses(tmp_path_factory):
    pasta = str(tmp_path_factory.mktemp("seis"))
    gera_pasta(pasta, com_dre=True, n_meses=6, grupos_faltando=3, tendencia_atual=0.9)
    s = Sessao(pasta, progresso=lambda p, t: None)
    s.ctx.data_corte = dt.date(2026, 9, 15)
    s.preparar()
    s.continuar()
    return s


def test_forecast_com_seis_meses_capta_queda_e_tem_backtest(seis_meses):
    from faturamento.previsao import calcula_previsao
    d = calcula_previsao(seis_meses.ctx, "TODAS")
    assert len(d["refs_hist"]) == 5 and d["faltam"] == ["06", "07", "08"]
    assert d["projecao"]["fatores"]["A"]["bruto"]["vme"] < 0.97          # consumo do mês 10% menor
    assert d["projecao"]["fatores"]["A"]["aplicado"]["vme"] < 1
    assert d["falta"]["dA"] == pytest.approx(d["projecao"]["total"]["dA"]) and d["falta"]["dA"] > 0
    assert len(d["backtest"]) == 3 and all(l["faltam"] == ["06", "07", "08"] for l in d["backtest"])
    html = open(seis_meses.caminho_html, encoding="utf-8").read()
    dados = html[html.index('id="view-dados"'):]
    for trecho in ("grupo × tendência do mês", "Fator aplicado", "Faixa provável", "backtest", "Erro médio absoluto"):
        assert trecho in dados
