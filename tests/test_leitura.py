# -*- coding: utf-8 -*-
import os

import numpy as np
import pandas as pd
import pytest

from dados_sinteticos import gera_pasta

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


CAB_CRONOGRAMA = ["Cód.Med", "Grupo", "Localidade", "Rio 01", "Rio 04", "Total Lig.", "Data da Leitura", "DS", "Qts. Dias",
                  "Vencimento", "Próxima Leitura", "DS", "Dias Próx."]


def _cronograma_real(grupos, mes, ano, dias_base):
    linhas = [["CRONOGRAMA DE LEITURA E FATURAMENTO"] + [""] * 12, [""] * 13, CAB_CRONOGRAMA]
    for i, g in enumerate(grupos):
        linhas.append([f"M{i}", str(int(g)), "CANTAGALO", "10", "5", "15", f"{5 + i:02d}/{mes:02d}/{ano}", "SEG",
                       str(dias_base + i % 3), f"20/{mes:02d}/{ano}", f"05/{mes % 12 + 1:02d}/{ano}", "TER", "30"])
    return linhas


@pytest.mark.parametrize("formato", ["xlsx", "csv"])
def test_cronograma_no_formato_real_com_titulo_e_dias_por_mes(tmp_path, formato):
    from faturamento import Sessao
    gera_pasta(str(tmp_path))
    os.remove(tmp_path / "Cronograma.csv")
    grupos = [f"{g:02d}" for g in range(1, 9)]
    ago, set_ = _cronograma_real(grupos, 8, 2026, 28), _cronograma_real(grupos, 9, 2026, 31)
    if formato == "xlsx":
        with pd.ExcelWriter(tmp_path / "Cronograma 2026.xlsx") as w:     # nomes de aba quaisquer: o mês vem da Data da Leitura
            pd.DataFrame([["Instruções"], ["qualquer coisa"]]).to_excel(w, sheet_name="Leia-me", index=False, header=False)
            pd.DataFrame(ago).to_excel(w, sheet_name="Planilha1", index=False, header=False)
            pd.DataFrame(set_).to_excel(w, sheet_name="cópia final (2)", index=False, header=False)
    else:
        texto = "sep=;\n" + "\n".join(";".join(l) for l in ago + set_[3:])
        (tmp_path / "Cronograma 2026.csv").write_text(texto, encoding="utf-8-sig")
    s = Sessao(str(tmp_path), progresso=lambda p, t: None)
    s.preparar()
    b = s.ctx.base_final
    assert len(s.ctx.classificacao["cronograma"]) == 1
    assert (b["Encontrado no Cronograma"] == "Sim").all()
    g1 = b[b["Grupo"] == "01"].groupby("Referencia de Leitura")["Qts. Dias"].first()
    assert g1["08/2026"] == 28 and g1["09/2026"] == 31          # dias de leitura de cada mês


def test_subpastas_mesmo_nome_sem_duplicar(tmp_path):
    """Pastas dentro da pasta: arquivos com o mesmo nome em pastas diferentes entram todos; cópias idênticas e linhas
    repetidas entre arquivos contam uma vez só — o resultado tem que ser igual ao da pasta sem subpastas."""
    from faturamento import Sessao
    plano, sub = tmp_path / "plano", tmp_path / "sub"
    gera_pasta(str(plano), formato_fatura="csv")

    def roda(pasta):
        s = Sessao(str(pasta), progresso=lambda p, t: None)
        s.preparar()
        s.continuar()
        return s.ctx

    ler = lambda n: pd.read_csv(plano / n, sep=";", dtype=str, encoding="utf-8-sig")
    fat = ler("Fatura.csv")
    ligs = sorted(fat["N. da Ligacao"].unique())
    metade = set(ligs[: len(ligs) // 2])
    for pasta, sel in (("Leste", lambda d, c: d[c].isin(metade)), ("Lagos", lambda d, c: ~d[c].isin(metade))):
        os.makedirs(sub / pasta)
        sel(fat, "N. da Ligacao").pipe(lambda d: fat[d]).to_csv(sub / pasta / "Fatura.csv", sep=";", index=False, encoding="utf-8-sig")
        for n in ("Consumo 08-2026.csv", "Consumo 09-2026.csv"):
            c = ler(n)
            c[sel(c, "N. Ligacao")].to_csv(sub / pasta / n, sep=";", index=False, encoding="utf-8-sig")
    (sub / "Cronograma.csv").write_bytes((plano / "Cronograma.csv").read_bytes())
    os.makedirs(sub / "copia")
    (sub / "copia" / "Cronograma.csv").write_bytes((plano / "Cronograma.csv").read_bytes())       # cópia idêntica
    os.makedirs(sub / "extra")
    fat[fat["N. da Ligacao"].isin(metade)].head(200).to_csv(sub / "extra" / "Fatura parcial.csv", sep=";", index=False,
                                                            encoding="utf-8-sig")                # linhas sobrepostas
    a, b = roda(plano), roda(sub)
    assert len(b.classificacao["fatura"]) == 3 and len(b.classificacao["consumo"]) == 4
    assert any("idêntico" in i["motivo"] for i in b.classificacao["ignorados"])
    for comp in ("comp_agua", "comp_esgoto"):
        x, y = getattr(a, comp), getattr(b, comp)
        assert x["Faturamento_atual"].sum() == pytest.approx(y["Faturamento_atual"].sum())
        assert x["Economias_atual"].sum() == pytest.approx(y["Economias_atual"].sum())
        assert x["Volume_Faturado_anterior"].sum() == pytest.approx(y["Volume_Faturado_anterior"].sum())
    assert any("Leste/Fatura.csv" == i["arquivo"] for i in b.bases_info)
    assert any("contadas uma vez só" in av for av in b.avisos_base)


def test_consumo_sem_mes_no_nome_usa_pasta_ou_colunas(tmp_path):
    from faturamento.leitura import referencia_do_consumo
    df = pd.DataFrame({"Mes Lancamento": ["5", "5"], "Ano Lancamento": ["2026", "2026"]})
    assert referencia_do_consumo(df, str(tmp_path / "09-2026" / "Consumo.csv")) == "09/2026"
    assert referencia_do_consumo(df, str(tmp_path / "geral" / "Consumo.csv")) == ["05/2026", "05/2026"]
