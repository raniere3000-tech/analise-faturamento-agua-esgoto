# -*- coding: utf-8 -*-
import os
import re

import pandas as pd
import pytest

from dados_sinteticos import NOME_MALICIOSO, gera_pasta
from faturamento import Sessao


def lê_html(sessao):
    with open(sessao.caminho_html, encoding="utf-8") as f:
        return f.read()


def soma_fatura(pasta_modelo, rubrica, referencia):
    """Recalcula, direto da planilha de fatura, o total de uma rubrica em um mês (conferência independente)."""
    df = pd.read_excel(os.path.join(pasta_modelo, "Fatura.xlsx"), dtype=str)
    df = df[(df["Rubrica"] == rubrica) & (df["Referencia de Leitura"] == referencia)]
    valores = df["Valor Parcela"].str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)
    return valores.sum()


def test_gera_os_arquivos_de_saida(analise):
    assert os.path.exists(analise.caminho_html)
    assert os.path.exists(analise.caminho_top100)
    abas = pd.ExcelFile(analise.caminho_top100).sheet_names
    assert abas == ["Top100_Agua", "Top100_Esgoto"]


def test_referencias(analise):
    assert (analise.ctx.ref_atual, analise.ctx.ref_anterior) == ("09/2026", "08/2026")
    assert analise.ctx.mes_atual == "Setembro/2026"
    assert analise.ctx.mes_anterior_curto == "Ago/26"


@pytest.mark.parametrize("rubrica,atributo", [("VALOR DE AGUA", "comp_agua"), ("VALOR DE ESGOTO", "comp_esgoto")])
def test_faturamento_confere_com_a_planilha(analise, pasta_modelo, rubrica, atributo):
    comp = getattr(analise.ctx, atributo)
    assert comp["Faturamento_atual"].sum() == pytest.approx(soma_fatura(pasta_modelo, rubrica, "15/09/2026"), rel=1e-9)
    assert comp["Faturamento_anterior"].sum() == pytest.approx(soma_fatura(pasta_modelo, rubrica, "15/08/2026"), rel=1e-9)


def test_comparativo_tem_todos_os_grupos(analise):
    assert len(analise.ctx.comp_agua) == 8
    assert sorted(analise.ctx.comp_agua["Grupo"]) == [f"{g:02d}" for g in range(1, 9)]


def test_top100_ordenado_por_queda(analise):
    for aba in ("Top100_Agua", "Top100_Esgoto"):
        df = pd.read_excel(analise.caminho_top100, sheet_name=aba)
        assert 0 < len(df) <= 100
        assert df["Queda_Consumo"].is_monotonic_decreasing
        assert (df["Queda_Consumo"] > 0).all()
        assert list(df["Ranking"]) == list(range(1, len(df) + 1))


def test_alerta_de_categoria_sem_minimo(analise):
    assert "CATEGORIA NOVA" in analise.ctx.categorias_sem_minimo
    html = lê_html(analise)
    assert "Categoria sem consumo mínimo cadastrado: CATEGORIA NOVA" in html     # aviso na aba Dados
    assert 'id="alerta-minimo"' not in html                                       # sem janela de alerta ao abrir


def test_html_tem_as_secoes_principais(analise):
    html = lê_html(analise)
    for trecho in ("Comparativo Água", "Comparativo Esgoto", "Matriz de migração de grupos",
                   "Economias acima x abaixo do consumo mínimo", "Top 100 clientes com maior queda de consumo",
                   "Setembro/2026 vs Agosto/2026"):
        assert trecho in html, trecho
    assert "__CHAVE_JUSTIFICATIVA__" not in html          # placeholder do JavaScript foi substituído
    assert "justificativas_Setembro_2026" in html


def test_top20_lista_so_contas_em_analise(pasta_pequena):
    sessao = Sessao(pasta_pequena, progresso=lambda p, d: None)
    top20 = sessao.preparar()
    assert top20["refAtual"] == "09/2026"
    assert top20["colunaSituacao"] == "Situacao Conta"
    assert top20["linhas"], "o gerador sempre cria algumas contas EM ANALISE"
    assert all(l["situacao"] == "EM ANALISE" for l in top20["linhas"])
    consumos = [l["consumo"] for l in top20["linhas"]]
    assert consumos == sorted(consumos, reverse=True)


def test_ajuste_do_top20_vale_so_para_o_mes_atual_e_avisa_no_relatorio(pasta_pequena):
    sessao = Sessao(pasta_pequena, progresso=lambda p, d: None)
    alvo = sessao.preparar()["linhas"][0]
    sessao.continuar([{"ligacao": alvo["ligacao"], "consumo": 12345.0, "valor": 999.0}])
    base = sessao.ctx.base_final
    atual = base[(base["N. Ligação"] == alvo["ligacao"]) & (base["Referencia de Leitura"] == "09/2026")]
    anterior = base[(base["N. Ligação"] == alvo["ligacao"]) & (base["Referencia de Leitura"] == "08/2026")]
    assert (pd.to_numeric(atual["Consumo Faturado"]) == 12345.0).all()
    assert pd.to_numeric(atual["Valor (R$)"]).sum() == pytest.approx(999.0)
    assert not (pd.to_numeric(anterior["Consumo Faturado"]) == 12345.0).any()
    assert "ajustados manualmente" in lê_html(sessao)


def test_nomes_de_clientes_sao_escapados_no_html(tmp_path):
    pasta = str(tmp_path / "dados")
    gera_pasta(pasta, n_ligacoes=60, n_grupos=3, injeta_cliente_html=True)
    sessao = Sessao(pasta, progresso=lambda p, d: None)
    sessao.preparar()
    sessao.continuar()
    html = lê_html(sessao)
    assert NOME_MALICIOSO not in html                      # nunca aparece "cru"
    assert "&lt;img src=x onerror=" in html                # aparece escapado (cliente está no Top 100)


def test_callback_de_progresso_vai_de_0_a_100(pasta_pequena):
    chamadas = []
    sessao = Sessao(pasta_pequena, progresso=lambda pct, desc: chamadas.append((pct, desc)))
    sessao.preparar()
    sessao.continuar()
    pcts = [c[0] for c in chamadas]
    assert pcts == sorted(pcts), "o progresso nunca pode andar para trás"
    assert pcts[-1] == 100.0
    assert re.search("Finalizado", chamadas[-1][1])


def test_mudar_regra_de_consumo_minimo_altera_a_classificacao(pasta_pequena, monkeypatch):
    from faturamento import analises
    sessao = Sessao(pasta_pequena, progresso=lambda p, d: None)
    sessao.preparar()
    sessao.continuar()
    antes = sessao.ctx.df_minimo_por_grupo[["Acima_Atual", "Abaixo_Atual"]].sum()
    monkeypatch.setitem(analises.CONSUMO_MINIMO_POR_CATEGORIA, "RESIDENCIAL", 10_000)   # ninguém passa de 10 mil m³
    sessao2 = Sessao(pasta_pequena, progresso=lambda p, d: None)
    sessao2.preparar()
    sessao2.continuar()
    depois = sessao2.ctx.df_minimo_por_grupo[["Acima_Atual", "Abaixo_Atual"]].sum()
    assert depois["Abaixo_Atual"] > antes["Abaixo_Atual"]


def test_limita_ao_ultimo_grupo_faturado(tmp_path):
    from faturamento import Sessao
    from dados_sinteticos import gera_pasta
    gera_pasta(str(tmp_path))
    s = Sessao(str(tmp_path), progresso=lambda p, t: None)
    s.preparar()
    b = s.ctx.base_final
    mais_recente = b["Referencia de Leitura"].max()
    b = b[~((b["Referencia de Leitura"] == mais_recente) & (b["Grupo"].astype(int) > 5))]
    s.ctx.base_final = b
    s.continuar()
    ctx = s.ctx
    assert ctx.ultimo_grupo == "05"
    assert ctx.base_final["Grupo"].astype(int).max() == 5
    assert set(ctx.comp_agua["Grupo"].astype(int)) <= {1, 2, 3, 4, 5}
    html = open(s.caminho_html, encoding="utf-8").read()
    assert "grupos até o 05" in html


def test_previsao_de_fechamento_projeta_grupos_que_faltam(tmp_path):
    from faturamento import Sessao
    from faturamento.previsao import calcula_previsao
    from dados_sinteticos import gera_pasta
    gera_pasta(str(tmp_path))
    s = Sessao(str(tmp_path), progresso=lambda p, t: None)
    s.preparar()
    b = s.ctx.base_final
    mais_recente = b["Referencia de Leitura"].max()
    s.ctx.base_final = b[~((b["Referencia de Leitura"] == mais_recente) & (b["Grupo"].astype(int) > 5))]
    s.continuar()
    r = calcula_previsao(s.ctx, "TODAS")
    assert r["faltam"] == ["06", "07", "08"]
    assert r["falta"]["dA"] > 0 and r["atual"]["dA"] > 0
    html = open(s.caminho_html, encoding="utf-8").read()
    assert "tabela-previsao" in html and "Previsão de fechamento" in html
