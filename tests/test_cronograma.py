# -*- coding: utf-8 -*-
"""Cronograma no modelo sem "Qts. Dias" (Grupo, Localidade, Rio 01, Rio 04, Total Lig., Data da Leitura) e filtro da
superintendência do painel (regras.json "sup_do_painel")."""
import pandas as pd
import pytest

from dados_sinteticos import gera_pasta
from faturamento import Sessao
from faturamento.config import REGRAS
from faturamento.leitura import identifica_tipo, processa_cronograma


def _cronograma(caminho, grupos_leste, grupos_interior, meses):
    """Uma aba por mês, como o arquivo enviado: Grupo, Localidade, Rio 01, Rio 04, Total Lig., Data da Leitura."""
    with pd.ExcelWriter(caminho, engine="openpyxl") as w:
        for mm, aa in meses:
            linhas = [{"Grupo": g, "Localidade": "Leste" if g in grupos_leste else "Interior", "Rio 01": 100, "Rio 04": 50,
                       "Total Lig.": 150, "Data da Leitura": f"{(int(g) % 20) + 3 + (mm % 2):02d}/{mm:02d}/{aa}"}
                      for g in grupos_leste + grupos_interior]
            pd.DataFrame(linhas).to_excel(w, sheet_name=f"{mm:02d}-{aa}", index=False)


def test_modelo_sem_qts_dias_e_reconhecido():
    assert identifica_tipo(["Grupo", "Localidade", "Rio 01", "Rio 04", "Total Lig.", "Data da Leitura"]) == "cronograma"


def test_dias_saem_da_diferenca_entre_as_leituras(tmp_path):
    caminho = str(tmp_path / "Cronograma.xlsx")
    _cronograma(caminho, ["1", "3"], ["2"], [(7, 2026), (8, 2026), (9, 2026)])
    c = processa_cronograma(caminho)
    g1 = c[c["Grupo"] == "1"].set_index("Referencia Cronograma")
    # grupo 1: 04/07 (jul ímpar: +1), 03/08, 04/09 → 30 e 32 dias; o primeiro mês não tem leitura anterior
    assert pd.isna(g1.loc["07/2026", "Qts. Dias"])
    assert g1.loc["08/2026", "Qts. Dias"] == 30 and g1.loc["09/2026", "Qts. Dias"] == 32
    assert set(c["Localidade"]) == {"Leste", "Interior"}


def test_painel_da_leste_fica_so_com_o_cronograma_da_leste(tmp_path, monkeypatch):
    monkeypatch.setitem(REGRAS, "sup_do_painel", "LESTE")
    destino = tmp_path / "dados"
    gera_pasta(str(destino), n_ligacoes=120, n_grupos=4, n_meses=2)
    (destino / "Cronograma.csv").unlink()
    _cronograma(str(destino / "Cronograma Leitura.xlsx"), ["1", "3"], ["2", "4"], [(7, 2026), (8, 2026), (9, 2026)])
    s = Sessao(str(destino), progresso=lambda pct, desc: None)
    s.preparar()
    ctx = s.ctx
    info = next(i for i in ctx.bases_info if i["tipo"] == "Cronograma")
    assert "6 linha(s) de outras superintendências fora (só LESTE)" in info["extra"]
    assert not ctx.classificacao["ignorados"] or not any("Cronograma" in i["arquivo"] for i in ctx.classificacao["ignorados"])
    b = ctx.base_final
    leste = b[b["Grupo"].isin(["01", "03"]) & (b["Referencia de Leitura"] == "09/2026")]
    assert len(leste) and leste["Qts. Dias"].notna().all()            # grupos da Leste com dias de leitura
    interior = b[b["Grupo"].isin(["02", "04"])]
    assert interior["Qts. Dias"].isna().all()                         # grupos da outra SUP ficaram fora do cronograma
