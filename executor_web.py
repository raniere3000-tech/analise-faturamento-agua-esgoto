# -*- coding: utf-8 -*-
"""
Ponte entre o site (Pyodide) e o pacote `faturamento`.

O site grava os arquivos escolhidos numa pasta virtual e chama as duas fases:
  preparar()  -> lê a pasta, monta a base e devolve o Top 20 (JSON) para o usuário conferir
  continuar() -> aplica os ajustes (se houver) e gera o relatório e os Excel
"""
import json
import sys

sys.path.insert(0, "/app")

try:
    from faturamento import Sessao  # noqa: E402
except ModuleNotFoundError as erro:  # worker antigo guardado no cache do navegador
    raise ModuleNotFoundError(
        "Os arquivos do programa não foram carregados (versão antiga em cache no navegador). "
        "Pressione Ctrl+F5 para recarregar a página e tente de novo.") from erro

_estado = {}


def preparar(pasta, progresso):
    """Fase 1. `progresso(percentual, descricao)` é uma função JavaScript do site."""
    sessao = Sessao(pasta, progresso=progresso)
    _estado["sessao"] = sessao
    return json.dumps(sessao.preparar(), ensure_ascii=False)


def continuar(ajustes_json):
    """Fase 2. Devolve (referência atual, referência anterior)."""
    ajustes = json.loads(ajustes_json or "[]")
    return _estado["sessao"].continuar(ajustes)
