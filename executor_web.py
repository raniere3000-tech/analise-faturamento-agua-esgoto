# -*- coding: utf-8 -*-
"""
Executor do pipeline dentro do navegador (Pyodide).

O site grava os arquivos escolhidos pelo usuário numa pasta virtual,
chama executar() e lê de volta o relatório HTML e os Excel gerados.
A barra de progresso (tqdm) é trocada por uma versão que avisa a página.
"""
import os
import sys
import types


def _instala_barra_web(progresso):
    class BarraWeb:
        def __init__(self, total=100, desc="", **kwargs):
            self.total = total
            self.n = 0.0
            self.desc = desc

        def set_description_str(self, texto):
            self.desc = texto
            progresso(float(self.n), str(texto))

        def update(self, incremento=1):
            self.n += incremento
            progresso(float(self.n), str(self.desc))

        def close(self):
            progresso(float(self.total), "Finalizado")

    mod_tqdm = types.ModuleType("tqdm")
    mod_auto = types.ModuleType("tqdm.auto")
    mod_auto.tqdm = BarraWeb
    mod_tqdm.tqdm = BarraWeb
    mod_tqdm.auto = mod_auto
    sys.modules["tqdm"] = mod_tqdm
    sys.modules["tqdm.auto"] = mod_auto


MARCADOR = "# @@PONTO_DE_EDICAO@@"
_estado = {}


def _saida_json(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)


def preparar(pasta, codigo_script, progresso):
    """Fase 1: lê a pasta, monta a base e devolve o Top 20 (JSON) para o usuário conferir."""
    _instala_barra_web(progresso)
    os.environ["FATURAMENTO_PASTA"] = pasta
    antes, achou, depois = codigo_script.partition(MARCADOR)
    if not achou:
        raise RuntimeError("Marcador do ponto de edição não encontrado no script.")
    escopo = {"__name__": "__main__"}
    exec(compile(antes, "acompanhamento_faturamento.py (parte 1)", "exec"), escopo)
    _estado.clear()
    _estado.update({"escopo": escopo, "depois": depois})
    return _saida_json(escopo["calcula_top20_maior_consumo"]())


def continuar(ajustes_json):
    """Fase 2: aplica os ajustes do usuário (se houver) e gera os relatórios."""
    import json
    escopo, depois = _estado["escopo"], _estado["depois"]
    ajustes = json.loads(ajustes_json or "[]")
    if ajustes:
        escopo["aplica_ajustes_top20"](ajustes)
    exec(compile(depois, "acompanhamento_faturamento.py (parte 2)", "exec"), escopo)
    return escopo.get("REF_ATUAL"), escopo.get("REF_ANTERIOR")
