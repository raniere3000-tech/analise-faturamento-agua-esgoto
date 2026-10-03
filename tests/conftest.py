# -*- coding: utf-8 -*-
import os
import shutil
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "tests"))

from dados_sinteticos import gera_pasta  # noqa: E402
from faturamento import Sessao           # noqa: E402


@pytest.fixture(scope="session")
def pasta_modelo(tmp_path_factory):
    """Pasta com planilhas sintéticas (400 ligações, 8 grupos, set/2026 x ago/2026)."""
    destino = tmp_path_factory.mktemp("modelo")
    gera_pasta(str(destino))
    return str(destino)


@pytest.fixture(scope="session")
def analise(pasta_modelo, tmp_path_factory):
    """Roda o pipeline completo uma vez e devolve a sessão (com o contexto)."""
    destino = tmp_path_factory.mktemp("analise") / "dados"
    shutil.copytree(pasta_modelo, destino)
    sessao = Sessao(str(destino), progresso=lambda pct, desc: None)
    sessao.preparar()
    sessao.continuar()
    return sessao


@pytest.fixture
def pasta_pequena(tmp_path):
    """Pasta pequena (rápida) para testes que precisam rodar o pipeline várias vezes."""
    destino = tmp_path / "dados"
    gera_pasta(str(destino), n_ligacoes=120, n_grupos=4)
    return str(destino)
