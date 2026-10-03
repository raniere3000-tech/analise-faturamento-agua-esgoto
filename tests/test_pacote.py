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
