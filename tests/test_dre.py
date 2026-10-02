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
    assert len(c["orcado"]) == 2


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
    rf = dre.orcado(sessao.ctx, "rf", dre.TODAS)
    sup_total = dre.orcado(sessao.ctx, "sup", dre.TODAS)
    lagos, leste = (dre.orcado(sessao.ctx, "sup", s) for s in ("LAGOS", "LESTE"))
    assert rf["bruto"] == pytest.approx(1000 * 10 * 9)           # coluna set/26 = 9º mês
    assert sup_total["bruto"] == pytest.approx(lagos["bruto"] + leste["bruto"])
    assert not any(v is not None for v in dre.orcado(sessao.ctx, "rf", "LAGOS").values())   # o RF só tem a linha Interior


def test_relatorio_tem_abas_e_nao_tem_download(sessao):
    with open(sessao.caminho_html, encoding="utf-8") as f:
        html = f.read()
    for trecho in ('id="btn-dre"', ">Diretas</button>", 'id="btn-indiretas"', 'data-sup="LAGOS"', "ORÇADO - SUP", "Δ R$ (Orçado Sup)"):
        assert trecho in html
    assert "RUBRICA NOVA SEM CLASSE" in html                      # aviso de rubrica fora da relação


def test_sem_arquivos_de_dre_o_relatorio_avisa(analise):
    with open(analise.caminho_html, encoding="utf-8") as f:
        html = f.read()
    assert "Nenhum arquivo de serviço avulso" in html
    assert "Orçado RF não encontrado" in html
