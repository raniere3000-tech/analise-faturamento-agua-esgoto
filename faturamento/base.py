# -*- coding: utf-8 -*-
"""Monta a base final: fatura + consumo + cronograma."""
import pandas as pd

from .config import COLUNAS_ECONOMIA_TOTAIS
from .leitura import classifica_arquivos, processa_consumo, processa_cronograma, processa_fatura


def _processa_lista(progresso, lista, func, ini, fin, desc):
    resultados = []
    total = len(lista)
    if total == 0:
        progresso.atualiza(fin, desc)
        return resultados
    for i, caminho in enumerate(lista, start=1):
        resultados.append(func(caminho))
        progresso.etapa(i, total, ini, fin, f"{desc} ({i}/{total})")
    return resultados


def monta_base(ctx):
    """Preenche ctx.classificacao, ctx.fatura_total e ctx.base_final."""
    progresso = ctx.progresso

    print("=" * 70)
    print("ETAPA 1/6 — VARREDURA E CLASSIFICAÇÃO DOS ARQUIVOS")
    print("=" * 70)
    ctx.classificacao = classifica_arquivos(ctx.pasta, progresso)

    print("=" * 70)
    print("ETAPA 2/6 — PROCESSAMENTO DOS ARQUIVOS")
    print("=" * 70)
    consumos = _processa_lista(progresso, ctx.classificacao["consumo"], processa_consumo, 18, 29, "Processando consumo")
    consumo_total = pd.concat(consumos, ignore_index=True) if consumos else pd.DataFrame(columns=["N. Ligação_consumo", "Referência"])
    print(f"✅ Consumo: {len(consumo_total)} linhas")

    faturas = _processa_lista(progresso, ctx.classificacao["fatura"], processa_fatura, 29, 40, "Processando faturas")
    fatura_total = pd.concat(faturas, ignore_index=True) if faturas else pd.DataFrame(columns=["N. da Ligacao"])
    print(f"✅ Fatura: {len(fatura_total)} linhas")

    cronogramas = _processa_lista(progresso, ctx.classificacao["cronograma"], processa_cronograma, 40, 45, "Processando cronogramas")
    cronograma_total = (
        pd.concat(cronogramas, ignore_index=True).drop_duplicates(subset="Grupo", keep="last")
        if cronogramas else pd.DataFrame(columns=["Grupo", "Data da Leitura", "Qts. Dias", "Aba/Mês Cronograma"])
    )
    print(f"✅ Cronogramas: {len(cronograma_total)} linhas")

    print("=" * 70)
    print("ETAPA 3/6 — MERGE")
    print("=" * 70)
    progresso.atualiza(47, "Merge base final")

    colunas_conflito = ["Grupo", "Situacao Ligacao", "Situacao Lancamento", "Nome Cliente", "Categoria"]
    consumo_total = consumo_total.drop(columns=[c for c in colunas_conflito if c in consumo_total.columns], errors="ignore")

    base_final = fatura_total.merge(
        consumo_total,
        left_on=["N. da Ligacao", "Referencia de Leitura"],
        right_on=["N. Ligação_consumo", "Referência"],
        how="left",
    )
    base_final["Encontrado no Consumo"] = base_final["N. Ligação_consumo"].notna().map({True: "Sim", False: "Não"})

    base_final = base_final.merge(cronograma_total, on="Grupo", how="left")
    base_final["Encontrado no Cronograma"] = base_final["Qts. Dias"].notna().map({True: "Sim", False: "Não"})

    cols_excl = [c for c in base_final.columns if c.endswith("_consumo") or c.endswith("_cronograma")] + ["N. Ligação_consumo", "Referência"]
    base_final = base_final.drop(columns=cols_excl, errors="ignore")

    for col in list(base_final.columns):
        if col.endswith("_x"):
            col_base = col[:-2]
            col_y = col_base + "_y"
            if col_y in base_final.columns:
                base_final = base_final.drop(columns=[col_y])
            base_final = base_final.rename(columns={col: col_base})

    print(f"✅ Merge final: {len(base_final)} linhas")

    base_final = base_final.rename(columns={"N. da Ligacao": "N. Ligação", "Valor Parcela": "Valor (R$)"})
    colunas_analise = ["Total Economias", "Qtd. Tipos de Economia", "Economia Mista", "Encontrado no Consumo", "Encontrado no Cronograma"]
    colunas_originais = [c for c in base_final.columns if c not in colunas_analise]
    base_final = base_final[colunas_originais + colunas_analise]

    # Medida "Economias_Totais": soma das categorias de economia (sem "Outros"), usada em todas as etapas
    for col in COLUNAS_ECONOMIA_TOTAIS:
        base_final[col] = pd.to_numeric(base_final[col], errors="coerce").fillna(0)
    base_final["Economias_Totais"] = base_final[COLUNAS_ECONOMIA_TOTAIS].sum(axis=1)
    print(f"✅ Coluna 'Economias_Totais' criada — soma de {len(COLUNAS_ECONOMIA_TOTAIS)} categorias")

    progresso.atualiza(52, "Base final pronta")
    ctx.fatura_total = fatura_total
    ctx.base_final = base_final
    return base_final
