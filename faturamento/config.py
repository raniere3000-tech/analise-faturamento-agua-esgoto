# -*- coding: utf-8 -*-
"""Constantes e regras de negócio.

As regras que a área de negócio costuma ajustar (consumo mínimo, rubricas, limiares)
ficam em `regras.json`, ao lado deste arquivo — não é preciso mexer no código.
"""
import json
import os

_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_DIR, "regras.json"), encoding="utf-8") as _f:
    REGRAS = json.load(_f)

EXTENSOES_VALIDAS = (".csv", ".xlsx", ".xls")

# Colunas que identificam cada tipo de arquivo
COLUNAS_CONSUMO = {"Leitura Atual", "Consumo Medido", "Consumo Faturado"}
COLUNAS_FATURA = {"Rubrica", "Valor Parcela", "Data de Vencimento"}
COLUNAS_CRONOGRAMA = {"Grupo", "Data da Leitura", "Qts. Dias"}

# Nomes aceitos para a coluna do nº da ligação
NOMES_LIGACAO = ["N. Ligacao", "N. da Ligacao", "N Ligacao", "N. da Ligação", "N. Ligação"]

# "Outros" entra no flag de economia mista, mas NÃO nas Economias_Totais nem no consumo mínimo
COLUNAS_ECONOMIA_TODAS = REGRAS["colunas_economia_todas"]
COLUNAS_ECONOMIA_TOTAIS = REGRAS["colunas_economia_totais"]

RUBRICAS_VALIDAS = REGRAS["rubricas_validas"]
SITUACAO_CONTA_EM_ANALISE = REGRAS["situacao_conta_em_analise"]

CONSUMO_MINIMO_POR_CATEGORIA = REGRAS["consumo_minimo_por_categoria"]
# Coluna de economia -> mínimo (m³) por economia daquele tipo
MINIMO_POR_TIPO_ECONOMIA = {
    coluna: CONSUMO_MINIMO_POR_CATEGORIA[categoria]
    for coluna, categoria in REGRAS["categoria_por_tipo_de_economia"].items()
}

ALERTA_VARIACAO_GRAFICO = REGRAS["alerta_variacao_grafico"]
DESTAQUE_QUEDA_PCT_TOP100 = REGRAS["destaque_queda_pct_top100"]
TEXTO_JUSTIFICATIVA_PADRAO = REGRAS["texto_justificativa_padrao"]

MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

# Arquivos que o próprio pipeline gera (não devem ser lidos como entrada)
NOME_RELATORIO_HTML = "Relatorio_Comparativo.html"
NOME_TOP100_XLSX = "Top100_Quedas_Consumo.xlsx"
NOME_TOP100_AUMENTO_XLSX = "Top100_Aumentos_Consumo.xlsx"
NOMES_SAIDA_LEGADOS = ("Base_Compilada_HISTORICO.xlsx",)

# ---- DRE (aba com orçado RF / orçado SUP / realizado) ----
import re as _re
import unicodedata as _ud


def chave_texto(s):
    """Chave para comparar rubricas/cidades: conserta texto com acento quebrado (ex.: 'CRÃ‰DITO'),
    tira acentos e deixa só letras e números em maiúsculas."""
    s = "" if s is None else str(s)
    for _ in range(3):
        try:
            novo = s.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if novo == s:
            break
        s = novo
    s = _ud.normalize("NFKD", s)
    return _re.sub(r"[^A-Z0-9]", "", s.upper().encode("ascii", "ignore").decode())


CLASSE_INDIRETA_POR_RUBRICA = {chave_texto(r): cl for r, cl in REGRAS["rubricas_indiretas"].items()}
LINHAS_INDIRETAS_DRE = REGRAS["linhas_indiretas_dre"]
CHAVES_CANCELAMENTO = [chave_texto(r) for r in REGRAS["rubricas_cancelamento"]]
SUP_POR_CIDADE = {chave_texto(cidade): sup for sup, cidades in REGRAS["superintendencias"].items() for cidade in cidades}
ALIAS_SUP = {"INTERIOR": "LAGOS"}      # no orçado, "Interior" é a superintendência LAGOS


def sup_da_localidade(texto):
    """SUP de uma Localidade: nome da cidade (relação em regras.json) ou o próprio nome da superintendência
    ("Lagos", "Leste", "Interior" — o cronograma traz assim). None se não reconhecer."""
    if texto is None or (isinstance(texto, float) and texto != texto):
        return None
    k = chave_texto(texto)
    if k in SUP_POR_CIDADE:
        return SUP_POR_CIDADE[k]
    k = ALIAS_SUP.get(k, k)
    return k if k in REGRAS["superintendencias"] else None
