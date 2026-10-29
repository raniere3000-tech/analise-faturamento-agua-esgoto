# -*- coding: utf-8 -*-
"""Modelos de planilha de orçado sem a coluna Sup: RF1T26 (coluna "Rubrica"), RF2T26 (coluna com o nome da SUP, "Leste")
e RF3T | 2025 (linhas numeradas, título do RF no cabeçalho). Cada linha cai na mesma linha da DRE nos três modelos."""
import os

import pandas as pd
import pytest

from dados_sinteticos import gera_pasta
from faturamento import Sessao
from faturamento.config import chave_texto
from faturamento.dados import NOME_LINHA_DRE
from faturamento.dre import linha_do_orcado
from faturamento.leitura import _classifica_um, processa_orcado

RF2T26 = ["▸ Faturamento Bruto  ", "▸ Fat. Bruto de água - Direto  ", "▸ Fat. Bruto de água - Indireto  ", "CORTE", "RELIGAÇÃO",
          "LNA", "SANÇÃO", "▸ Fat. Bruto de esgoto - Direto  ", "▸ Fat. Bruto de esgoto - Indireto  ", "▸ Faturamento Líquido  ",
          "▸ Total Cut-off  ", "▸ Cut-off  ", "(=) Receita Bruta de Impostos", "▸ (-) Impostos s/ a receita  ", "▸ PIS  ",
          "▸ Cofins  ", "(=) Receita Líquida", "▸ (-) Custos Operacionais  ", "▸ Diretos  ", "▸ Indiretos  ",
          "(-) Custos de Concessão", "▸ Arrendamento Mercantil  ", "▸ (-) PECLD  ", "Outras Receitas e Despesas",
          "(=) EBITDA Gerencial", "▸ (-) Custos com Partes Relacionadas  ", "(=) EBITDA Contábil", "▸ FLUXO DE CAIXA  ",
          "▸ (+) Arrecadação  ", "▸ Indicadores Operacionais  ", "▸ Economias de Água Faturadas  ",
          "▸ Economias de Esgoto Faturadas  ", "▸ Volume de Água Faturado  ", "▸ Volume de Esgoto Faturado  "]
RF1T26 = [r for r in RF2T26 if "Partes Relacionadas" not in r]
RF1T26.insert(RF1T26.index("▸ Faturamento Líquido  "), "(-) Cancelamentos")
RF3T = ["01. DRE", "01.01. Receita Líquida", "01.01.01. Faturamento Líquido", "01.01.01.01. Fat. Bruto de água - Direto",
        "01.01.01.02. Fat. Bruto de esgoto - Direto", "01.01.01.03. Fat. Bruto de Água - Indireto", "CORTE", "RELIGAÇÃO", "LNA",
        "SANÇÃO", "01.01.01.04. Fat. Bruto de esgoto - Indireto", "01.01.01.06. Cancelamento", "01.01.01.05. Fat. Outros",
        "01.01.02. Faturamento Cut-Off", "01.02. Custo", "01.02.01.01. PECLD", "02. COMPONENTES",
        "02.01.01.01. Qtde. Ligações (Ativadas) - Água", "02.02.01. Economias Faturadas - Água",
        "02.02.01.01. Economias de Água - Faturadas", "02.02.02. Economias Faturadas - Esgoto",
        "02.02.02.01. Economias de Esgoto - Faturadas", "02.03.01. Volume Faturado - Água", "02.03.01.01. Vol. Total Faturado - Água",
        "02.03.02. Volume Faturado - Esgoto", "02.03.02.01. Vol. Total Faturado - Esgoto", "05.01.01.01. Arrecadação",
        "06.02.05.01. Cortes - Cavalete", "06.02.06.01. Religação - Cavalete"]

# entendimento das linhas (tabela enviada): linha da planilha → linha da DRE
ENTENDIMENTO = {
    "Fat. Bruto de água - Direto": "DIRETAS ÁGUA", "Fat. Bruto de água - Indireto": "Fat. de água - Indireto",
    "CORTE": "Soma (calculada)", "RELIGAÇÃO": "Soma (calculada)", "LNA": "Soma (calculada)", "SANÇÃO": "Soma (calculada)",
    "Fat. Bruto de esgoto - Direto": "DIRETAS ESGOTO", "Fat. Bruto de esgoto - Indireto": "Fat. de esgoto - Indireto",
    "(-) Cancelamentos": "Cancelamento", "Faturamento Líquido": "não usada na DRE", "Total Cut-off": "não usada na DRE",
    "Cut-off": "não usada na DRE", "(=) Receita Bruta de Impostos": "não usada na DRE",
    "(-) Impostos s/ a receita": "não usada na DRE", "PIS": "não usada na DRE", "Cofins": "não usada na DRE",
    "(=) Receita Líquida": "não usada na DRE", "(-) Custos Operacionais": "não usada na DRE", "Diretos": "não usada na DRE",
    "Indiretos": "não usada na DRE", "(-) Custos de Concessão": "não usada na DRE", "Arrendamento Mercantil": "não usada na DRE",
    "(-) PECLD": "não usada na DRE", "Outras Receitas e Despesas": "não usada na DRE", "(=) EBITDA Gerencial": "não usada na DRE",
    "(=) EBITDA Contábil": "não usada na DRE", "FLUXO DE CAIXA": "não usada na DRE", "(+) Arrecadação": "não usada na DRE",
    "Indicadores Operacionais": "não usada na DRE", "Economias de Água Faturadas": "Economias de Água - Faturadas",
    "Economias de Esgoto Faturadas": "Economias de Esgoto - Faturadas", "Volume de Água Faturado": "Volume de Água - Faturado",
    "Volume de Esgoto Faturado": "Volume de Esgoto - Faturado",
}
# mesmas linhas no RF3T (numeradas, nomes antigos)
ENTENDIMENTO_RF3T = {
    "Fat. Bruto de água - Direto": "DIRETAS ÁGUA", "Fat. Bruto de Água - Indireto": "Fat. de água - Indireto",
    "Fat. Bruto de esgoto - Direto": "DIRETAS ESGOTO", "Fat. Bruto de esgoto - Indireto": "Fat. de esgoto - Indireto",
    "Cancelamento": "Cancelamento", "CORTE": "Soma (calculada)", "Faturamento Líquido": "não usada na DRE",
    "Fat. Outros": "não usada na DRE", "PECLD": "não usada na DRE", "Economias Faturadas - Água": "não usada na DRE",
    "Economias de Água - Faturadas": "Economias de Água - Faturadas", "Economias de Esgoto - Faturadas": "Economias de Esgoto - Faturadas",
    "Vol. Total Faturado - Água": "Volume de Água - Faturado", "Vol. Total Faturado - Esgoto": "Volume de Esgoto - Faturado",
    "Cortes - Cavalete": "não usada na DRE",
}


def destino(rubrica):
    """Mesmo texto do quadro "Orçado: linhas reconhecidas" da aba Dados."""
    linha = linha_do_orcado(chave_texto(rubrica))
    return NOME_LINHA_DRE.get(linha, "Soma (calculada)" if linha and linha.startswith("ri_") else "não usada na DRE")


def _planilha(caminho, cabecalho, linhas, meses, titulo=None):
    df = pd.DataFrame({cabecalho: linhas, **{m: [1000.0 * (i + 1)] * len(linhas) for i, m in enumerate(meses)}})
    with pd.ExcelWriter(caminho, engine="openpyxl") as w:
        df.to_excel(w, index=False, startrow=2 if titulo else 0)
        if titulo:
            w.sheets["Sheet1"].cell(row=1, column=1, value=titulo)


MESES_26 = ["jan/26", "fev/26", "mar/26", "abr/26", "mai/26", "jun/26", "jul/26", "ago/26", "set/26", "out/26", "nov/26", "dez/26"]


@pytest.mark.parametrize("rubrica,esperado", list(ENTENDIMENTO.items()) + list(ENTENDIMENTO_RF3T.items()))
def test_entendimento_de_cada_linha(rubrica, esperado):
    assert destino(rubrica) == esperado


@pytest.mark.parametrize("nome,cabecalho,linhas,meses,titulo,sup", [
    ("RF2T26.xlsx", "Leste", RF2T26, MESES_26, None, "LESTE"),
    ("RF1T26.xlsx", "Rubrica", RF1T26, MESES_26, None, ""),
    ("RF3T 2025.xlsx", "RF3T | 2025", RF3T, [f"{m[:3]}/25" for m in MESES_26], None, ""),
    ("RF3T Leste.xlsx", "RF3T | 2025", RF3T, ["2025-%02d-01 00:00:00" % i for i in range(1, 13)], "Orçado RF3T", "LESTE"),
    ("RF1T26 marco.xlsx", "Rubrica", RF1T26, ["janeiro/2026", "fevereiro/2026", "março/2026"], None, ""),
])
def test_modelos_sem_coluna_sup_sao_lidos(tmp_path, nome, cabecalho, linhas, meses, titulo, sup):
    caminho = str(tmp_path / nome)
    _planilha(caminho, cabecalho, linhas, meses, titulo)
    assert _classifica_um(caminho, nome).get("tipo") == "orcado"
    longo = processa_orcado(caminho, 0)
    assert set(longo["Sup"]) == {sup}
    assert len(set(longo["Referencia"])) == len(meses) and longo["Referencia"].str.match(r"^\d{2}/\d{4}$").all()
    # todas as linhas da planilha estão lá (sem o "▸" e sem a numeração do RF3T) e com o mesmo entendimento da tabela
    tabela = {**ENTENDIMENTO, **ENTENDIMENTO_RF3T}
    lidas = set(longo["Rubrica"])
    for r in lidas:
        chave = r.replace("▸", "").strip()
        if chave in tabela:
            assert destino(r) == tabela[chave], r
    assert len(lidas) == len(linhas)


def test_rf2t26_leste_entra_na_dre_do_painel(tmp_path):
    destino_pasta = tmp_path / "dados"
    gera_pasta(str(destino_pasta), n_ligacoes=120, n_grupos=4)
    _planilha(str(destino_pasta / "RF2T26.xlsx"), "Leste", RF2T26, MESES_26)
    _planilha(str(destino_pasta / "RF3T 2025.xlsx"), "RF3T | 2025", RF3T, [f"{m[:3]}/26" for m in MESES_26])
    s = Sessao(str(destino_pasta), progresso=lambda pct, desc: None)
    s.preparar()
    s.continuar()
    from faturamento import dre
    ctx = s.ctx
    assert {"RF2T26", "RF3T 2025"} <= set(ctx.orcado)
    leste = dre.orcado(ctx, "RF2T26", "LESTE")                        # set/26 = 9º mês → 9000 em cada linha
    assert leste["dA"] == pytest.approx(9000) and leste["iA"] == pytest.approx(9000) and leste["volE"] == pytest.approx(9000)
    assert not any(v for v in dre.orcado(ctx, "RF2T26", "INTERIOR").values() if v)
    # RF3T sem SUP, numa análise com duas SUPs: entra só no total, com aviso na aba Dados
    assert dre.orcado(ctx, "RF3T 2025", dre.TODAS)["dA"] == pytest.approx(9000)
    html = open(s.caminho_html, encoding="utf-8").read()
    assert "RF3T 2025.xlsx: a planilha não diz a superintendência" in html
    assert not any("RF2T26" in i["arquivo"] or "RF3T" in i["arquivo"] for i in ctx.classificacao["ignorados"])
