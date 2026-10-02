# -*- coding: utf-8 -*-
"""Barra de progresso do pipeline.

- Rodando no PC/Colab: barra de texto (tqdm, se estiver instalado).
- Rodando no navegador (Pyodide): o site passa um `callback(percentual, descricao)`.
"""


class Progresso:
    def __init__(self, callback=None, total=100):
        self.callback = callback
        self.total = total
        self.n = 0.0
        self.desc = "Iniciando"
        self._barra = None
        if callback is None:
            try:
                from tqdm.auto import tqdm
                self._barra = tqdm(total=total, desc=self.desc, unit="%",
                                   bar_format="{l_bar}{bar}| {n:.0f}%")
            except ImportError:
                self._barra = None

    def atualiza(self, percentual, descricao):
        percentual = max(0.0, min(float(self.total), float(percentual)))
        self.desc = str(descricao)
        incremento = percentual - self.n
        if incremento > 0:
            self.n = percentual
        if self.callback is not None:
            self.callback(float(self.n), self.desc)
        elif self._barra is not None:
            self._barra.set_description_str(self.desc)
            if incremento > 0:
                self._barra.update(incremento)
        else:
            print(f"[{self.n:5.1f}%] {self.desc}")

    def etapa(self, indice, total, inicio, fim, descricao):
        if total <= 0:
            self.atualiza(fim, descricao)
            return
        self.atualiza(inicio + (fim - inicio) * indice / total, descricao)

    def fecha(self):
        if self.callback is not None:
            self.callback(float(self.total), "Finalizado")
        elif self._barra is not None:
            self._barra.close()
