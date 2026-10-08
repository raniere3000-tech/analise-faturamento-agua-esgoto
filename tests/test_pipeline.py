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
    for trecho in ("Comparativo Água Mês a Mês", "Comparativo Esgoto Mês a Mês", "Matriz de migração de grupos",
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
    assert "tabela-previsao" in html and "Forecast de fechamento" in html


def test_kpi_faturamento_total_antes_de_agua_e_esgoto(sessao_pipeline=None):
    import pandas as pd
    from faturamento.painel_html import gera_cards_kpis_html
    df = pd.DataFrame([{"FatAgua_Atual": 100.0, "FatAgua_Anterior": 80.0, "FatEsgoto_Atual": 50.0, "FatEsgoto_Anterior": 40.0,
                        "Eco_Atual": 10, "Eco_Anterior": 10, "VolFat_Atual": 5, "VolFat_Anterior": 5, "Acima_Atual": 1, "Acima_Ant": 1}])
    h = gera_cards_kpis_html(df)
    assert h.index("Faturamento Total") < h.index("Faturamento Água") < h.index("Faturamento Esgoto")
    assert "R$ 150,00" in h


def test_dias_uteis_e_forecast_das_indiretas():
    import datetime as dt
    from faturamento.previsao import dias_uteis_do_mes, feriados
    assert dt.date(2026, 10, 12) in feriados(2026) and dt.date(2026, 4, 3) in feriados(2026)   # 12/10 e Sexta Santa
    d = dias_uteis_do_mes("10/2026", dt.date(2026, 10, 5))     # hoje 06/10, dados até D-1
    assert d == {"uteis": 21, "uteis_decorridos": 3, "uteis_faltam": 18, "corte": 16, "corte_decorridos": 2, "corte_faltam": 14}
    assert dt.date(2026, 2, 16) not in feriados(2026) and dt.date(2026, 6, 4) not in feriados(2026)   # facultativos contam como úteis
    # mês fechado: nada falta; mês futuro: nada decorrido
    assert dias_uteis_do_mes("10/2026", dt.date(2026, 11, 5))["uteis_faltam"] == 0
    assert dias_uteis_do_mes("10/2026", dt.date(2026, 9, 1))["uteis_decorridos"] == 0


def test_top100_aumento_de_consumo_com_download(analise):
    import base64, io, re
    html = open(analise.caminho_html, encoding="utf-8").read()
    diretas = html[html.index('id="view-tabelas"'):html.index('id="view-analise"')]
    assert "Top 100 clientes" not in diretas and "Economias faturadas por ciclo" not in diretas   # foram para a aba Análise
    tab = html[html.index('id="view-analise"'):]
    i = tab.index("Top 100 clientes com maior aumento de consumo — Água")
    assert tab.index("Top 100 clientes com maior queda de consumo — Esgoto") < i
    assert i < tab.index("Top 100 clientes com maior aumento de consumo — Esgoto")
    # uma seta por tabela: água e esgoto (quedas e aumentos) baixam cada uma a sua lista
    for arquivo, aba in (("Top100_Aumentos_Agua.xlsx", "Top100_Aumento_Agua"), ("Top100_Aumentos_Esgoto.xlsx", "Top100_Aumento_Esgoto")):
        b64 = re.search(r'data-arquivo="' + arquivo + r'" [^>]*data-b64="([^"]+)"', tab).group(1)
        xls = pd.ExcelFile(io.BytesIO(base64.b64decode(b64)))
        assert xls.sheet_names == [aba]
        df = pd.read_excel(xls, sheet_name=aba)
        assert len(df) <= 100 and (df["Aumento_Consumo"] > 0).all()
        assert df["Aumento_Consumo"].is_monotonic_decreasing
    for arquivo in ("Top100_Quedas_Agua.xlsx", "Top100_Quedas_Esgoto.xlsx"):
        assert f'data-arquivo="{arquivo}"' in tab


def test_delta_faturamento_sem_casas_decimais(analise):
    import re
    html = open(analise.caminho_html, encoding="utf-8").read()
    deltas = re.findall(r'<td data-field="delta-fat"[^>]*>([^<]+)</td>', html)
    assert deltas and all("," not in d for d in deltas)


def test_minimo_vetorizado_igual_a_regra_linha_a_linha(analise):
    import numpy as np
    from faturamento.analises import calcula_minimo_matricula, minimo_matricula_vetorizado
    from faturamento.config import MINIMO_POR_TIPO_ECONOMIA
    df = analise.ctx.base_final.copy()
    for c in MINIMO_POR_TIPO_ECONOMIA:
        df[c] = pd.to_numeric(df.get(c, 0), errors="coerce").fillna(0)
    df.loc[df.index[:5], list(MINIMO_POR_TIPO_ECONOMIA)[:2]] = 1           # algumas ligações mistas
    linha = df.apply(calcula_minimo_matricula, axis=1).astype(float)
    vetor = minimo_matricula_vetorizado(df)
    assert np.allclose(linha.fillna(-1), vetor.fillna(-1))


def test_etapa2_mostra_economias_das_ligacoes(tmp_path):
    import json
    from dados_sinteticos import gera_pasta
    from faturamento import Sessao
    gera_pasta(str(tmp_path))
    s = Sessao(str(tmp_path), progresso=lambda p, t: None)
    info = s.preparar()
    linhas = info["linhas"]
    assert linhas and all("economias" in l for l in linhas)
    assert sum(l["economias"] for l in linhas) > 0
    json.dumps(linhas, allow_nan=False)                       # vai em JSON para o site: sem NaN


def test_etapa2_mes_anterior_e_totais_por_grupo(tmp_path):
    import json
    from dados_sinteticos import gera_pasta
    from faturamento import Sessao
    gera_pasta(str(tmp_path))
    s = Sessao(str(tmp_path), progresso=lambda p, t: None)
    info = s.preparar()
    json.dumps(info, allow_nan=False)
    assert info["refAnterior"] == "08/2026"
    assert all("consumo_ant" in l and "valor_ant" in l for l in info["linhas"])
    assert any(l["valor_ant"] for l in info["linhas"])
    grupos = {g["grupo"]: g for g in info["grupos"]}
    assert grupos and all(g["valor"] > 0 and g["ligacoes"] > 0 for g in grupos.values())
    # cada ligação da conferência está dentro do total do seu grupo
    for l in info["linhas"]:
        assert grupos[l["grupo"]]["valor"] >= l["valor"] - 0.01
    # total dos grupos = valor do mês inteiro (todas as ligações)
    b = s.ctx.base_final
    mes = b[b["Referencia de Leitura"] == info["refAtual"]]
    assert sum(g["valor"] for g in grupos.values()) == pytest.approx(pd.to_numeric(mes["Valor (R$)"]).sum(), rel=1e-6)
