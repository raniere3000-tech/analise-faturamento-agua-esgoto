# -*- coding: utf-8 -*-
"""Análise de faturamento de água e esgoto (comparativo mês atual x mês anterior)."""
from .pipeline import Sessao, executar  # noqa: F401

__all__ = ["Sessao", "executar"]
