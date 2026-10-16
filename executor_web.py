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


def acompanhamento(sup, fotos_json, caminho):
    """Export "Acompanhamento Mensal" (botão do site): grava o .xlsx em `caminho` e devolve JSON com o nome do arquivo
    e a "foto" do realizado acumulado das indiretas, que o site guarda no ajustes_relatorio.json para o próximo export."""
    from faturamento.acompanhamento import dados_acompanhamento, gera_xlsx, nome_arquivo
    ctx = _estado["sessao"].ctx
    dados = dados_acompanhamento(ctx, sup or "TODAS")
    conteudo, foto = gera_xlsx(dados, json.loads(fotos_json or "[]"))
    with open(caminho, "wb") as f:
        f.write(conteudo)
    return json.dumps({"nome": nome_arquivo(dados), "foto": foto, "ref": dados["ref"], "sup": dados["sup"]}, ensure_ascii=False)
