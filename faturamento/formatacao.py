# -*- coding: utf-8 -*-
"""Formatação de números (padrão brasileiro) e de nomes de mês/texto."""
import unicodedata

from .config import MESES_PT


def normaliza_texto(texto):
    """Maiúsculas, sem acento e sem espaços repetidos (para comparar textos)."""
    txt = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return " ".join(txt.upper().split())


def ref_mais_recente(refs):
    """Maior referência 'MM/AAAA' em ordem cronológica (comparar o texto erraria: '12/2025' > '01/2026')."""
    validas = [r for r in refs if isinstance(r, str) and len(r) == 7 and r[2] == "/"]
    return max(validas, key=lambda r: (r[3:], r[:2])) if validas else None


def nome_mes(ref):
    m, a = ref.split("/")
    return f"{MESES_PT[int(m) - 1]}/{a}"


def nome_mes_curto(ref):
    m, a = ref.split("/")
    return f"{MESES_PT[int(m) - 1][:3]}/{a[-2:]}"


def fmt_num(v, dec=0):
    try:
        if dec == 0:
            return f"{v:,.0f}".replace(",", ".")
        s = f"{v:,.{dec}f}"
        return s.replace(",", "§").replace(".", ",").replace("§", ".")
    except (TypeError, ValueError):
        return "0"


def fmt_moeda_br(v):
    try:
        s = f"{v:,.2f}"
        return s.replace(",", "§").replace(".", ",").replace("§", ".")
    except (TypeError, ValueError):
        return "0,00"


def fmt_int_br(v):
    try:
        return f"{v:,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"
