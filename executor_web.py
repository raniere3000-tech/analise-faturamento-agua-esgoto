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


def continuar(ajustes_json, ref=None):
    """Fase 2. Devolve (referência atual, referência anterior). `ref`: mês escolhido no filtro do painel (refaz a
    análise daquele mês com a base já lida)."""
    ajustes = json.loads(ajustes_json or "[]")
    return _estado["sessao"].continuar(ajustes, ref=ref or None)


def grandes_clientes(lista_json, caminho):
    """Excel de Grandes Clientes (botão "GC" da aba Dados): grava o .xlsx em `caminho` e devolve JSON com o nome do
    arquivo e quantas matrículas foram encontradas. `lista_json`: [{mat, tipo}] (planilha da pasta + adicionadas)."""
    from faturamento.grandes_clientes import gera_xlsx_gc
    conteudo, _, info = gera_xlsx_gc(_estado["sessao"].ctx, json.loads(lista_json or "[]"))
    with open(caminho, "wb") as f:
        f.write(conteudo)
    return json.dumps(info, ensure_ascii=False)


def grandes_clientes_dados(lista_json):
    """Dados das matrículas GC para a tela da aba Dados (as adicionadas no relatório não vêm embutidas)."""
    from faturamento.grandes_clientes import dados_gc
    return json.dumps(dados_gc(_estado["sessao"].ctx, json.loads(lista_json or "[]")), ensure_ascii=False)


def acompanhamento(sup, fotos_json, caminho, ref=None, orcados_json=None):
    """Export "Acompanhamento Mensal" (botão do site): grava o .xlsx em `caminho` e devolve JSON com o nome do arquivo
    e a "foto" do realizado acumulado das indiretas, que o site guarda no ajustes_relatorio.json para o próximo export."""
    from faturamento.acompanhamento import dados_acompanhamento, gera_xlsx, nome_arquivo
    ctx = _estado["sessao"].contexto_do_mes(ref or None)      # o mês que está na tela (None = o mais recente)
    orc = json.loads(orcados_json or "{}")                    # orçados escolhidos no botão (vazio = os padrões)
    dados = dados_acompanhamento(ctx, sup or "TODAS", orc.get("ciclo") or None, orc.get("indiretas") or None)
    conteudo, foto = gera_xlsx(dados, json.loads(fotos_json or "[]"))
    with open(caminho, "wb") as f:
        f.write(conteudo)
    return json.dumps({"nome": nome_arquivo(dados), "foto": foto, "ref": dados["ref"], "sup": dados["sup"]}, ensure_ascii=False)
