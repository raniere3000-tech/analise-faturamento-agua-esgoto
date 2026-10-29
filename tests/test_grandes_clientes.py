# -*- coding: utf-8 -*-
"""Grandes Clientes (GC): lista de matrículas da pasta + adicionadas, Excel com faturamento/consumo/vencimento mês a mês."""
import io
import os

import pandas as pd
import pytest

from dados_sinteticos import gera_pasta
from faturamento import Sessao
from faturamento.grandes_clientes import chave_matricula, dados_gc, gera_xlsx_gc, monta_gc
from faturamento.leitura import identifica_tipo


@pytest.fixture(scope="module")
def sessao_gc(tmp_path_factory):
    destino = tmp_path_factory.mktemp("gc") / "dados"
    gera_pasta(str(destino), n_ligacoes=120, n_grupos=4, n_meses=3)
    # mesmo formato da planilha "Matriculas lest GC": Matricula | TIPO (uma matrícula com zero à esquerda, uma inexistente)
    pd.DataFrame({"Matricula": ["100003", "0100007", "999999999"], "TIPO": ["GC", "gc", "GC"]}).to_excel(
        destino / "Matriculas lest GC.xlsx", index=False)
    s = Sessao(str(destino), progresso=lambda pct, desc: None)
    s.preparar()
    s.continuar()
    return s


def test_reconhece_a_planilha_de_matriculas():
    assert identifica_tipo(["Matricula", "TIPO"]) == "matriculas_gc"
    assert identifica_tipo(["Matrícula", "Tipo"]) == "matriculas_gc"
    assert chave_matricula("0102340199") == chave_matricula("102340199.0") == "102340199"


def test_lista_da_pasta_entra_no_contexto_e_na_aba_dados(sessao_gc):
    ctx = sessao_gc.ctx
    assert [i["mat"] for i in ctx.gc_lista] == ["100003", "100007", "999999999"]
    assert {i["tipo"] for i in ctx.gc_lista} == {"GC"}
    assert any(i["tipo"] == "Matrículas GC" for i in ctx.bases_info)
    assert not any("Matriculas lest GC" in ig["arquivo"] for ig in ctx.classificacao["ignorados"])
    html = open(sessao_gc.caminho_html, encoding="utf-8").read()
    assert 'id="gcBaixar"' in html and 'id="gc-dados"' in html and "Matriculas lest GC.xlsx" in html


def test_valores_batem_com_a_base_em_todos_os_meses(sessao_gc):
    ctx = sessao_gc.ctx
    an, refs, cad = monta_gc(ctx, [{"mat": "100003", "tipo": "GC"}, {"mat": "100050", "tipo": "PUBLICO"}])
    assert len(refs) == 3
    b = ctx.base_completa
    for lig in ("100003", "100050"):
        for ref in refs:
            linhas = b[(b["N. Ligação"] == lig) & (b["Referencia de Leitura"] == ref)]
            if not len(linhas):
                continue
            r = an[(an["Matrícula"] == lig) & (an["Referência"] == ref)].iloc[0]
            assert r["Faturado Total (R$)"] == pytest.approx(pd.to_numeric(linhas["Valor (R$)"]).sum(), abs=0.01)
            agua = linhas[linhas["__serv"] == "A"]
            assert r["Consumo Faturado Água (m³)"] == pytest.approx(pd.to_numeric(agua["Consumo Faturado"]).sum())
            assert r["Data de Vencimento"] is not None
    assert list(cad["Tipo"]) == ["GC", "PUBLICO"]


def test_excel_tem_as_abas_por_mes_e_marca_as_nao_encontradas(sessao_gc):
    lista = [{"mat": i["mat"], "tipo": i["tipo"]} for i in sessao_gc.ctx.gc_lista] + [{"mat": "100010", "tipo": "GC"}]
    conteudo, nome, info = gera_xlsx_gc(sessao_gc.ctx, lista)
    assert nome.startswith("GC_Faturamento_Consumo_") and nome.endswith(".xlsx")
    assert info == {"nome": nome, "matriculas": 4, "encontradas": 3, "meses": 3}
    abas = pd.read_excel(io.BytesIO(conteudo), sheet_name=None, dtype={"Matrícula": str})
    assert list(abas) == ["GC", "Faturamento (R$)", "Consumo (m³)", "Vencimento", "Analítico"]
    gc = abas["GC"]                                   # aba principal: por mês, faturado | consumo | vencimento lado a lado
    meses = [c[:-len(" Faturado (R$)")] for c in gc.columns if c.endswith(" Faturado (R$)")]
    assert len(meses) == 3
    for m in meses:
        assert gc[f"{m} Consumo (m³)"].iloc[:2].notna().all() and gc[f"{m} Vencimento"].iloc[:2].notna().all()
    fat = abas["Faturamento (R$)"]
    assert list(fat["Matrícula"]) == ["100003", "100007", "999999999", "100010"]
    assert fat.loc[2, "Nome Cliente"] == "NÃO ENCONTRADA NA BASE"
    assert {"Média", "Total"}.issubset(fat.columns) and len([c for c in fat.columns if "/" in c]) == 3
    assert abas["Vencimento"].iloc[0, 5:].notna().any()


def test_dados_da_tela_tem_consumo_e_vencimento_por_mes(sessao_gc):
    d = dados_gc(sessao_gc.ctx, [{"mat": "100003", "tipo": "GC"}, {"mat": "999999999", "tipo": "GC"}])
    assert len(d["refs"]) == 3
    m, falta = d["matriculas"]
    assert m["achada"] and not falta["achada"] and falta["meses"] == []
    assert len(m["meses"]) == 3
    for ref, venc, medido, agua, esgoto, val_a, val_e, total in m["meses"]:
        assert len(venc) == 10 and venc[2] == "/" and agua > 0 and total == pytest.approx(val_a + val_e, abs=0.01)
    html = open(sessao_gc.caminho_html, encoding="utf-8").read()
    assert '"meses":' in html and 'id="gcLista"' in html          # matrículas da planilha já vêm com os dados


def test_site_e_worker_ligam_o_botao_ao_python():
    raiz = os.path.join(os.path.dirname(__file__), "..")
    site = open(os.path.join(raiz, "index.html"), encoding="utf-8").read()
    worker = open(os.path.join(raiz, "analisador.worker.js"), encoding="utf-8").read()
    rel = open(os.path.join(raiz, "faturamento", "assets", "relatorio.js"), encoding="utf-8").read()
    executor = open(os.path.join(raiz, "executor_web.py"), encoding="utf-8").read()
    assert "window.baixarGC = async (lista)" in site and 'fase: "gc"' in site
    assert '"faturamento/grandes_clientes.py"' in worker and 'fase === "gc"' in worker
    assert "def grandes_clientes(lista_json, caminho)" in executor and "def grandes_clientes_dados(lista_json)" in executor
    assert "window.dadosGC = async (lista)" in site and 'fase === "gcDados"' in worker and "window.parent.dadosGC" in rel
    assert "criaSync('gc'" in rel and "window.parent.baixarGC" in rel and "await syncGC.empurrar()" in rel


def test_vencimento_em_outros_formatos_e_texto_que_nao_e_data():
    import datetime
    from faturamento.grandes_clientes import _vencimentos
    d = datetime.date(2026, 10, 15)
    for valor in ("15/10/2026", "15/10/26", "2026-10-15 00:00:00", "15.10.2026", "15-10-2026", "46310", "46310.0", "20261015"):
        assert _vencimentos(pd.Series([valor, None, ""])) == d, valor
    assert _vencimentos(pd.Series(["15/10/2026", "20/10/2026"])) == "15/10/2026, 20/10/2026"
    assert _vencimentos(pd.Series(["A VISTA"])) == "A VISTA"          # não é data: aparece como está na fatura
    assert _vencimentos(pd.Series([None, "", "nan"])) is None


def test_vencimento_vazio_na_linha_de_agua_vem_de_outra_rubrica(tmp_path):
    from faturamento.leitura import processa_fatura_completa
    linhas = []
    for rub, venc in (("VALOR DE AGUA", ""), ("VALOR DE ESGOTO", ""), ("DESCONTO", "15/10/2026")):
        linhas.append({"N. da Ligacao": "100003", "Grupo": "01", "Rubrica": rub, "Valor Parcela": "10,00",
                       "Referencia de Leitura": "15/10/2026", "Data de Vencimento": venc})
    caminho = tmp_path / "Fatura.csv"
    pd.DataFrame(linhas).to_csv(caminho, sep=";", index=False, encoding="utf-8-sig")
    agua_esgoto, _ = processa_fatura_completa(str(caminho))
    assert list(agua_esgoto["Data de Vencimento"]) == ["15/10/2026", "15/10/2026"]


def test_lista_de_matriculas_comeca_fechada(sessao_gc):
    html = open(sessao_gc.caminho_html, encoding="utf-8").read()
    assert '<details class="val-aba" id="gcListaWrap"><summary id="gcListaTitulo">' in html
    assert '<details class="val-aba" id="gcListaWrap" open' not in html
