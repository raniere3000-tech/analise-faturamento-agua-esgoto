# -*- coding: utf-8 -*-
"""Forecast dos grupos que ainda não faturaram: economias × volume por economia × tarifa, com tendência do mês.

Para cada grupo que falta, separado para água (A) e esgoto (E):
  economias   = economias do grupo (média ponderada)              × fator de economias
  volume      = economias × volume por economia (média ponderada) × fator de volume
  faturamento = volume × tarifa do grupo (média ponderada)         × fator de tarifa
Média ponderada: com n meses de histórico, o mês mais antigo pesa 1 e o mais recente pesa n.
Fatores (tendência do mês): realizado dos grupos que já faturaram ÷ o que o mesmo método previa para eles.
Como no começo do mês há poucos grupos, o fator é "puxado" para 1 conforme a confiança
(confiança = economias-base dos grupos já faturados ÷ economias-base de todos os grupos).
Faixa provável (~80%): ±1,28 × raiz da soma dos (coef. de variação histórico do grupo × previsão do grupo)².
"""
import math

SERVICOS = ("A", "E")
Z_FAIXA = 1.28                      # ~80% de probabilidade (distribuição normal)


def _pesos(n):
    total = n * (n + 1) / 2
    return [(i + 1) / total for i in range(n)]


def _media_pond(valores):
    if not valores:
        return None
    return sum(w * v for w, v in zip(_pesos(len(valores)), valores))


def base_do_grupo(historico, s):
    """historico: lista de dicts {dA, ecoA, volA, ...} do grupo, do mês mais antigo ao mais recente."""
    d, eco, vol = "d" + s, "eco" + s, "vol" + s
    com_eco = [h for h in historico if h[eco] > 0 and h[vol] > 0]
    if not com_eco:                                   # sem economias/volume: cai para a média ponderada do valor
        return {"eco": 0.0, "vme": 0.0, "tar": 0.0, "simples": True,
                "valor": _media_pond([h[d] for h in historico]) or 0.0,
                "eco_media": _media_pond([h[eco] for h in historico]) or 0.0,
                "vol_media": _media_pond([h[vol] for h in historico]) or 0.0}
    return {"eco": _media_pond([h[eco] for h in com_eco]), "vme": _media_pond([h[vol] / h[eco] for h in com_eco]),
            "tar": _media_pond([h[d] / h[vol] for h in com_eco]), "simples": False}


def _cv(valores):
    """Coeficiente de variação (desvio padrão ÷ média) do histórico; 0 com menos de 2 meses."""
    if len(valores) < 2:
        return 0.0
    m = sum(valores) / len(valores)
    if not m:
        return 0.0
    return math.sqrt(sum((v - m) ** 2 for v in valores) / (len(valores) - 1)) / abs(m)


def projeta(por_mes, refs, atual_grupos, faltam, faturados):
    """por_mes: {ref: {grupo: {dA, ecoA, volA, dE, ecoE, volE}}} do histórico (refs do mais antigo ao mais novo);
    atual_grupos: {grupo: {...}} do mês projetado (só os já faturados). Devolve forecast, fatores, detalhes e faixa."""
    hist = {g: [por_mes[r][g] for r in refs if g in por_mes[r]] for g in set(faltam) | set(faturados)}
    bases = {s: {g: base_do_grupo(h, s) for g, h in hist.items() if h} for s in SERVICOS}
    fatores, total = {}, {k + s: 0.0 for s in SERVICOS for k in ("d", "eco", "vol")}
    grupos = {g: {"meses": [r for r in refs if g in por_mes[r]]} for g in faltam if hist.get(g)}
    var = {k + s: 0.0 for s in SERVICOS for k in ("d", "eco", "vol")}
    for s in SERVICOS:
        b = bases[s]
        lidos = [g for g in faturados if g in b and not b[g]["simples"] and g in atual_grupos]
        esp_eco = sum(b[g]["eco"] for g in lidos)
        real_eco = sum(atual_grupos[g]["eco" + s] for g in lidos)
        esp_vol = sum(atual_grupos[g]["eco" + s] * b[g]["vme"] for g in lidos)
        real_vol = sum(atual_grupos[g]["vol" + s] for g in lidos)
        esp_val = sum(atual_grupos[g]["vol" + s] * b[g]["tar"] for g in lidos)
        real_val = sum(atual_grupos[g]["d" + s] for g in lidos)
        eco_todos = sum(x["eco"] for x in b.values())
        conf = esp_eco / eco_todos if eco_todos else 0.0
        bruto = {"eco": real_eco / esp_eco if esp_eco else 1.0, "vme": real_vol / esp_vol if esp_vol else 1.0,
                 "tar": real_val / esp_val if esp_val else 1.0}
        aplicado = {k: 1 + conf * (v - 1) for k, v in bruto.items()}
        fatores[s] = {"bruto": bruto, "aplicado": aplicado, "confianca": conf, "grupos_lidos": len(lidos)}
        for g in grupos:
            if g not in b:
                continue
            x = b[g]
            if x["simples"]:
                eco, vol, val = x["eco_media"], x["vol_media"], x["valor"]
            else:
                eco = x["eco"] * aplicado["eco"]
                vol = eco * x["vme"] * aplicado["vme"]
                val = vol * x["tar"] * aplicado["tar"]
            grupos[g][s] = {"base": x, "eco": eco, "vol": vol, "valor": val}
            for k, v in (("d", val), ("eco", eco), ("vol", vol)):
                total[k + s] += v
                var[k + s] += (_cv([h[k + s] for h in hist[g]]) * v) ** 2
    faixa = {k: (total[k] - Z_FAIXA * math.sqrt(var[k]), total[k] + Z_FAIXA * math.sqrt(var[k])) for k in total}
    return {"total": total, "fatores": fatores, "grupos": grupos, "faixa": faixa}


def media_simples(por_mes, refs, faltam, n=3):
    """Método antigo: média simples dos últimos n meses de cada grupo (para comparação no backtest)."""
    total = {k + s: 0.0 for s in SERVICOS for k in ("d", "eco", "vol")}
    for g in faltam:
        h = [por_mes[r][g] for r in refs[-n:] if g in por_mes[r]]
        for k in total:
            total[k] += sum(x[k] for x in h) / len(h) if h else 0.0
    return total


def backtest(por_mes_todos, refs_todos, n_faltam, n_hist=6, max_meses=3):
    """Simula meses passados como se os últimos `n_faltam` grupos ainda não tivessem faturado.
    por_mes_todos/refs_todos: todos os meses disponíveis (mais antigo → mais novo). Devolve uma linha por mês testado."""
    linhas = []
    for i in range(len(refs_todos) - 1, 0, -1):
        if len(linhas) >= max_meses:
            break
        alvo, hist_refs = refs_todos[i], refs_todos[max(0, i - n_hist):i]
        if len(hist_refs) < 2:
            break
        grupos_mes = sorted(por_mes_todos[alvo])
        if len(grupos_mes) < 2:
            continue
        k = min(max(1, n_faltam), len(grupos_mes) - 1)
        faltam, faturados = grupos_mes[-k:], grupos_mes[:-k]
        atual = {g: por_mes_todos[alvo][g] for g in faturados}
        novo = projeta(por_mes_todos, hist_refs, atual, faltam, faturados)["total"]
        antigo = media_simples(por_mes_todos, hist_refs, faltam)
        real = {c: sum(por_mes_todos[alvo][g][c] for g in faltam) for c in ("dA", "dE")}
        linha = {"mes": alvo, "faltam": faltam, "real": real, "novo": {c: novo[c] for c in real}, "antigo": {c: antigo[c] for c in real}}
        linha["erro_novo"] = {c: (novo[c] / real[c] - 1) if real[c] else None for c in real}
        linha["erro_antigo"] = {c: (antigo[c] / real[c] - 1) if real[c] else None for c in real}
        linhas.append(linha)
    return linhas
