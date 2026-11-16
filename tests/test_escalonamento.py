# -*- coding: utf-8 -*-
"""Validação do escalonamento do esgoto: água, esgoto e % esgoto/água (inteiro) por matrícula, mês a mês."""
import io
import json
import os

import pandas as pd

from faturamento.escalonamento import dados_escalonamento, gera_escalonamento, pct_esgoto

RAIZ = os.path.join(os.path.dirname(__file__), "..")


def test_pct_arredondada_para_o_inteiro():
    assert pct_esgoto(100, 24.99) == 25 and pct_esgoto(100, 25.01) == 25 and pct_esgoto(80, 19.99) == 25
    assert pct_esgoto(0, 10) is None and pct_esgoto(100, 100) == 100


def test_so_matriculas_com_esgoto_em_todos_os_meses(analise):
    ctx = analise.ctx
    df = dados_escalonamento(ctx)
    assert len(df) and (df.groupby("Matrícula")["Esgoto (R$)"].apply(lambda s: (s != 0).any())).all()
    assert df["ref"].nunique() >= 2                                  # todos os meses da pasta, não só o atual
    linha = df[(df["Água (R$)"] > 0)].iloc[0]
    assert linha["% esgoto/água"] == round(linha["Esgoto (R$)"] / linha["Água (R$)"] * 100)
    grupo = str(df["Grupo"].iloc[0])
    so = dados_escalonamento(ctx, grupos=[grupo])
    assert len(so) and set(so["Grupo"].astype(str)) == {grupo}


def test_arquivo_com_as_duas_abas(analise):
    r = gera_escalonamento(analise.ctx)
    assert r["nome"].startswith("Validacao_escalonamento_esgoto_") and r["matriculas"] > 0
    if r["nome"].endswith(".xlsx"):
        abas = pd.read_excel(io.BytesIO(r["conteudo"]), sheet_name=None)
        assert list(abas) == ["Por mês", "Lado a lado"]
        assert {"Mês", "Matrícula", "Água (R$)", "Esgoto (R$)", "% esgoto/água", "1º mês com esgoto"} <= set(abas["Por mês"].columns)
        assert any(c.startswith("% esgoto/água ") for c in abas["Lado a lado"].columns)


def test_botao_no_comparativo_esgoto_e_ligacao_com_o_site(analise):
    html = open(analise.caminho_html, encoding="utf-8").read()
    assert html.count('class="btn-just btn-escalonamento"') == 1 and "Validação do escalonamento" in html
    assert "window.parent.baixarEscalonamentoSite" in html
    site = open(os.path.join(RAIZ, "index.html"), encoding="utf-8").read()
    assert "window.baixarEscalonamentoSite = async (params) =>" in site and 'fase: "escalonamento"' in site
    worker = open(os.path.join(RAIZ, "analisador.worker.js"), encoding="utf-8").read()
    assert '"faturamento/escalonamento.py"' in worker and 'if (fase === "escalonamento")' in worker
    import executor_web
    executor_web._estado["sessao"] = analise
    import tempfile
    caminho = tempfile.mktemp()
    info = json.loads(executor_web.escalonamento(json.dumps({"sup": "TODAS", "grupos": None}), caminho))
    assert info["linhas"] > 0 and os.path.getsize(caminho) > 0
