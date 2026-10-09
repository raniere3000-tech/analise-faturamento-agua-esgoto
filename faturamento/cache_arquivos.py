# -*- coding: utf-8 -*-
"""Arquivos já lidos em análises anteriores (guardados no navegador): não são lidos de novo.

O site (analisador.worker.js) guarda, para cada arquivo da pasta, o resultado já processado da leitura
(classificação e tabela pronta) e, na próxima análise, compara cada arquivo pelo caminho, tamanho e data de alteração:
  - arquivo igual ao guardado: o site grava no lugar dele um arquivo vazio e entrega o resultado guardado
    (pasta CACHE_DIR/entrada/<id>/<etapa>.pkl.gz) — a leitura é pulada;
  - arquivo novo ou alterado: é lido normalmente e o resultado vai para CACHE_DIR/saida/<id>/, que o site guarda.
CACHE_DIR/meta.json diz, para cada arquivo (caminho relativo à pasta), o id, o tamanho real e se veio do cache.
Sem meta.json (uso local, testes) nada muda: tudo é lido do arquivo.
"""
import gzip
import json
import os
import pickle

VERSAO = "2"            # mude quando a leitura dos arquivos mudar: o que foi guardado com outra versão é descartado
CACHE_DIR = os.environ.get("FATURAMENTO_CACHE", "/cache")

_estado = {"pasta": None, "meta": {}, "lidos": set(), "reaproveitados": set()}


def configura(pasta):
    """Chamado no começo de cada análise: lê o meta.json do site (se houver) e zera os contadores."""
    meta = {}
    caminho = os.path.join(CACHE_DIR, "meta.json")
    if os.path.exists(caminho):
        try:
            with open(caminho, encoding="utf-8") as f:
                dados = json.load(f)
            if str(dados.get("versao")) == VERSAO:
                meta = dados.get("arquivos") or {}
        except (OSError, ValueError):
            meta = {}
    _estado.update(pasta=os.path.abspath(pasta), meta=meta, lidos=set(), reaproveitados=set())


def _rel(caminho):
    try:
        return os.path.relpath(os.path.abspath(caminho), _estado["pasta"] or "").replace(os.sep, "/")
    except ValueError:
        return os.path.basename(caminho)


def _info(caminho):
    return _estado["meta"].get(_rel(caminho))


def em_cache(caminho):
    """True se o arquivo é igual ao de uma análise anterior e o resultado da leitura veio guardado."""
    i = _info(caminho)
    return bool(i and i.get("em_cache"))


def tamanho(caminho):
    """Tamanho real do arquivo (o que veio do cache foi gravado vazio no lugar dele)."""
    i = _info(caminho)
    if i and i.get("tamanho") is not None:
        return int(i["tamanho"])
    return os.path.getsize(caminho)


def _arquivo(pasta, caminho, etapa):
    i = _info(caminho)
    if not i or not i.get("id"):
        return None
    nome = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(etapa))
    return os.path.join(CACHE_DIR, pasta, str(i["id"]), nome + ".pkl.gz")


def carrega(caminho, etapa):
    """Resultado guardado da etapa (ou None se não houver: aí o arquivo é lido normalmente)."""
    if not em_cache(caminho):
        return None
    arq = _arquivo("entrada", caminho, etapa)
    if not arq or not os.path.exists(arq):
        return None
    try:
        with gzip.open(arq, "rb") as f:
            obj = pickle.load(f)
    except Exception:            # guardado corrompido/antigo: lê o arquivo de verdade
        return None
    _estado["reaproveitados"].add(_rel(caminho))
    return obj


def guarda(caminho, etapa, obj):
    """Guarda o resultado da leitura para o site salvar no navegador (só arquivos que vieram de verdade)."""
    _estado["lidos"].add(_rel(caminho))
    if em_cache(caminho):
        return
    arq = _arquivo("saida", caminho, etapa)
    if not arq:
        return
    try:
        os.makedirs(os.path.dirname(arq), exist_ok=True)
        with gzip.open(arq, "wb", compresslevel=3) as f:
            pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:     # sem espaço / objeto que não serializa: segue sem guardar
        print(f"   ⚠️ Não foi possível guardar a leitura de {_rel(caminho)} para a próxima vez ({exc}).")


def memo(caminho, etapa, funcao):
    """Resultado guardado da etapa; sem ele, executa funcao() e guarda."""
    obj = carrega(caminho, etapa)
    if obj is not None:
        return obj
    obj = funcao()
    guarda(caminho, etapa, obj)
    return obj


def resumo():
    """{lidos, reaproveitados}: quantos arquivos foram lidos agora e quantos vieram de análises anteriores."""
    reap = _estado["reaproveitados"]
    return {"lidos": len(_estado["lidos"] - reap), "reaproveitados": len(reap)}
