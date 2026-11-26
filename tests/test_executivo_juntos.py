# -*- coding: utf-8 -*-
"""Executivo Interior + Leste num PDF só: o "Resumo para juntar" de um painel e o PDF único no outro."""
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _le(*partes):
    return open(os.path.join(RAIZ, *partes), encoding="utf-8").read()


def test_menu_do_executivo_tem_juntar_e_resumo():
    idx = _le("index.html")
    assert 'data-modo="juntar"' in idx and 'data-modo="resumo"' in idx
    assert 'id="arqJuntar"' in idx and 'w.gerarExecutivo(await libsPdf(), "juntar", await f.text())' in idx


def test_resumo_e_pdf_unico_no_relatorio():
    js = _le("faturamento", "assets", "relatorio.js")
    for trecho in ("function montaExecutivo(celular, parte)", "function execResumoParaJuntar()", "function execJuntar(libs, texto)",
                   "function execCapaParte(parte, filtros)", "function execGraficoCapa(leste)", "function execCapaHtml(blocos, nomeMes)",
                   "EXEC_RESUMO_TIPO = 'faturamento-executivo-resumo'"):
        assert trecho in js, trecho
    # o painel é identificado pelo prefixo do armazenamento (Leste) e o Interior vem sempre primeiro
    assert "/leste/i.test(e) ? 'LESTE' : 'INTERIOR'" in js
    assert "(a.sup === 'INTERIOR' ? 0 : 1)" in js
    # o Resumo de cada superintendência vai só para a página inicial (um abaixo do outro) e sai das páginas de cada uma
    assert "if (parte && !nome) { cont.appendChild(execCapaParte(parte" in js
    assert "if (!el.classList.contains('exec-capa-parte')) cont.appendChild(el)" in js
    assert "versao: 2" in js and "!(j.versao >= 2)" in js
    # o HTML do arquivo é só conteúdo: scripts e atributos on* saem
    assert "querySelectorAll('script, iframe, object, embed')" in js
    # links da página inicial, volta para ela e marcadores do PDF
    assert "pdf4.link(" in js and "textWithLink('« Página inicial" in js and "outline.add(null, 'Página inicial" in js


def test_cores_da_arrecadacao():
    css = _le("faturamento", "assets", "relatorio.css")
    assert ".exec-capa .cap-leste .cap-tag { background:#16a5b8; }" in css
    assert "#view-executivo .exec-capa .exec-capa-parte.cap-leste { border-top-color:#16a5b8; }" in css
    assert "#view-executivo .exec-parte-leste th { background:#16a5b8 !important;" in css
