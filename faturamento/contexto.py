# -*- coding: utf-8 -*-
"""Estado compartilhado de uma análise (substitui as variáveis globais do script antigo)."""
from dataclasses import dataclass, field

import pandas as pd

from .progresso import Progresso


@dataclass
class Contexto:
    pasta: str
    progresso: Progresso
    classificacao: dict = field(default_factory=dict)
    base_final: pd.DataFrame = None
    base_completa: pd.DataFrame = None     # base_final antes de limitar ao último grupo faturado
    fatura_total: pd.DataFrame = None
    cancelamento: pd.DataFrame = None      # linhas da fatura com rubricas de cancelamento
    avulso: pd.DataFrame = None            # serviços avulsos (receita indireta)
    orcado: dict = field(default_factory=dict)   # {"rf": {arquivo, dados}, "sup": {...}} (None se não houver)

    # Meses comparados (preenchidos em `define_referencias`)
    ref_atual: str = ""
    ref_anterior: str = ""
    ultimo_grupo: str = ""      # último grupo com faturamento na última referência
    mes_atual: str = ""
    mes_anterior: str = ""
    mes_atual_curto: str = ""
    mes_anterior_curto: str = ""
    df_atual: pd.DataFrame = None
    df_anterior: pd.DataFrame = None

    # Resultados intermediários
    comp_agua: pd.DataFrame = None
    comp_esgoto: pd.DataFrame = None
    df_minimo_por_grupo: pd.DataFrame = None

    # Avisos exibidos no relatório
    ajustes_feitos: int = 0
    avisos_base: list = field(default_factory=list)   # avisos da leitura dos arquivos (aba Dados)
    bases_info: list = field(default_factory=list)
    aviso_ajustes_html: str = ""
    alerta_minimo_html: str = ""
    categorias_sem_minimo: dict = field(default_factory=dict)
