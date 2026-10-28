# -*- coding: utf-8 -*-
"""Filtro de mês do painel: a análise inteira refeita para um mês passado (comparativo com o mês anterior a ele) e o
orçado SUP sem o mês comparado pelo RF mais recente."""
import json
import re

import pytest

from dados_sinteticos import gera_pasta
from faturamento import Sessao, dre

# trechos que mudam a cada geração (datas, arquivos compactados/Excel embutidos)
_limpa = lambda h: re.sub(r"[A-Za-z0-9+/=]{300,}", "B64", re.sub(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}(:\d{2})?", "", h))


@pytest.fixture(scope="module")
def pasta(tmp_path_factory):
    destino = tmp_path_factory.mktemp("filtro_mes") / "dados"
    gera_pasta(str(destino), com_dre=True, n_meses=4, n_ligacoes=120, n_grupos=4)
    return str(destino)


def _sessao(pasta):
    s = Sessao(pasta, progresso=lambda pct, desc: None)
    s.preparar()
    return s


def _info(html):
    return json.loads(re.search(r'id="info-filtros">(.*?)</script>', html).group(1))


def test_mes_passado_igual_a_rodar_so_aquele_mes_e_volta(pasta):
    s = _sessao(pasta)
    assert s.continuar() == ("09/2026", "08/2026")
    h_set = open(s.caminho_html, encoding="utf-8").read()
    assert s.continuar(ref="07/2026") == ("07/2026", "06/2026")       # comparativo com o mês anterior ao escolhido
    h_jul = open(s.caminho_html, encoding="utf-8").read()
    inf = _info(h_jul)
    assert inf["mesAtual"] == "07/2026" and [m["ref"] for m in inf["meses"]][-1] == "07/2026"   # nada depois de julho
    assert "Comparativo Água Mês a Mês" in h_jul and "Jul/26" in h_jul and "Set/26" not in h_jul
    direto = _sessao(pasta)
    direto.continuar(ref="07/2026")
    assert _limpa(open(direto.caminho_html, encoding="utf-8").read()) == _limpa(h_jul)
    s.continuar()                                                     # de volta ao mês mais recente: igual ao primeiro
    assert _limpa(open(s.caminho_html, encoding="utf-8").read()) == _limpa(h_set)


def test_orcado_sup_sem_o_mes_usa_o_rf_mais_recente(pasta):
    s = _sessao(pasta)
    s.continuar()
    ctx = s.ctx
    sup, rfs = dre.fontes_sup(ctx)[0], dre.fontes_rf(ctx)
    assert sorted(rfs, key=dre._ordem_rf)[-1] == "RF01T26"            # RF01T26 (2026) é mais novo que RF3T25 (2025)
    d = ctx.orcado[sup]["dados"]
    ctx.orcado[sup]["dados"] = d[d["Referencia"] != "09/2026"]        # SUP sem setembro
    assert dre.fonte_substituta(ctx, sup, "09/2026") == "RF01T26"
    assert dre.orcado(ctx, sup, dre.TODAS, "09/2026") == dre.orcado(ctx, "RF01T26", dre.TODAS, "09/2026")
    assert "(= RF01T26)" in dre.rotulo_fonte(ctx, sup, "09/2026")
    assert dre.fonte_substituta(ctx, sup, "08/2026") is None           # mês com orçado SUP: continua o dele
    assert dre.fonte_substituta(ctx, "RF01T26", "09/2026") is None
