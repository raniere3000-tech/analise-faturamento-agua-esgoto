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
    dados = html[i:]
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


def test_tabelas_orcado_por_ciclo_acima_das_economias(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    tab = html[html.index('id="view-tabelas"'):]
    j = tab.index("Água por ciclo — Realizado × Orçado RF SUP")
    assert tab.index("Comparativo Esgoto Mês a Mês") < j < tab.index("Economias faturadas por ciclo")
    assert "Esgoto por ciclo — Realizado × Orçado RF SUP" in html and "Água por ciclo — Realizado × Orçado RF01T26" in html


def test_dados_tem_validacao_dos_calculos(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    dados = html[html.index('id="view-dados"'):]
    assert "validação dos cálculos" in dados and "btn-baixar" in dados
    # todos os tópicos recolhíveis e fechados ao abrir a aba
    for t in ("Avisos (", "Conferência dos KPIs", "Bases carregadas", "Orçado: linhas reconhecidas", "Bases para download",
              "1. Resumo", "2. Diretas", "3. Indiretas", "4. Forecast", "5. DRE"):
        assert f'<details class="val-aba"><summary>{t}' in dados, t
    assert '<details class="val-aba" open' not in dados
    pos = [dados.index(t) for t in ("1. Resumo", "2. Diretas", "3. Indiretas", "4. Forecast", "5. DRE")]
    assert pos == sorted(pos)


def test_diretas_tem_so_duas_tabelas_de_orcado_com_seletor(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    tab = html[html.index('id="view-tabelas"'):]
    assert 'id="selOrcCiclo"' in tab and "selecionarOrcadoCiclo" in html
    for f in ("RF01T26", "RF3T25", "RF SUP"):
        assert f'<option value="{f}">' in tab
    # cada planilha tem um par (Água e Esgoto); só o primeiro par aparece de início
    assert tab.count('class="orc-ciclo-bloco" data-orc-ciclo="RF01T26">') == 1
    assert tab.count('class="orc-ciclo-bloco"') == 3 and tab.count(" hidden>") >= 2
    assert 'data-src=' not in tab.split("Economias faturadas por ciclo")[0]      # não depende do filtro Comparar do cabeçalho


def test_indiretas_financeiro_e_eventos_com_forecast_e_grafico_no_fim(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    ind = html[html.index('id="view-indiretas"'):html.index('id="view-tabelas"')]
    bloco = ind[ind.index('data-sup="TODAS" data-mes="09/2026"'):]
    bloco = bloco[:bloco.index('class="sup-bloco"')] if 'class="sup-bloco"' in bloco else bloco
    pos = [bloco.index(t) for t in ("Indiretas — financeiro (R$)", "Indiretas — eventos faturados", "Evolução mensal por classe")]
    assert pos == sorted(pos)                                     # gráfico no fim
    assert bloco.count('class="tabela-dre tabela-previsao"') == 2
    for col in ("Orçado<br>RF01T26", "Orçado<br>RF SUP", "Realizado", "Forecast ✎", "Realizado<br>+ Forecast", "Δ %<br>vs RF01T26",
                "Ticket médio<br>3 meses"):
        assert col in bloco, col
    for k in ("ri_CORTE", "iE", "ev_ri_CORTE", "ev_iE"):
        assert f'data-k="{k}" contenteditable="true"' in bloco, k
    assert "Quantidade e ticket médio" not in ind
    ago = ind[ind.index('data-sup="TODAS" data-mes="08/2026"'):]
    ago = ago[:ago.index('class="sup-bloco"')]
    assert "contenteditable" not in ago and "Mês fechado" in ago


def test_eventos_orcado_pelo_ticket_de_3_meses(tmp_path):
    from faturamento.previsao import eventos_indiretas
    gera_pasta(str(tmp_path), com_dre=True)
    s = Sessao(str(tmp_path), progresso=lambda p, t: None)
    s.preparar()
    s.continuar()
    ctx = s.ctx
    ev = eventos_indiretas(ctx, dre.TODAS, ctx.ref_atual)
    ago = dre._indiretas_mes(ctx, dre.TODAS, "08/2026")["CORTE"]           # único mês fechado no arquivo
    assert ev["ticket"]["ri_CORTE"] == pytest.approx(ago[1] / ago[0])
    orc = dre.orcado(ctx, "RF01T26", dre.TODAS, ctx.ref_atual)["ri_CORTE"]
    assert ev["orcado"]["RF01T26"]["ev_ri_CORTE"] == pytest.approx(orc / ev["ticket"]["ri_CORTE"])
    assert ev["real"]["ev_ri_CORTE"] == dre._indiretas_mes(ctx, dre.TODAS, ctx.ref_atual)["CORTE"][0]

def test_aba_dados_no_fim_e_forecast_explicado(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert html.index('id="btn-forecast"') < html.index('id="btn-dados"')
    dados = html[html.index('id="view-dados"'):]
    for trecho in ("Em resumo", "Os três métodos", "Passo a passo", "Método 1", "Método 2", "Método 3", "Dias de corte",
                   "Data de corte (D-1)", "validacao_forecast_todas.xlsx", 'data-fc-sup="LAGOS"'):
        assert trecho in dados
    # a explicação longa saiu da aba Forecast (fica só em Dados)
    fc = html[html.index('id="view-forecast"'):html.index('id="view-dados"')]
    assert "Dados</b> › <b>4. Forecast" in fc and "pela média do mesmo grupo" not in fc
    site = open(os.path.join(os.path.dirname(__file__), "..", "index.html"), encoding="utf-8").read()
    assert site.index('data-view="forecast"') < site.index('data-view="dados"')


def test_orcado_por_ciclo_com_peso_proprio_por_metrica(sessao):
    from faturamento.orcado_ciclo import comparativo_orcado, pesos_por_ciclo
    ctx = sessao.ctx
    orc = dre.orcado(ctx, "RF01T26", dre.TODAS, ctx.ref_atual)
    for rub, kf, kv, ke in (("AGUA", "dA", "volA", "ecoA"), ("ESGOTO", "dE", "volE", "ecoE")):
        pesos = pesos_por_ciclo(ctx, rub)
        assert set(pesos) == {"valor", "volume", "economias"}
        for m in pesos:
            assert sum(pesos[m].values()) == pytest.approx(1)
        assert pesos["valor"] != pesos["volume"]                     # pesos de fato separados
        comp = comparativo_orcado(ctx, rub, rub, kf, kv, ke, orc)
        assert comp["Faturamento_anterior"].sum() == pytest.approx(orc.get(kf) or 0)
        assert comp["Volume_Faturado_anterior"].sum() == pytest.approx(orc.get(kv) or 0)
        assert comp["Economias_anterior"].sum() == pytest.approx(orc.get(ke) or 0)
        g = comp["Grupo"].iloc[0]
        assert comp["Volume_Faturado_anterior"].iloc[0] == pytest.approx(pesos["volume"][g] * (orc.get(kv) or 0))


def test_dados_explica_cada_tabela_e_grafico_com_bases_para_baixar(sessao):
    import base64, io, re
    html = open(sessao.caminho_html, encoding="utf-8").read()
    dados = html[html.index('id="view-dados"'):]
    for titulo in ("Tabela DRE", "KPIs (8 cards)", "Gráfico — Faturamento total por grupo", "Dias de leitura (média)",
                   "Destaques do mês", "Resumo consolidado por grupo", "Comparativo Água / Esgoto", "Orçado por ciclo",
                   "ativas × cortadas", "Matriz de migração", "consumo mínimo", "maior queda de consumo", "maior aumento de consumo",
                   "Indiretas: financeiro em R$", "Indiretas: eventos faturados", "Gráfico — Evolução mensal por classe", "Forecast de fechamento"):
        assert titulo in dados, titulo
    assert dados.count("Como a tabela / o gráfico é montado") >= 15
    # cada base aparece embutida uma vez e é referenciada por vários botões
    for ch in ("fatura", "fatura_mensal", "avulso", "cancelamento", "orcado"):
        assert dados.count(f'id="base-dl-{ch}"') == 1
        assert dados.count(f'data-ref="{ch}"') >= 2
    b64 = re.search(r'id="base-dl-fatura" data-arquivo="base_fatura.csv">([^<]+)<', dados).group(1)
    df = pd.read_csv(io.BytesIO(base64.b64decode(b64)), sep=";", decimal=",", encoding="utf-8-sig")
    assert {"N. Ligação", "Grupo", "Valor (R$)", "Superintendência", "Entra em economias/volume"} <= set(df.columns)
    assert set(df["Referencia de Leitura"]) == {"08/2026", "09/2026"}


def test_progresso_avisa_cada_grafico_tabela_e_kpi(tmp_path):
    msgs = []
    gera_pasta(str(tmp_path), com_dre=True)
    s = Sessao(str(tmp_path), progresso=lambda p, t: msgs.append((p, t)))
    s.preparar()
    s.continuar()
    textos = [t for _, t in msgs]
    for t in ("Criando KPIs do Resumo (8 cards)", "Criando gráfico: Faturamento total por grupo",
              "Criando tabela: Matriz de migração de grupos", "Criando aba Indiretas: orçado × realizado, gráfico de evolução e ticket médio",
              "Criando aba Forecast: LAGOS", "Criando aba Dados: bases para download"):
        assert t in textos, t
    pcts = [p for p, _ in msgs]
    assert pcts == sorted(pcts)                          # a barra só avança


def test_indiretas_tem_forecast_no_mes_mais_novo_do_avulso(tmp_path):
    import datetime as dt
    gera_pasta(str(tmp_path), com_dre=True)
    arq = tmp_path / "Servico avulso 09-2026.csv"
    av = pd.read_csv(arq, sep=";", dtype=str, encoding="utf-8-sig")
    out = av[av["Referencia de Leitura"] == "set/26"].copy()
    out["Referencia de Leitura"] = "out/26"                       # avulso já tem outubro; a fatura vai até setembro
    pd.concat([av, out]).to_csv(arq, sep=";", index=False, encoding="utf-8-sig")
    s = Sessao(str(tmp_path), progresso=lambda p, t: None)
    s.ctx.data_corte = dt.date(2026, 10, 15)
    s.preparar()
    s.continuar()
    html = open(s.caminho_html, encoding="utf-8").read()
    ind = html[html.index('id="view-indiretas"'):html.index('id="view-tabelas"')]
    out_bloco = ind[ind.index('data-sup="TODAS" data-mes="10/2026"'):]
    out_bloco = out_bloco[:out_bloco.index('class="sup-bloco"')]
    assert 'data-k="ri_CORTE" contenteditable="true"' in out_bloco and "Mês fechado" not in out_bloco
    set_bloco = ind[ind.index('data-sup="TODAS" data-mes="09/2026"'):]
    assert 'data-k="ri_CORTE" contenteditable="true"' in set_bloco[:set_bloco.index('class="sup-bloco"')]


def test_ocultar_forecast_nao_esconde_a_coluna_nas_indiretas():
    from faturamento.relatorio import carrega_asset
    js = carrega_asset("relatorio.js")
    assert "['#view-forecast', prevOculta], ['#view-indiretas', prevOcultaInd]" in js   # um botão por aba


def test_botao_executivo_e_ocultar_forecast_nas_indiretas(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert 'onclick="gerarExecutivo()"' in html and "function gerarExecutivo" in html
    ind = html[html.index('id="view-indiretas"'):html.index('id="view-tabelas"')]
    assert 'class="btn-just btn-prev-toggle" onclick="previsaoAlternar(this)"' in ind


def test_ordem_das_abas(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    ordem = ["btn-resumo", "btn-tabelas", "btn-indiretas", "btn-forecast", "btn-dre", "btn-dados"]
    assert [html.index(f'id="{b}"') for b in ordem] == sorted(html.index(f'id="{b}"') for b in ordem)
    site = open(os.path.join(os.path.dirname(__file__), "..", "index.html"), encoding="utf-8").read()
    vistas = ["resumo", "tabelas", "indiretas", "forecast", "dre", "dados"]
    pos = [site.index(f'data-view="{v}"') for v in vistas]
    assert pos == sorted(pos) and 'class="tab active" data-view="resumo"' in site
