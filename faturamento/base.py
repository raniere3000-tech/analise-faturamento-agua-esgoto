# -*- coding: utf-8 -*-
"""Monta a base final: fatura + consumo + cronograma."""
import os

import numpy as np
import pandas as pd

from .config import COLUNAS_ECONOMIA_TODAS, COLUNAS_ECONOMIA_TOTAIS
from .leitura import (chave_grupo, classifica_arquivos, compacta_textos, nome_relativo, processa_avulso, processa_consumo, processa_cronograma,
                      processa_fatura_completa, processa_orcado)


COLUNAS_DESCARTADAS = ["Leitura Atual", "Consumo Medido", "Total Economias", "Qtd. Tipos de Economia", "Mes Lancamento",
                       "Ano Lancamento", "Data de Vencimento", "Aba/Mês Cronograma"]


def localidade_por_grupo(crono):
    """{grupo: cidade} pelo cronograma (coluna Localidade; a mais frequente se o grupo aparecer com mais de uma)."""
    if crono is None or not len(crono) or "Localidade" not in crono.columns:
        return {}
    t = crono.dropna(subset=["Localidade"])
    t = t[~t["Localidade"].astype(str).str.strip().str.lower().isin(["", "nan", "none"])]
    if not len(t):
        return {}
    return t.groupby("Grupo")["Localidade"].agg(lambda s: s.value_counts().index[0]).to_dict()


def sem_repetir_entre_arquivos(frames, chave=None):
    """Junta as tabelas de vários arquivos sem contar duas vezes a mesma linha.
    Uma linha que aparece em mais de um arquivo vale só no primeiro em que aparece; linhas repetidas dentro do mesmo
    arquivo são mantidas (podem ser lançamentos legítimos). `chave`: colunas que identificam a linha (padrão: todas).
    Devolve (tabela, linhas descartadas)."""
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        return pd.DataFrame(), 0
    if len(frames) == 1:
        return frames[0], 0
    tudo = pd.concat([f.assign(__arquivo=i) for i, f in enumerate(frames)], ignore_index=True)
    cols = [c for c in (chave or [c for c in tudo.columns if c != "__arquivo"]) if c in tudo.columns]
    assinatura = pd.util.hash_pandas_object(tudo[cols], index=False)          # sem converter tudo para texto (memória)
    primeiro = tudo.groupby(assinatura.values)["__arquivo"].transform("min")
    manter = tudo["__arquivo"] == primeiro
    return tudo[manter].drop(columns="__arquivo").reset_index(drop=True), int((~manter).sum())


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


def _cruza_cronograma(base, crono):
    """Dias de leitura de cada linha: pelo grupo E mês (Data da Leitura do cronograma = mês da Referencia de Leitura);
    sem esse mês no cronograma, usa a última linha do grupo."""
    cols = ["Data da Leitura", "Qts. Dias", "Aba/Mês Cronograma"]
    if not len(crono):
        return base.assign(**{c: pd.NA for c in cols})
    # cruza pelos pares (grupo, mês) distintos — poucos — e só então espalha nas linhas: não copia a base inteira
    chave = base["Grupo"].map({g: chave_grupo(g) for g in base["Grupo"].dropna().unique()})
    por_mes = crono.dropna(subset=["Referencia Cronograma"]).drop_duplicates(["Grupo", "Referencia Cronograma"], keep="last")
    por_mes = por_mes.set_index(["Grupo", "Referencia Cronograma"])[cols]
    por_grupo = crono.drop_duplicates("Grupo", keep="last").set_index("Grupo")[cols]
    pares = pd.DataFrame({"g": chave.values, "r": base["Referencia de Leitura"].values}).drop_duplicates()
    achados = por_mes.reindex(pd.MultiIndex.from_frame(pares[["g", "r"]])).reset_index(drop=True)
    reserva = por_grupo.reindex(pares["g"].values).reset_index(drop=True)
    faltam = achados["Qts. Dias"].isna()
    for c in cols:
        achados[c] = achados[c].where(~faltam, reserva[c])
    achados.index = pd.MultiIndex.from_frame(pares[["g", "r"]])
    idx_linhas = pd.MultiIndex.from_arrays([chave.values, base["Referencia de Leitura"].values])
    posicoes = achados.index.get_indexer(idx_linhas)
    for c in cols:
        valores = achados[c].to_numpy()
        base[c] = valores[posicoes]
    return base


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
    # a mesma ligação no mesmo mês em dois arquivos de consumo duplicaria as linhas da fatura no cruzamento: vale a primeira
    antes = len(consumo_total)
    consumo_total = consumo_total.drop_duplicates(subset=["N. Ligação_consumo", "Referência"])
    if len(consumo_total) < antes:
        ctx.avisos_base.append(f"{antes - len(consumo_total)} linha(s) de consumo repetidas entre arquivos (mesma ligação e mês) "
                               "foram contadas uma vez só.")
    print(f"✅ Consumo: {len(consumo_total)} linhas")

    faturas_cc = _processa_lista(progresso, ctx.classificacao["fatura"], processa_fatura_completa, 29, 40, "Processando faturas")
    faturas = [f for f, _ in faturas_cc]
    fatura_total, rep_fat = sem_repetir_entre_arquivos(faturas)
    if not len(fatura_total):
        fatura_total = pd.DataFrame(columns=["N. da Ligacao"])
    ctx.cancelamento, rep_canc = sem_repetir_entre_arquivos([c for _, c in faturas_cc])
    avulsos = [processa_avulso(c) for c in ctx.classificacao["avulso"]]
    ctx.avulso, rep_av = sem_repetir_entre_arquivos(avulsos)
    for qtd, tipo in ((rep_fat, "fatura"), (rep_canc, "cancelamento"), (rep_av, "serviço avulso")):
        if qtd:
            ctx.avisos_base.append(f"{qtd} linha(s) de {tipo} que já estavam em outro arquivo foram contadas uma vez só "
                                   "(arquivos com informações sobrepostas).")
    ctx.orcado = {}
    for caminho, aba in ctx.classificacao["orcado"]:
        arquivo = nome_relativo(caminho, ctx.pasta)
        nome = os.path.splitext(os.path.basename(caminho))[0].replace("_", " ").strip()
        if nome in ctx.orcado and ctx.orcado[nome]["arquivo"] != arquivo:     # mesmo nome em outra pasta: inclui a pasta
            nome = os.path.splitext(arquivo)[0].replace("_", " ").strip()
        longo = processa_orcado(caminho, aba)
        if not len(longo):
            print(f"   ⚠️ {arquivo}: orçado sem valores (planilha vazia); ignorado.")
            continue
        tipo = "sup" if "SUP" in nome.upper() else "rf"
        if nome not in ctx.orcado or len(longo) > len(ctx.orcado[nome]["dados"]):
            ctx.orcado[nome] = {"arquivo": arquivo, "tipo": tipo, "dados": longo}
    print(f"✅ Fatura: {len(fatura_total)} linhas")
    if len(fatura_total) and "Referencia de Leitura" in fatura_total.columns:
        sem_ref = int(fatura_total["Referencia de Leitura"].isna().sum())
        if sem_ref:
            ctx.avisos_base.append(f"{sem_ref} linha(s) da fatura com 'Referencia de Leitura' vazia ou em formato não reconhecido "
                                  "ficaram fora da análise.")

    def periodo(serie):
        meses = sorted({m for m in serie.dropna().astype(str) if len(m) == 7}, key=lambda r: (r[3:], r[:2]))
        return ", ".join(meses)
    ctx.bases_info = (
        [{"tipo": "Consumo", "arquivo": nome_relativo(c, ctx.pasta), "linhas": len(d), "periodo": periodo(d["Referência"])}
         for c, d in zip(ctx.classificacao["consumo"], consumos)]
        + [{"tipo": "Fatura", "arquivo": nome_relativo(c, ctx.pasta), "linhas": len(f), "periodo": periodo(f["Referencia de Leitura"]),
            "extra": f"{len(canc)} linhas de cancelamento"} for c, (f, canc) in zip(ctx.classificacao["fatura"], faturas_cc)]
        + [{"tipo": "Serviço avulso", "arquivo": nome_relativo(c, ctx.pasta), "linhas": len(a), "periodo": periodo(a["Referencia"])}
           for c, a in zip(ctx.classificacao["avulso"], avulsos)]
    )

    cronogramas = _processa_lista(progresso, ctx.classificacao["cronograma"], processa_cronograma, 40, 45, "Processando cronogramas")
    cronograma_total = (
        pd.concat(cronogramas, ignore_index=True)
        if cronogramas else pd.DataFrame(columns=["Grupo", "Data da Leitura", "Qts. Dias", "Aba/Mês Cronograma", "Referencia Cronograma"])
    )
    print(f"✅ Cronogramas: {len(cronograma_total)} linhas")
    ctx.grupo_localidade = localidade_por_grupo(cronograma_total)
    if ctx.classificacao["cronograma"] and not len(cronograma_total):
        ctx.avisos_base.append("O cronograma foi encontrado, mas nenhuma linha válida foi lida (são necessárias as colunas Grupo, "
                               "Data da Leitura e Qts. Dias): os dias de leitura ficaram vazios.")
    elif not ctx.classificacao["cronograma"]:
        ctx.avisos_base.append("Nenhum cronograma de leitura reconhecido na pasta (colunas Grupo, Data da Leitura e Qts. Dias): "
                               "os dias de leitura ficaram vazios.")
    ctx.bases_info += [{"tipo": "Cronograma", "arquivo": nome_relativo(c, ctx.pasta), "linhas": len(d),
                        "periodo": periodo(d["Referencia Cronograma"]) if "Referencia Cronograma" in d else "",
                        "extra": f"{d['Grupo'].nunique()} grupos" if len(d) else "nenhuma linha válida"}
                       for c, d in zip(ctx.classificacao["cronograma"], cronogramas)]
    for nome, info in ctx.orcado.items():
        ctx.bases_info.append({"tipo": "Orçado SUP" if info["tipo"] == "sup" else "Orçado RF", "arquivo": info["arquivo"],
                               "linhas": len(info["dados"]), "periodo": periodo(info["dados"]["Referencia"])})

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
    ctx.fatura_total = fatura_total[["Grupo"]].drop_duplicates()     # só os grupos (filtro do relatório)
    del fatura_total, consumo_total                  # libera as tabelas de origem: a base cruzada já tem tudo
    compacta_textos(base_final)
    base_final["Encontrado no Consumo"] = np.where(base_final["N. Ligação_consumo"].notna(), "Sim", "Não")

    base_final = _cruza_cronograma(base_final, cronograma_total)
    base_final["Encontrado no Cronograma"] = np.where(base_final["Qts. Dias"].notna(), "Sim", "Não")
    # ciclos considerados = os grupos que existem na fatura (já cruzada com o consumo); grupos só do cronograma são ignorados
    if len(cronograma_total):
        ciclos = sorted(base_final["Grupo"].dropna().astype(str).str.strip().unique(), key=lambda g: (len(g), g))
        sem = sorted(base_final.loc[base_final["Qts. Dias"].isna(), "Grupo"].dropna().astype(str).str.strip().unique(),
                     key=lambda g: (len(g), g))
        achados = len(ciclos) - len(sem)
        print(f"✅ Cronograma × fatura/consumo: {achados} de {len(ciclos)} ciclos com dias de leitura")
        ctx.cronograma_resumo = {"ciclos": len(ciclos), "achados": achados, "sem": sem}
        if sem:
            ctx.avisos_base.append(f"Ciclos da fatura/consumo sem linha no cronograma ({len(sem)} de {len(ciclos)}): "
                                   + ", ".join(sem[:15]) + (" …" if len(sem) > 15 else "") + " — ficaram sem dias de leitura.")

    # ajustes de colunas sem copiar a tabela (com 2 milhões de linhas, cada cópia pesa centenas de MB no navegador)
    cols_excl = [c for c in base_final.columns if c.endswith("_consumo") or c.endswith("_cronograma")] + ["N. Ligação_consumo", "Referência"]
    cols_excl += [c[:-2] + "_y" for c in base_final.columns if c.endswith("_x") and c[:-2] + "_y" in base_final.columns]
    cols_excl += [c for c in COLUNAS_DESCARTADAS if c in base_final.columns]   # só serviam para ler/cruzar
    base_final.drop(columns=[c for c in dict.fromkeys(cols_excl) if c in base_final.columns], inplace=True)
    novos = {c: c[:-2] for c in base_final.columns if c.endswith("_x")}
    novos.update({"N. da Ligacao": "N. Ligação", "Valor Parcela": "Valor (R$)"})
    base_final.rename(columns=novos, inplace=True)

    print(f"✅ Merge final: {len(base_final)} linhas")
    for col in COLUNAS_ECONOMIA_TODAS:                 # quantidades de economia: inteiros pequenos
        if col in base_final.columns:
            base_final[col] = pd.to_numeric(base_final[col], errors="coerce").fillna(0).astype("int32")

    # Medida "Economias_Totais": soma das categorias de economia (sem "Outros"), usada em todas as etapas
    for col in COLUNAS_ECONOMIA_TOTAIS:
        base_final[col] = pd.to_numeric(base_final[col], errors="coerce").fillna(0)
    base_final["Economias_Totais"] = base_final[COLUNAS_ECONOMIA_TOTAIS].sum(axis=1)
    print(f"✅ Coluna 'Economias_Totais' criada — soma de {len(COLUNAS_ECONOMIA_TOTAIS)} categorias")

    # serviço da linha (A = água, E = esgoto), calculado uma vez por rubrica distinta: evita buscar texto a cada cálculo
    rub = base_final["Rubrica"].astype(str)
    unicas = rub.unique()
    base_final["__serv"] = rub.map({r: "E" if "ESGOTO" in r.upper() else "A" if "AGUA" in r.upper() else "" for r in unicas})

    progresso.atualiza(52, "Base final pronta")
    ctx.base_final = base_final
    return base_final
