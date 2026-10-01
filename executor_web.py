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


def executar(pasta, codigo_script, progresso):
    _instala_barra_web(progresso)
    os.environ["FATURAMENTO_PASTA"] = pasta
    escopo = {"__name__": "__main__"}
    exec(compile(codigo_script, "acompanhamento_faturamento.py", "exec"), escopo)
    return escopo.get("REF_ATUAL"), escopo.get("REF_ANTERIOR")
