# -*- coding: utf-8 -*-
"""Coluna "Situação" das tabelas da aba Diretas: Liberado / Em Análise / LIS / Aguardando."""
import datetime as dt
import re

import pandas as pd
import pytest

from dados_sinteticos import gera_pasta
from faturamento import Sessao


@pytest.fixture(scope="module")
def sessao(tmp_path_factory):
    pasta = str(tmp_path_factory.mktemp("sitgrupo"))
    gera_pasta(pasta, n_meses=2, grupos_faltando=3)          # grupos 06, 07 e 08 ainda sem fatura no mês
    s = Sessao(pasta, progresso=lambda p, t: None)
    s.ctx.data_corte = dt.date(2026, 9, 10)                    # hoje = 11/09: o cronograma lê o grupo 07 (dia 11)
    s.preparar()
    s.continuar()
    return s


def test_regras_da_situacao(sessao):
    from faturamento.situacao_grupo import situacao_dos_grupos
    ctx = sessao.ctx
    sit = situacao_dos_grupos(ctx)
    assert sit["7"] == "LIS" and sit["8"] == "Aguardando" and sit["6"] == "Aguardando"     # 06: dia já passou, sem nenhuma linha
    at = ctx.df_atual[ctx.df_atual["Grupo"].astype(str).str.lstrip("0").isin(["1", "2", "3", "4", "5"])]
    analise = set(at.loc[at["Situacao Conta"] == "EM ANALISE", "Grupo"].astype(str).str.lstrip("0"))
    for g in ("1", "2", "3", "4", "5"):
        assert sit[g] == ("Em Análise" if g in analise else "Liberado"), g
    assert analise and len(analise) < 5                        # os dados têm os dois casos


def test_coluna_situacao_nas_tabelas_de_diretas(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    diretas = html[html.index('id="view-tabelas"'):html.index('id="view-analise"')]
    tab = diretas[diretas.index('id="tabela-agua"'):]
    tab = tab[:tab.index("</table>")]
    assert '<th rowspan="2" title="LIS' in tab and ">Situação</th>" in tab
    linhas = re.findall(r'<tr class="([^"]*)" data-grupo="([^"]*)"', tab)
    pend = [g for c, g in linhas if c == "linha-pendente"]
    assert pend == ["06", "07", "08"]                          # LIS e Aguardando aparecem sem valores
    assert re.search(r'data-grupo="07"><td data-field="grupo">07</td><td data-field="situacao"><span class="sit-grupo sit-lis">LIS</span>', tab)
    assert 'sit-liberado">Liberado</span>' in tab and 'sit-analise">Em Análise</span>' in tab
    # linha pendente não tem valores: o total do JS continua só com os grupos comparados
    p = tab[tab.index('class="linha-pendente"'):]
    assert "data-fat-atual" not in p[:p.index("</tr>")]


def test_grupo_lido_so_no_consumo_usa_a_situacao_do_consumo():
    from faturamento.situacao_grupo import resumo_situacao_conta
    cons = pd.DataFrame({"Grupo_consumo": ["9", "9", "10"], "Referência": ["09/2026"] * 3,
                         "Situacao Conta": ["LIBERADA", "EM ANALISE", "LIBERADA"]})
    r = resumo_situacao_conta(cons, "Grupo_consumo", "Referência").set_index("g")
    assert bool(r.loc["9", "em_analise"]) and not bool(r.loc["10", "em_analise"]) and bool(r.loc["10", "liberada"])
