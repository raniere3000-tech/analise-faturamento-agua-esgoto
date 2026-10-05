# -*- coding: utf-8 -*-
import os

import numpy as np
import pandas as pd
import pytest

from faturamento.leitura import (classifica_arquivos, detecta_linha_cabecalho, identifica_tipo, le_dataframe,
                                 processa_fatura, referencia_do_nome)

CABECALHO_CONSUMO = "N. Ligacao;Leitura Atual;Consumo Medido;Consumo Faturado"


def escreve(caminho, texto, encoding="utf-8-sig"):
    with open(caminho, "w", encoding=encoding, newline="") as f:
        f.write(texto)
    return str(caminho)


def test_referencia_do_nome():
    assert referencia_do_nome("Consumo 09-2026.csv") == "09/2026"
    assert referencia_do_nome("consumo_12-2025.xlsx") == "12/2025"
    assert np.isnan(referencia_do_nome("Consumo sem mes.csv"))


def test_detecta_cabecalho_depois_de_linhas_de_titulo(tmp_path):
    arq = escreve(tmp_path / "c.csv", f"Relatório de consumo;;;\nGerado em 01/10/2026;;;\n{CABECALHO_CONSUMO}\n1;10;5;5\n")
    assert detecta_linha_cabecalho(arq) == 2
    df = le_dataframe(arq)
    assert list(df.columns)[:4] == ["N. Ligacao", "Leitura Atual", "Consumo Medido", "Consumo Faturado"]
    assert len(df) == 1


def test_csv_com_linha_sep(tmp_path):
    """CSV do Excel que começa com 'sep=;' deve ser lido sem perder o cabeçalho."""
    arq = escreve(tmp_path / "c.csv", f"sep=;\n{CABECALHO_CONSUMO}\n1;10;5;5\n2;20;6;6\n")
    df = le_dataframe(arq)
    assert "Consumo Faturado" in df.columns
    assert len(df) == 2


def test_csv_latin1(tmp_path):
    arq = escreve(tmp_path / "c.csv", f"{CABECALHO_CONSUMO};Nome Cliente\n1;10;5;5;JOSÉ DA SILVA\n", encoding="latin-1")
    df = le_dataframe(arq)
    assert df["Nome Cliente"].iloc[0] == "JOSÉ DA SILVA"


def test_identifica_tipo():
    assert identifica_tipo(["Leitura Atual", "Consumo Medido", "Consumo Faturado", "X"]) == "consumo"
    assert identifica_tipo(["Rubrica", "Valor Parcela", "Data de Vencimento"]) == "fatura"
    assert identifica_tipo(["Grupo", "Data da Leitura", "Qts. Dias"]) == "cronograma"
    assert identifica_tipo(["a", "b"]) == "desconhecido"


def test_processa_fatura_converte_valor_br_e_filtra_rubricas(tmp_path):
    texto = ("N. da Ligacao;Grupo;Rubrica;Valor Parcela;Data de Vencimento;Referencia de Leitura\n"
             "1;01;VALOR DE AGUA;1.234,56;28/09/2026;15/09/2026\n"
             "1;01;VALOR DE ESGOTO;0,50;28/09/2026;15/09/2026\n"
             "1;01;VALOR DE OUTRO;9,99;28/09/2026;15/09/2026\n")
    df = processa_fatura(escreve(tmp_path / "f.csv", texto))
    assert sorted(df["Rubrica"]) == ["VALOR DE AGUA", "VALOR DE ESGOTO"]
    assert df.loc[df["Rubrica"] == "VALOR DE AGUA", "Valor Parcela"].iloc[0] == pytest.approx(1234.56)
    assert set(df["Referencia de Leitura"]) == {"09/2026"}


def test_classifica_pasta_modelo(pasta_modelo):
    r = classifica_arquivos(pasta_modelo)
    assert len(r["fatura"]) == 1 and len(r["consumo"]) == 2 and len(r["cronograma"]) == 1
    assert r["ignorados"] == []


def test_classifica_lista_arquivos_ignorados_com_motivo(pasta_pequena):
    escreve(os.path.join(pasta_pequena, "lixo.csv"), "coluna1;coluna2\n1;2\n")
    with open(os.path.join(pasta_pequena, "corrompido.xlsx"), "wb") as f:
        f.write(b"isto nao e um xlsx")
    r = classifica_arquivos(pasta_pequena)
    nomes = {i["arquivo"]: i["motivo"] for i in r["ignorados"]}
    assert set(nomes) == {"lixo.csv", "corrompido.xlsx"}
    assert "colunas" in nomes["lixo.csv"]
    assert "ler" in nomes["corrompido.xlsx"]
    assert len(r["fatura"]) == 1                      # os arquivos bons continuam sendo usados


def test_classifica_sem_fatura_explica_o_que_falta(tmp_path):
    escreve(tmp_path / "Consumo 09-2026.csv", f"{CABECALHO_CONSUMO}\n1;10;5;5\n")
    with pytest.raises(FileNotFoundError, match="FATURA"):
        classifica_arquivos(str(tmp_path))


def test_classifica_pasta_vazia(tmp_path):
    with pytest.raises(FileNotFoundError):
        classifica_arquivos(str(tmp_path))


def test_arquivos_gerados_pelo_pipeline_nao_sao_lidos_como_entrada(pasta_pequena):
    escreve(os.path.join(pasta_pequena, "Relatorio_Comparativo.html"), "<html></html>")
    pd.DataFrame({"a": [1]}).to_excel(os.path.join(pasta_pequena, "Top100_Quedas_Consumo.xlsx"), index=False)
    r = classifica_arquivos(pasta_pequena)
    assert r["ignorados"] == []


def test_padroniza_referencia_formatos_variados():
    import pandas as pd
    from faturamento.leitura import padroniza_referencia
    s = pd.Series(["05/10/2026", "10/2026", "2026-10-05 00:00:00", "2026-10-05", "out/26", "Outubro/2026", "09/09/2026 00:00:00"])
    assert list(padroniza_referencia(s)) == ["10/2026"] * 6 + ["09/2026"]


def test_referencia_do_nome_formatos():
    from faturamento.leitura import referencia_do_nome
    assert referencia_do_nome("Consumo 10-2026.csv") == "10/2026"
    assert referencia_do_nome("Consumo 10.2026.csv") == "10/2026"
    assert referencia_do_nome("Consumo out-26.xlsx") == "10/2026"
