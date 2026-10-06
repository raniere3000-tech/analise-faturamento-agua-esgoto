# -*- coding: utf-8 -*-
"""Aba DRE / Indiretas: realizado (diretas, indiretas, cancelamento), orçado RF/SUP e visão por SUP."""
import os

import pandas as pd
import pytest

from dados_sinteticos import gera_pasta
from faturamento import Sessao, dre
from faturamento.config import CLASSE_INDIRETA_POR_RUBRICA, chave_texto


@pytest.fixture(scope="module")
def sessao(tmp_path_factory):
    destino = tmp_path_factory.mktemp("dre") / "dados"
    gera_pasta(str(destino), com_dre=True)
    s = Sessao(str(destino), progresso=lambda pct, desc: None)
    s.preparar()
    s.continuar()
    return s


def le_avulso(pasta):
    df = pd.read_csv(os.path.join(pasta, "Servico avulso 09-2026.csv"), sep=";", encoding="utf-8-sig", dtype=str)
    df["valor"] = df["Valor Parcela"].str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)
    df["classe"] = df["Rubrica"].map(lambda r: CLASSE_INDIRETA_POR_RUBRICA.get(chave_texto(r), "OUTROS"))
    return df[df["Referencia de Leitura"] == "set/26"]


def test_arquivos_novos_sao_classificados(sessao):
    c = sessao.ctx.classificacao
    assert len(c["avulso"]) == 1 and len(c["fatura"]) == 1      # o avulso não pode ser lido como fatura
    assert len(c["orcado"]) == 3


def test_indiretas_conferem_com_a_planilha(sessao):
    av = le_avulso(os.path.dirname(sessao.caminho_html))
    esperado = av[av["classe"] != "EXCLUIR"].groupby("classe")["valor"].sum()
    r = dre.realizado(sessao.ctx, dre.TODAS)
    assert r["iE"] == pytest.approx(esperado["LNE"])
    assert r["iA"] == pytest.approx(esperado.drop("LNE").sum())
    assert r["ri_CORTE"] == pytest.approx(esperado["CORTE"])


def test_rubrica_com_acento_quebrado_e_classificada():
    assert CLASSE_INDIRETA_POR_RUBRICA[chave_texto("COBRANÃ‡A DE PARCELAS")] == "EXCLUIR"
    assert CLASSE_INDIRETA_POR_RUBRICA[chave_texto("ACRÃ‰SCIMOS MANDADO JUDICIAL")] == "SANÇÃO"
    assert chave_texto("LIG. AGUA 3/4\" - VAZAO 3MÂ³/H - ASFALTO") == chave_texto("LIG. AGUA 3/4\" - VAZAO 3M³/H - ASFALTO")


def test_bruto_e_soma_de_diretas_e_indiretas(sessao):
    r = dre.realizado(sessao.ctx, dre.TODAS)
    assert r["bruto"] == pytest.approx(r["dA"] + r["dE"] + r["iA"] + r["iE"])
    assert r["dTot"] == pytest.approx(r["dA"] + r["dE"])


def test_sups_somam_o_total(sessao):
    sups = dre.lista_sups(sessao.ctx)
    assert sups[0] == dre.TODAS and {"LAGOS", "LESTE"} <= set(sups)
    total = dre.realizado(sessao.ctx, dre.TODAS)
    for chave in ("bruto", "iA", "iE", "canc", "ecoA", "volA"):
        assert sum(dre.realizado(sessao.ctx, s)[chave] for s in sups[1:]) == pytest.approx(total[chave])


def test_cancelamento_vem_da_fatura(sessao):
    pasta = os.path.dirname(sessao.caminho_html)
    df = pd.read_excel(os.path.join(pasta, "Fatura.xlsx"), dtype=str)
    df = df[df["Rubrica"].isin(["DESCONTO", "ABATIMENTO - M3", "IR MUNICIPAL"]) & (df["Referencia de Leitura"] == "15/09/2026")]
    soma = df["Valor Parcela"].str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float).sum()
    assert dre.realizado(sessao.ctx, dre.TODAS)["canc"] == pytest.approx(soma)


def test_orcado_rf_e_sup(sessao):
    ctx = sessao.ctx
    assert set(ctx.orcado) == {"RF01T26", "RF3T25", "RF SUP"}
    rf = dre.orcado(ctx, "RF01T26", dre.TODAS)
    sup_total = dre.orcado(ctx, "RF SUP", dre.TODAS)
    lagos, leste = (dre.orcado(ctx, "RF SUP", s) for s in ("LAGOS", "LESTE"))
    assert rf["bruto"] == pytest.approx(1000 * 10 * 9)           # coluna set/26 = 9º mês
    assert sup_total["bruto"] == pytest.approx(lagos["bruto"] + leste["bruto"])
    # no orçado, "Interior" é a superintendência LAGOS
    assert dre.orcado(ctx, "RF01T26", "LAGOS")["bruto"] == pytest.approx(rf["bruto"])
    assert not any(v is not None for v in dre.orcado(ctx, "RF01T26", "LESTE").values())


def test_rf_antigo_com_linhas_numeradas_e_meses_soma_de(sessao):
    antigo = dre.orcado(sessao.ctx, "RF3T25", dre.TODAS)          # set/26 = 9 × valor-base
    assert antigo["dA"] == pytest.approx(18000) and antigo["dE"] == pytest.approx(9000)
    assert antigo["canc"] == pytest.approx(-2700) and antigo["ecoA"] == pytest.approx(450) and antigo["volA"] == pytest.approx(6300)
    assert antigo["bruto"] == pytest.approx(27000)                # sem linha "Faturamento Bruto": soma das partes


def test_opcoes_de_referencia_comparam_rf_com_rf_sup(sessao):
    valores = [v for v, _ in dre.opcoes_referencia(sessao.ctx)]
    assert {"RF01T26|RF SUP", "RF3T25|RF SUP", "cmp:RF01T26|RF SUP", "cmp:RF3T25|RF SUP", "RF01T26", "RF3T25", "RF SUP"} <= set(valores)


def test_relatorio_tem_abas_e_nao_tem_download(sessao):
    with open(sessao.caminho_html, encoding="utf-8") as f:
        html = f.read()
    for trecho in ('id="btn-dre"', ">Diretas</button>", 'id="btn-indiretas"', 'data-sup="LAGOS"', "Orçado<br>RF SUP", "Orçado<br>RF3T25"):
        assert trecho in html
    assert "RUBRICA NOVA SEM CLASSE" in html                      # aviso de rubrica fora da relação


def test_sem_arquivos_de_dre_o_relatorio_avisa(analise):
    with open(analise.caminho_html, encoding="utf-8") as f:
        html = f.read()
    assert "Nenhum arquivo de serviço avulso" in html
    assert "Orçado RF não encontrado" in html


def test_blocos_por_mes_e_sup(sessao):
    with open(sessao.caminho_html, encoding="utf-8") as f:
        html = f.read()
    for mes in ("08/2026", "09/2026"):
        for sup in ("TODAS", "LAGOS", "LESTE", "SEM SUP"):
            assert f'data-sup="{sup}" data-mes="{mes}"' in html
    assert 'id="info-filtros"' in html and "Evolução mensal por classe" in html and "Ticket médio" in html


def test_dre_do_mes_anterior(sessao):
    ctx = sessao.ctx
    r = dre.realizado(ctx, dre.TODAS, "08/2026")
    av = le_avulso(os.path.dirname(sessao.caminho_html))
    ago = pd.read_csv(os.path.join(os.path.dirname(sessao.caminho_html), "Servico avulso 09-2026.csv"), sep=";", encoding="utf-8-sig", dtype=str)
    ago = ago[ago["Referencia de Leitura"] == "ago/26"]
    valores = ago["Valor Parcela"].str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)
    classes = ago["Rubrica"].map(lambda x: CLASSE_INDIRETA_POR_RUBRICA.get(chave_texto(x), "OUTROS"))
    assert r["iE"] == pytest.approx(valores[classes == "LNE"].sum())
    assert r["dA"] != dre.realizado(ctx, dre.TODAS)["dA"]
    assert dre.lista_meses(ctx) == ["08/2026", "09/2026"] and len(av) > 0


def test_aba_dados_lista_bases_avisos_e_mapeamento(sessao):
    with open(sessao.caminho_html, encoding="utf-8") as f:
        html = f.read()
    i = html.index('id="view-dados"')
    dados = html[i:i + 20000]
    for trecho in ("Bases carregadas", "Servico avulso 09-2026.csv", "RF01T26.xlsx", "Fat. Bruto de água - Direto", "DIRETAS ÁGUA",
                   "RUBRICA NOVA SEM CLASSE"):
        assert trecho in dados
    assert "avisos-card" not in html.split('id="view-dre"')[1].split('id="view-dados"')[0]   # DRE sem caixa de avisos


def test_rolagem_da_pagina_sobre_a_tabela():
    from faturamento.relatorio import carrega_asset
    assert "'wheel'" not in carrega_asset("relatorio.js")      # a roda do mouse não pode ser capturada pela tabela


def test_forecast_em_aba_propria_e_comparacao_entre_duas_planilhas(tmp_path):
    from faturamento import Sessao
    from dados_sinteticos import gera_pasta
    gera_pasta(str(tmp_path), com_dre=True)
    s = Sessao(str(tmp_path), progresso=lambda p, t: None)
    s.preparar()
    s.continuar()
    html = open(s.caminho_html, encoding="utf-8").read()
    assert 'id="view-forecast"' in html and 'id="btn-forecast"' in html
    i, j = html.index('id="view-forecast"'), html.index('id="view-dados"')
    assert "tabela-previsao" in html[i:j]
    assert "tabela-previsao" not in html[html.index('id="view-dre"'):html.index('id="view-forecast"')]
    # qualquer par de planilhas de orçado tem colunas de diferença (ex.: RF01T26 × RF3T25)
    assert 'data-combo' not in html[html.index('id="view-dre"'):html.index('id="view-forecast"')]
    assert '"fontes"' in html


def test_metas_ri_do_rf_e_sem_delta_entre_orcados_nas_indiretas(tmp_path):
    import pandas as pd
    from faturamento import Sessao
    from faturamento.dre import orcado
    from dados_sinteticos import gera_pasta
    gera_pasta(str(tmp_path), com_dre=True)
    rf = tmp_path / "RF01T26.xlsx"
    df = pd.read_excel(rf)
    meses = [c for c in df.columns if c not in ("Sup", "Rubrica")]
    extras = [("RI Cortes/Recorte", 10), ("RI Religações", 20), ("RI Ligações - Água", 30), ("RI Fiscalização", 40), ("RI Outros - Água", 50)]
    df = df[df["Rubrica"] != "RI Cortes/Recorte"]
    linhas = [{"Sup": "Interior", "Rubrica": r, **{m: v for m in meses}} for r, v in extras]
    pd.concat([df, pd.DataFrame(linhas)]).to_excel(rf, index=False)
    s = Sessao(str(tmp_path), progresso=lambda p, t: None)
    s.preparar()
    s.continuar()
    o = orcado(s.ctx, "RF01T26", "TODAS")
    assert [o[k] for k in ("ri_CORTE", "ri_RELIGAÇÃO", "ri_LNA", "ri_SANÇÃO", "ri_OUTROS")] == [10, 20, 30, 40, 50]
    html = open(s.caminho_html, encoding="utf-8").read()
    ind = html[html.index('id="view-indiretas"'):html.index('id="view-tabelas"')]
    assert "data-combo" not in ind                      # sem Δ entre orçados nas Indiretas
    assert 'data-combo' not in html[html.index('id="view-dre"'):html.index('id="view-forecast"')]   # DRE também sem Δ entre orçados


def test_orcado_indiretas_com_rubrica_curta_e_valor_em_texto(tmp_path):
    import pandas as pd
    from faturamento import Sessao
    from faturamento.dre import orcado
    from dados_sinteticos import gera_pasta
    gera_pasta(str(tmp_path), com_dre=True)
    rf = tmp_path / "RF01T26.xlsx"
    df = pd.read_excel(rf)
    meses = [c for c in df.columns if c not in ("Sup", "Rubrica")]
    df = df[df["Rubrica"] != "RI Cortes/Recorte"]
    extras = [("CORTE", " R$ 226.713,01 "), ("RELIGAÇÃO", " R$ 184.837,03 "), ("LNA", " R$ 255.916,39 "), ("SANÇÃO", " R$ 359.404,46 ")]
    linhas = [{"Sup": "Interior", "Rubrica": r, **{m: v for m in meses}} for r, v in extras]
    pd.concat([df, pd.DataFrame(linhas)]).to_excel(rf, index=False)
    s = Sessao(str(tmp_path), progresso=lambda p, t: None)
    s.preparar()
    s.continuar()
    o = orcado(s.ctx, "RF01T26", "TODAS")
    assert o["ri_CORTE"] == pytest.approx(226713.01) and o["ri_SANÇÃO"] == pytest.approx(359404.46)
    assert o["ri_RELIGAÇÃO"] == pytest.approx(184837.03) and o["ri_LNA"] == pytest.approx(255916.39)


def test_dados_tem_conferencia_dos_kpis(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert "Conferência dos KPIs" in html and "Total (KPIs)" in html
