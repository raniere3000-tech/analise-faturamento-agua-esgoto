# -*- coding: utf-8 -*-
"""O site copia uma lista fixa de arquivos para o Pyodide: ela precisa bater com o pacote."""
import json
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def arquivos_do_pacote():
    achados = set()
    base = os.path.join(RAIZ, "faturamento")
    for pasta, _, nomes in os.walk(base):
        if "__pycache__" in pasta:
            continue
        for n in nomes:
            if n.endswith((".py", ".json", ".css", ".js")):
                achados.add(os.path.relpath(os.path.join(pasta, n), RAIZ).replace(os.sep, "/"))
    return achados


def test_lista_do_worker_confere_com_o_pacote():
    with open(os.path.join(RAIZ, "analisador.worker.js"), encoding="utf-8") as f:
        js = f.read()
    bloco = re.search(r"const ARQUIVOS_PY = \[(.*?)\];", js, re.S).group(1)
    listados = set(re.findall(r'"([^"]+)"', bloco))
    assert listados == arquivos_do_pacote()


def test_regras_json_valido_e_completo():
    with open(os.path.join(RAIZ, "faturamento", "regras.json"), encoding="utf-8") as f:
        regras = json.load(f)
    for chave in ("rubricas_validas", "situacao_conta_em_analise", "consumo_minimo_por_categoria",
                  "categoria_por_tipo_de_economia", "colunas_economia_todas", "colunas_economia_totais",
                  "alerta_variacao_grafico", "destaque_queda_pct_top100", "texto_justificativa_padrao"):
        assert chave in regras, chave
    for coluna, categoria in regras["categoria_por_tipo_de_economia"].items():
        assert categoria in regras["consumo_minimo_por_categoria"], (coluna, categoria)


def test_executor_web_expoe_as_duas_fases():
    with open(os.path.join(RAIZ, "executor_web.py"), encoding="utf-8") as f:
        codigo = f.read()
    assert "def preparar(" in codigo and "def continuar(" in codigo


def test_ref_mais_recente_e_cronologica():
    from faturamento.formatacao import ref_mais_recente
    assert ref_mais_recente(["12/2025", "01/2026", "11/2025"]) == "01/2026"
    assert ref_mais_recente(["09/2026", "10/2026"]) == "10/2026"
    assert ref_mais_recente([]) is None


def test_selo_de_versao_igual_a_versao_do_site():
    import re
    site = open(os.path.join(os.path.dirname(__file__), "..", "index.html"), encoding="utf-8").read()
    versao = re.search(r'const VERSAO_SITE = "(v\d+\.\d+)-\d{8}"', site).group(1)
    assert f'<span class="versao" id="versao">{versao}</span>' in site


def test_excel_sem_xlsxwriter_usa_openpyxl(monkeypatch):
    """Rede que bloqueia o PyPI ("Can't fetch metadata for 'xlsxwriter'"): o Excel sai pelo openpyxl."""
    import importlib.util
    import io
    import pandas as pd
    from faturamento import tabelas_html
    original = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda nome, *a: None if nome == "xlsxwriter" else original(nome, *a))
    assert tabelas_html.motor_excel() == "openpyxl"
    conteudo = tabelas_html.xlsx_bytes({"Aba": pd.DataFrame({"a": [1, 2]})})
    assert pd.read_excel(io.BytesIO(conteudo))["a"].tolist() == [1, 2]
    monkeypatch.setattr(importlib.util, "find_spec", lambda nome, *a: None)
    assert tabelas_html.xlsx_bytes({"Aba": pd.DataFrame({"a": [1]})}) == b""
    assert tabelas_html.botao_download_xlsx("x", "x.xlsx", b"") == ""


def test_worker_nao_para_se_o_pypi_falhar():
    import os
    js = open(os.path.join(os.path.dirname(__file__), "..", "analisador.worker.js"), encoding="utf-8").read()
    assert "pyodide.loadPackage(EXTRAS)" in js and "try { await micropip.install(pacote); }" in js


def test_bibliotecas_do_pdf_no_site():
    import os
    raiz = os.path.join(os.path.dirname(__file__), "..")
    for arq in ("lib/jspdf.umd.min.js", "lib/html2canvas.min.js"):
        assert os.path.getsize(os.path.join(raiz, arq)) > 100000, arq
    site = open(os.path.join(raiz, "index.html"), encoding="utf-8").read()
    assert '"lib/jspdf.umd.min.js", "lib/html2canvas.min.js"' in site and "w.gerarExecutivo(await libsPdf(), b.dataset.modo)" in site


def test_executivo_tem_versao_para_celular():
    """O botão Executivo oferece a versão para ler no celular (em pé, colunas principais) e a A4 para imprimir."""
    import os
    raiz = os.path.join(os.path.dirname(__file__), "..")
    site = open(os.path.join(raiz, "index.html"), encoding="utf-8").read()
    assert 'data-modo="celular"' in site and 'data-modo="a4"' in site
    js = open(os.path.join(raiz, "faturamento", "assets", "relatorio.js"), encoding="utf-8").read()
    assert "const celular = modo !== 'a4';" in js and "cont.classList.add('exec-celular')" in js
    assert "function enxugaTabelaCelular(t)" in js and "function paginaCelular(" in js
    css = open(os.path.join(raiz, "faturamento", "assets", "relatorio.css"), encoding="utf-8").read()
    assert "#view-executivo.exec-celular .kpis-grid { grid-template-columns:repeat(2, minmax(0,1fr)); }" in css


def test_consumo_minimo_do_publico_e_15():
    from faturamento.config import CONSUMO_MINIMO_POR_CATEGORIA, MINIMO_POR_TIPO_ECONOMIA
    assert CONSUMO_MINIMO_POR_CATEGORIA["PUBLICA"] == 15 and CONSUMO_MINIMO_POR_CATEGORIA["PUB. ESTADUAL"] == 15
    assert MINIMO_POR_TIPO_ECONOMIA["Qtd. Economia Publica"] == 15


def test_superintendencia_lagos_agora_e_interior():
    from faturamento.config import REGRAS, sup_da_localidade
    from faturamento.dre import _nome_sup, _sup_orcado
    assert "INTERIOR" in REGRAS["superintendencias"] and "LAGOS" not in REGRAS["superintendencias"]
    assert sup_da_localidade("Lagos") == "INTERIOR" and sup_da_localidade("Interior") == "INTERIOR"
    assert sup_da_localidade("RIO BONITO") == "INTERIOR" and sup_da_localidade("MARICA") == "LESTE"
    assert _sup_orcado("LAGOS") == "INTERIOR" == _sup_orcado("Interior")
    assert _nome_sup("TODAS") == "Todas as superintendências"
