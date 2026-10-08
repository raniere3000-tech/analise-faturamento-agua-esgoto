# -*- coding: utf-8 -*-
"""Arquivos já lidos numa análise anterior não são lidos de novo (o site guarda o resultado no navegador)."""
import json
import os
import shutil

import pandas as pd
import pytest

from dados_sinteticos import gera_pasta
from faturamento import Sessao, cache_arquivos


def _roda(pasta):
    s = Sessao(str(pasta), progresso=lambda p, t: None)
    info = s.preparar()
    return s, info


def test_segunda_analise_reaproveita_os_arquivos_ja_lidos(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(cache_arquivos, "CACHE_DIR", str(cache))
    pasta = tmp_path / "dados"
    gera_pasta(str(pasta), com_dre=True)
    arquivos = sorted(os.path.relpath(os.path.join(r, f), pasta).replace(os.sep, "/")
                      for r, _, fs in os.walk(pasta) for f in fs)
    ids = {rel: f"id{i}" for i, rel in enumerate(arquivos)}

    # 1ª análise: nada guardado; o site pede para guardar tudo (pasta saida)
    meta = {"versao": cache_arquivos.VERSAO,
            "arquivos": {rel: {"id": ids[rel], "tamanho": os.path.getsize(pasta / rel), "em_cache": False} for rel in arquivos}}
    cache.mkdir()
    (cache / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    s1, info1 = _roda(pasta)
    assert info1["leitura"]["reaproveitados"] == 0 and info1["leitura"]["lidos"] == len(arquivos)
    saida = cache / "saida"
    assert sorted(os.listdir(saida)) == sorted(ids.values())

    # 2ª análise: o site entrega o que guardou (pasta entrada) e grava os arquivos vazios no lugar dos originais
    shutil.move(str(saida), str(cache / "entrada"))
    for rel in arquivos:
        meta["arquivos"][rel]["em_cache"] = True
        (pasta / rel).write_bytes(b"")
    (cache / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    s2, info2 = _roda(pasta)
    assert info2["leitura"] == {"lidos": 0, "reaproveitados": len(arquivos)}
    assert not (cache / "saida").exists()                       # nada novo para guardar
    pd.testing.assert_frame_equal(s1.ctx.base_final.reset_index(drop=True), s2.ctx.base_final.reset_index(drop=True))
    assert info1["linhas"] == info2["linhas"] and info1["grupos"] == info2["grupos"]
    assert s2.ctx.orcado.keys() == s1.ctx.orcado.keys()


def test_sem_meta_ou_outra_versao_le_tudo(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(cache_arquivos, "CACHE_DIR", str(cache))
    pasta = tmp_path / "dados"
    gera_pasta(str(pasta))
    (cache / "meta.json").write_text(json.dumps({"versao": "versao-velha", "arquivos": {"Fatura.xlsx": {"id": "x", "em_cache": True}}}),
                                     encoding="utf-8")
    _, info = _roda(pasta)
    assert info["leitura"]["reaproveitados"] == 0 and info["leitura"]["lidos"] > 0
