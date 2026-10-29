# -*- coding: utf-8 -*-
"""Extração de bases por matrículas e meses (Dados › Bases analíticas) e orçados por grupo (aba Diretas)."""
import io

import pandas as pd
import pytest

from dados_sinteticos import gera_pasta
from faturamento import Sessao
from faturamento.extrair_base import chave_lig, extrai_base, ligacoes_do_arquivo, ligacoes_do_texto


@pytest.fixture(scope="module")
def sessao(tmp_path_factory):
    destino = tmp_path_factory.mktemp("extrair") / "dados"
    gera_pasta(str(destino), com_dre=True, n_meses=4, n_ligacoes=120, n_grupos=4)
    s = Sessao(str(destino), progresso=lambda pct, desc: None)
    s.preparar()
    s.continuar()
    return s


def test_matriculas_coladas_e_de_arquivo():
    assert chave_lig("0100398") == chave_lig("100398.0") == chave_lig("100.398") == "100398"
    assert ligacoes_do_texto("100398\n100275, 100398; 7") == ["100398", "100275", "7"]
    buf = io.BytesIO()
    pd.DataFrame({"Nome": ["A", "B"], "Matrícula": ["100398", "100275"]}).to_excel(buf, index=False)
    assert ligacoes_do_arquivo("lista.xlsx", buf.getvalue()) == ["100398", "100275"]
    assert ligacoes_do_arquivo("lista.csv", "Nome;Ligação\nA;100398\n".encode()) == ["100398"]


def test_por_matricula_nos_meses_marcados_e_nao_encontradas(sessao):
    ctx = sessao.contexto_do_mes(None)
    ligs = sorted(ctx.base_completa["N. Ligação"].astype(str).unique())[:5]
    r = extrai_base(ctx, ligs + ["999999"], ["09/2026", "08/2026"], "matricula")
    assert r["nome"].endswith(".xlsx") and "999999" in r["naoEncontradas"]
    abas = pd.read_excel(io.BytesIO(r["conteudo"]), sheet_name=None)
    assert set(abas) == {"Agosto-2026", "Setembro-2026"} and sum(len(a) for a in abas.values()) == r["linhas"]
    set_ = abas["Setembro-2026"]
    assert set(set_["Matrícula"].astype(str)) <= set(ligs)
    b = ctx.base_completa
    b = b[(b["Referencia de Leitura"] == "09/2026") & b["N. Ligação"].astype(str).isin(ligs)]
    assert set_["Faturamento total (R$)"].sum() == pytest.approx(pd.to_numeric(b["Valor (R$)"], errors="coerce").sum(), abs=0.05)
    assert set(set_["Tipo de faturamento"]) <= {"AGUA", "AGUA E ESGOTO"}


def test_todas_as_matriculas_e_linhas_completas(sessao):
    ctx = sessao.contexto_do_mes(None)
    r = extrai_base(ctx, None, ["09/2026"], "matricula")
    assert r["linhas"] == ctx.base_completa.loc[ctx.base_completa["Referencia de Leitura"] == "09/2026", "N. Ligação"].nunique()
    lig = str(ctx.base_completa["N. Ligação"].iloc[0])
    r2 = extrai_base(ctx, [lig], ["09/2026", "08/2026", "07/2026"], "linhas")
    b = ctx.base_completa
    assert r2["linhas"] == int((b["N. Ligação"].astype(str) == lig).sum() - (b.loc[b["N. Ligação"].astype(str) == lig, "Referencia de Leitura"] == "06/2026").sum())
    abas = pd.read_excel(io.BytesIO(r2["conteudo"]), sheet_name=None)
    assert not any(str(c).startswith("__") for a in abas.values() for c in a.columns)


def test_orcados_por_grupo_todos_os_arquivos_e_meses_seguintes(sessao):
    from faturamento.dre import TODAS, orcado
    from faturamento.orcado_ciclo import dados_orcados_por_grupo, orcados_por_grupo_html
    d = dados_orcados_por_grupo(sessao.ctx)
    assert d["meses"][0] == "09/2026" and "12/2026" in d["meses"]                # mês da análise e os seguintes
    assert set(d["fontes"]) == {"RF01T26", "RF3T25", "RF SUP"}
    assert d["orc"]["RF01T26"]["10/2026"]["dA"] == pytest.approx(orcado(sessao.ctx, "RF01T26", TODAS, "10/2026")["dA"])
    for s in ("A", "E"):
        for m in ("valor", "volume", "economias"):
            assert sum(d["pesos"][s][m].values()) == pytest.approx(1.0)
    assert 'id="orcGruposTabela"' in orcados_por_grupo_html(sessao.ctx)
