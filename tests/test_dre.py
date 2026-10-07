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
        for sup in ("TODAS", "LAGOS", "LESTE"):
            assert f'data-sup="{sup}" data-mes="{mes}"' in html
    # linhas sem cidade herdam a SUP do grupo: não sobra "SEM SUP"
    assert 'data-sup="SEM SUP" data-mes="09/2026"' not in html
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
              "1. Resumo", "2. Diretas", "3. Análise", "4. Indiretas", "5. Forecast", "6. DRE"):
        assert f'<details class="val-aba"><summary>{t}' in dados, t
    assert '<details class="val-aba" open' not in dados
    pos = [dados.index(t) for t in ("1. Resumo", "2. Diretas", "3. Análise", "4. Indiretas", "5. Forecast", "6. DRE")]
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
    import gzip
    b64 = re.search(r'id="base-dl-fatura" data-gz="1" data-arquivo="base_fatura.csv">([^<]+)<', dados).group(1)
    df = pd.read_csv(io.BytesIO(gzip.decompress(base64.b64decode(b64))), sep=";", decimal=",", encoding="utf-8-sig")
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


def test_sup_dos_grupos_pelo_cronograma(tmp_path):
    gera_pasta(str(tmp_path))                                   # fatura e consumo sem cidade: a SUP só pode vir do grupo
    cr = pd.read_csv(tmp_path / "Cronograma.csv", sep=";", dtype=str, encoding="utf-8-sig")
    cr["Localidade"] = ["MARICA" if int(g) % 2 else "CANTAGALO" for g in cr["Grupo"]]      # ímpares Leste, pares Lagos
    cr.to_csv(tmp_path / "Cronograma.csv", sep=";", index=False, encoding="utf-8-sig")
    s = Sessao(str(tmp_path), progresso=lambda p, t: None)
    s.preparar()
    s.continuar()
    ctx = s.ctx
    assert ctx.grupo_sup["1"] == "LESTE" and ctx.grupo_sup["2"] == "LAGOS"
    b = ctx.base_final
    assert set(b.loc[b["Grupo"] == "01", "__sup"]) == {"LESTE"} and set(b.loc[b["Grupo"] == "02", "__sup"]) == {"LAGOS"}
    html = open(s.caminho_html, encoding="utf-8").read()
    assert '"grupoSup": {"01": "LESTE", "02": "LAGOS"' in html


def test_destaques_um_quadro_por_superintendencia(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    resumo = html[html.index('id="view-resumo"'):html.index('id="view-dre"')]
    assert 'class="card sup-dest" data-sup="LAGOS"' in resumo and 'class="card sup-dest" data-sup="LESTE"' in resumo
    assert "Destaques do mês — Setembro/2026 — LAGOS" in resumo and "Destaques do mês — Setembro/2026 — LESTE" in resumo


def test_downloads_seguem_o_filtro_de_superintendencia(sessao):
    import base64
    import io
    import re
    from faturamento import validacao
    from faturamento.tabelas_html import filtra_sup
    ctx = sessao.ctx
    html = open(sessao.caminho_html, encoding="utf-8").read()
    # um Excel por SUP em cada tabela da aba Dados; fora de Todas, começa escondido (o filtro mostra o da SUP escolhida)
    for sup in ("LAGOS", "LESTE"):
        assert f'<span class="sup-dl" data-sup="{sup}" style="display:none">' in html
        assert f'data-arquivo="validacao_dre_{sup}.xlsx"' in html
    assert '<span class="sup-dl" data-sup="TODAS"><button' in html
    # o Excel da DRE de LAGOS traz o realizado de LAGOS
    b64 = re.search(r'data-arquivo="validacao_dre_LAGOS.xlsx" [^>]*data-b64="([^"]+)"', html).group(1)
    dre_lagos = pd.read_excel(io.BytesIO(base64.b64decode(b64))).set_index("Rubrica")
    assert dre_lagos.loc["Faturamento Bruto", "Realizado"] == pytest.approx(dre.realizado(ctx, "LAGOS", ctx.ref_atual)["bruto"])
    # tabelas por grupo: só os grupos da SUP
    resumo = filtra_sup(ctx, ctx.resultados["resumo"], "LESTE")
    assert len(resumo) and all(ctx.grupo_sup[str(int(g))] == "LESTE" for g in resumo["Grupo"])
    assert filtra_sup(ctx, ctx.resultados["resumo"], "TODAS") is ctx.resultados["resumo"]
    # bases CSV: a coluna Superintendência (orçado padronizado: Interior → LAGOS) é a usada pelo filtro no navegador
    validacao.monta_bases(ctx)                    # BASES é do último relatório gerado: refaz com esta sessão
    assert "Superintendência" in validacao.BASES["orcado"]["df"].columns
    assert "INTERIOR" not in set(validacao.BASES["orcado"]["df"]["Superintendência"])
    assert "Superintendência" in validacao.BASES["fatura"]["df"].columns


def test_filtro_do_csv_por_superintendencia_no_navegador(tmp_path):
    import shutil
    import subprocess
    if not shutil.which("node"):
        pytest.skip("node não instalado")
    js = open(os.path.join(os.path.dirname(__file__), "..", "faturamento", "assets", "relatorio.js"), encoding="utf-8").read()
    ini = js.index("function filtraCsvPorSup")
    fim = js.index("\n}\n", ini) + 3
    csv = '﻿A;Superintendência;B\n1;LAGOS;"x;y"\n2;LESTE;"linha\nquebrada"\n3;LAGOS;"aspas ""z"""\n'
    prog = js[ini:fim] + "\nprocess.stdout.write(JSON.stringify([filtraCsvPorSup(require('fs').readFileSync(process.argv[2], 'utf8'), 'LAGOS'), filtraCsvPorSup('A;B\\n1;2\\n', 'LAGOS')]));"
    arq = tmp_path / "t.js"
    arq.write_text(prog, encoding="utf-8")
    dados = tmp_path / "base.csv"
    dados.write_bytes(csv.encode("utf-8"))
    import json
    saida = subprocess.run(["node", str(arq), str(dados)], capture_output=True, check=True).stdout.decode("utf-8")
    lagos, sem_coluna = json.loads(saida)
    assert lagos == '﻿A;Superintendência;B\n1;LAGOS;"x;y"\n3;LAGOS;"aspas ""z"""\n'
    assert sem_coluna is None


def test_ultimo_grupo_por_superintendencia_e_dias_de_leitura():
    """Lagos (5xx) e Leste (4xx) leem em paralelo: o corte do 'último grupo faturado' é por SUP, e grupo sem leitura
    no mês não entra como 0 dia na média (era o que dava 9,0 dias em vez de ~30)."""
    from types import SimpleNamespace
    from faturamento.comparativo import limita_ao_ultimo_grupo
    from faturamento.config import sup_da_localidade
    from faturamento.painel_html import media_dias
    assert sup_da_localidade("Lagos") == "LAGOS" and sup_da_localidade("Leste") == "LESTE"
    assert sup_da_localidade("Interior") == "LAGOS" and sup_da_localidade("Maricá") == "LESTE"
    assert sup_da_localidade("Rio Centro-Sul") is None
    linhas = []
    for g in list(range(401, 406)) + list(range(501, 506)):
        linhas.append({"Grupo": str(g), "Referencia de Leitura": "09/2026", "Valor (R$)": 100.0})
        if g in (401, 402, 501, 502, 503):                       # já faturados em outubro
            linhas.append({"Grupo": str(g), "Referencia de Leitura": "10/2026", "Valor (R$)": 100.0})
    ctx = SimpleNamespace(base_final=pd.DataFrame(linhas), ref_atual="10/2026",
                          grupo_localidade={str(g): ("Leste" if g < 500 else "Lagos") for g in list(range(401, 406)) + list(range(501, 506))})
    limita_ao_ultimo_grupo(ctx)
    assert sorted(ctx.base_final["Grupo"].unique()) == ["401", "402", "501", "502", "503"]
    assert ctx.ultimo_grupo == "503 (LAGOS), 402 (LESTE)"
    assert len(ctx.base_completa) == len(linhas)                # o forecast continua vendo todos os grupos
    assert media_dias(pd.Series([30.0, 31.0, 0.0, 0.0])) == pytest.approx(30.5)
    assert media_dias(pd.Series([0.0])) == 0.0


def test_card_de_dias_segue_o_filtro(sessao):
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert 'data-field="dias-media-atual"' in html and "data-dias-atual=" in html[html.index('id="tabela-dados-resumo"'):]
    resumo = sessao.ctx.resultados["resumo"]
    assert (resumo["Dias_Leitura_Atual"] > 0).all()


def test_situacao_lancamento_no_top100_e_nos_cards(sessao):
    from faturamento.situacao_lancamento import classifica
    ctx = sessao.ctx
    top = ctx.resultados["top_agua"]
    assert "Situação Lançamento 09/2026" in top.columns and "Situação Lançamento 08/2026" in top.columns
    from dados_sinteticos import SITUACOES_LANCAMENTO
    assert set(top["Situação Lançamento 09/2026"]) <= set(SITUACOES_LANCAMENTO)
    r = ctx.resultados["situacao_lancamento"]["TODAS"]
    at = ctx.df_atual[ctx.df_atual["__serv"] == "A"]
    assert r["Ligações atual"].sum() == at["N. Ligação"].nunique()
    assert r["% ligações atual"].sum() == pytest.approx(100)
    assert r.iloc[0]["Situação"] == "01-3EM MAOS"                  # a mais frequente primeiro
    lagos = ctx.resultados["situacao_lancamento"]["LAGOS"]
    assert 0 < lagos["Ligações atual"].sum() < r["Ligações atual"].sum()
    html = open(sessao.caminho_html, encoding="utf-8").read()
    diretas = html[html.index('id="view-tabelas"'):]
    assert "Situação de lançamento —" in diretas and diretas.count('class="sitl-card"') >= 4
    assert "Por que analisar:" in diretas and "Situação Lançamento 09/2026" in diretas
    assert classifica("04-7FIXADA AO PORTAO")[0] == "Entregue" and classifica("61-RETIDA - CONSOLIDADO")[0] == "Público"
    assert classifica("07 - RECALCULADA")[0] == "Retida" and classifica("07-6NO HD")[0] == "Entregue"
    assert classifica("73-RETIDA - MED > 2X MED FATUR")[0] == "Aumento de Consumo"
    assert classifica("71-RETIDA - QUEDA DE CONSUMO F")[0] == "Queda de Consumo"
    assert classifica("00-7NAO ENTREGUE")[0] == "Não Entregue" and classifica("99-CODIGO NOVO")[0] == "Outros"
    # visão sintética: um card por leitura da situação, somando os códigos do grupo
    rs = ctx.resultados["situacao_lancamento_sintetica"]["TODAS"].set_index("Situação")
    an = r.set_index("Situação")
    assert rs.loc["Entregue", "Ligações atual"] == an.loc[["01-3EM MAOS", "02-1CAIXA CORREIO"], "Ligações atual"].sum()
    assert rs["Ligações atual"].sum() == r["Ligações atual"].sum() and "Outros" in rs.index
    assert diretas.count('data-gsit="Entregue"') >= 3 and 'class="sitl-visao"' in diretas
    assert 'data-visao="sintetica" hidden' in diretas


def test_seta_de_cada_situacao_baixa_as_ligacoes(sessao):
    import base64
    import gzip
    import io
    import re
    ctx = sessao.ctx
    html = open(sessao.caminho_html, encoding="utf-8").read()
    assert html.count('class="btn-sitl-dl"') >= 4 and 'data-sit="50-EMITIDO - RETIDA" data-sup="LAGOS"' in html
    assert 'class="btn-sitl-dl" data-sup="LAGOS" title="Baixar a base analítica com as matrículas (CSV)"' in html
    m = re.search(r'<script type="application/octet-stream" id="sitl-detalhe" data-col-sit="([^"]+)"[^>]*>([^<]+)</script>', html)
    det = pd.read_csv(io.BytesIO(gzip.decompress(base64.b64decode(m.group(2)))), sep=";", decimal=",", dtype={"N. Ligação": str},
                      encoding="utf-8-sig")
    col = m.group(1)
    assert col == "Situação Lançamento Setembro/2026" and "Superintendência" in det.columns
    r = ctx.resultados["situacao_lancamento"]
    for sup in ("TODAS", "LAGOS"):
        d = det if sup == "TODAS" else det[det["Superintendência"] == sup]
        esperado = r[sup].set_index("Situação")["Ligações atual"]
        assert d[col].value_counts().sort_index().to_dict() == esperado[esperado > 0].sort_index().astype(int).to_dict()


def test_dados_para_o_filtro_de_grupos_nos_downloads(sessao):
    import json
    import re
    html = open(sessao.caminho_html, encoding="utf-8").read()
    top = json.loads(re.search(r'<script type="application/json" id="top100-dados">(.*?)</script>', html, re.S).group(1))
    q = pd.DataFrame(top["queda-agua"]["data"], columns=top["queda-agua"]["columns"])
    assert q.groupby("Grupo").size().max() <= 100 and "Superintendência" in q.columns
    # o Top 100 de Todas é o começo da lista de candidatos (mesma ordem)
    assert list(q["N. Ligação"].head(100)) == list(sessao.ctx.resultados["top_agua"]["N. Ligação"])
    sit = json.loads(re.search(r'<script type="application/json" id="sitl-agregados">(.*?)</script>', html, re.S).group(1))
    total = sum(l[3] for l in sit["at"])
    assert total == sessao.ctx.resultados["situacao_lancamento"]["TODAS"]["Ligações atual"].sum()
    for tipo in ("top", "semfat"):
        assert f'data-csv-filtrado="{tipo}"' in html
    assert 'id="semfat-dados"' in html and 'data-top="aumento-esgoto"' in html


def test_executivo_imprime_documento_leve(sessao):
    """O PDF sai de um documento só com o Executivo (sem as bases embutidas), senão a impressão falhava."""
    html = open(sessao.caminho_html, encoding="utf-8").read()
    ini = html.index("function gerarExecutivo")
    trecho = html[ini:html.index("function imprimirDocumentoLeve")]
    assert "imprimirDocumentoLeve(cont)" in trecho and "window.print()" not in trecho
    assert "querySelectorAll('script').forEach(x => x.remove())" in trecho
