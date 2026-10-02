# -*- coding: utf-8 -*-
"""Gera planilhas SINTÉTICAS (valores inventados) no mesmo formato dos arquivos reais.

Usado pelos testes e para comparar o resultado do pipeline antes/depois de mudanças.
Nenhum dado de cliente real é usado aqui.
"""
import os
import random

import pandas as pd

CATEGORIAS = ["RESIDENCIAL", "COMERCIAL", "SOCIAL", "PUBLICA", "INDUSTRIAL", "PEQ. COMERCIO"]


def _br(valor):
    """1234.5 -> '1.234,50' (formato da coluna Valor Parcela nos arquivos reais)."""
    s = f"{valor:,.2f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


NOME_MALICIOSO = '<img src=x onerror=alert("xss")> & CIA'


def gera_pasta(destino, n_ligacoes=400, n_grupos=8, semente=7, mes_atual=(9, 2026),
               categoria_sem_minimo=True, formato_fatura="xlsx", injeta_cliente_html=False):
    """Cria fatura (2 meses), consumo (1 arquivo por mês) e cronograma em `destino`."""
    rnd = random.Random(semente)
    os.makedirs(destino, exist_ok=True)
    m, a = mes_atual
    mes_ant, ano_ant = (m - 1, a) if m > 1 else (12, a - 1)
    meses = [(mes_ant, ano_ant), (m, a)]
    grupos = [f"{g:02d}" for g in range(1, n_grupos + 1)]
    categorias = CATEGORIAS + (["CATEGORIA NOVA"] if categoria_sem_minimo else [])

    ligacoes = []
    for i in range(n_ligacoes):
        tipo_eco = rnd.choice(["Residencial"] * 6 + ["Comercial", "Industrial", "Publica", "Outros"])
        ligacoes.append({
            "lig": str(100000 + i),
            "grupo": rnd.choice(grupos),
            "cliente": f"CLIENTE {i:04d}",
            "categoria": rnd.choice(categorias),
            "situacao": rnd.choice(["ATIVA"] * 8 + ["CORTADA"]),
            "conta": "EM ANALISE" if rnd.random() < 0.05 else "NORMAL",
            "eco": tipo_eco,
            "n_eco": rnd.choice([1, 1, 1, 2, 3]),
            "base": rnd.uniform(6, 60),
        })

    if injeta_cliente_html:
        # ligação com nome com HTML e queda de consumo enorme (precisa aparecer no Top 100)
        ligacoes.append({"lig": "999999", "grupo": grupos[0], "cliente": NOME_MALICIOSO, "categoria": "RESIDENCIAL",
                         "situacao": "ATIVA", "conta": "EM ANALISE", "eco": "Residencial", "n_eco": 1, "base": 500.0})

    fat, consumos = [], {}
    for (mm, aa) in meses:
        ref_leitura = f"15/{mm:02d}/{aa}"
        linhas_consumo = []
        for l in ligacoes:
            if rnd.random() < 0.03:                       # ligação ausente no mês
                continue
            consumo = max(0.0, l["base"] * rnd.uniform(0.6, 1.3))
            if rnd.random() < 0.05:
                consumo = 0.0
            if l["lig"] == "999999":
                consumo = 10.0 if (mm, aa) == (m, a) else 500.0
            valor_agua = round(consumo * rnd.uniform(4.0, 6.0), 2)
            valor_esg = round(valor_agua * 0.8, 2)
            for rub, val in (("VALOR DE AGUA", valor_agua), ("VALOR DE ESGOTO", valor_esg), ("VALOR DE OUTRO", 3.5)):
                fat.append({
                    "N. da Ligacao": l["lig"], "Grupo": l["grupo"], "Nome Cliente": l["cliente"],
                    "Categoria": l["categoria"], "Situacao Ligacao": l["situacao"], "Situacao Conta": l["conta"],
                    "Rubrica": rub, "Valor Parcela": _br(val),
                    "Data de Vencimento": f"28/{mm:02d}/{aa}", "Referencia de Leitura": ref_leitura,
                })
            eco = {f"Qtd. Economia {t}": 0 for t in ("Residencial", "Comercial", "Industrial", "Publica", "Outros")}
            eco[f"Qtd. Economia {l['eco']}"] = l["n_eco"]
            linhas_consumo.append({
                "N. Ligacao": l["lig"], "Leitura Atual": round(rnd.uniform(100, 9000)),
                "Consumo Medido": round(consumo, 1), "Consumo Faturado": round(consumo, 1), **eco,
            })
        consumos[(mm, aa)] = pd.DataFrame(linhas_consumo)

    df_fat = pd.DataFrame(fat)
    if formato_fatura == "csv":
        df_fat.to_csv(os.path.join(destino, "Fatura.csv"), sep=";", index=False, encoding="utf-8-sig")
    else:
        df_fat.to_excel(os.path.join(destino, "Fatura.xlsx"), index=False)
    for (mm, aa), df in consumos.items():
        df.to_csv(os.path.join(destino, f"Consumo {mm:02d}-{aa}.csv"), sep=";", index=False, encoding="utf-8-sig")
    pd.DataFrame({
        "Grupo": grupos,
        "Data da Leitura": [f"{5 + i:02d}/{m:02d}/{a}" for i in range(len(grupos))],
        "Qts. Dias": [28 + (i % 4) for i in range(len(grupos))],
    }).to_csv(os.path.join(destino, "Cronograma.csv"), sep=";", index=False, encoding="utf-8-sig")
    return destino
