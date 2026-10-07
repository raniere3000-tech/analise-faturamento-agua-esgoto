# -*- coding: utf-8 -*-
"""Gera planilhas SINTÉTICAS (valores inventados) no mesmo formato dos arquivos reais.

Usado pelos testes e para comparar o resultado do pipeline antes/depois de mudanças.
Nenhum dado de cliente real é usado aqui.
"""
import os
import random

import pandas as pd

CIDADES = ["SAO GONCALO", "MARICA", "ITAOCARA", "CASIMIRO DE ABREU", "CIDADE FORA DA RELACAO"]
CANCELAMENTOS = ["DESCONTO", "ABATIMENTO - M3", "IR MUNICIPAL"]
AVULSOS = [("CORTE NO CAVALETE", 150.0), ("RELIGACAO NO REGISTRO", 90.0), ("LIG. AGUA 3/4\" - VAZAO 3M³/H - ASFALTO", 400.0),
           ("LIG. ESGOTO 150MM VIDRADO - TERRA - ASFALTO", 700.0), ("VIOLACAO DO LACRE RES", 250.0),
           ("VISTORIA", 60.0), ("COBRANÇA DE PARCELAS", 500.0), ("RUBRICA NOVA SEM CLASSE", 10.0)]
MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
CATEGORIAS = ["RESIDENCIAL", "COMERCIAL", "SOCIAL", "PUBLICA", "INDUSTRIAL", "PEQ. COMERCIO"]


def _br(valor):
    """1234.5 -> '1.234,50' (formato da coluna Valor Parcela nos arquivos reais)."""
    s = f"{valor:,.2f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


NOME_MALICIOSO = '<img src=x onerror=alert("xss")> & CIA'


# códigos reais da fatura de ciclo (o último não está na relação de regras.json: cai em "Outros")
SITUACOES_LANCAMENTO = ["01-3EM MAOS", "02-1CAIXA CORREIO", "50-EMITIDO - RETIDA", "71-RETIDA - QUEDA DE CONSUMO F",
                        "73-RETIDA - MED > 2X MED FATUR", "00-7NAO ENTREGUE", "99-CODIGO NOVO"]


def gera_pasta(destino, n_ligacoes=400, n_grupos=8, semente=7, mes_atual=(9, 2026),
               categoria_sem_minimo=True, formato_fatura="xlsx", injeta_cliente_html=False, com_dre=False,
               n_meses=2, grupos_faltando=0, tendencia_atual=1.0):
    """Cria fatura (`n_meses` meses), consumo (1 arquivo por mês) e cronograma em `destino`.
    `grupos_faltando`: os últimos grupos não aparecem no mês atual; `tendencia_atual`: multiplica o consumo do mês atual."""
    rnd = random.Random(semente)
    os.makedirs(destino, exist_ok=True)
    m, a = mes_atual
    meses = []
    for k in range(n_meses - 1, -1, -1):
        t = a * 12 + (m - 1) - k
        meses.append((t % 12 + 1, t // 12))
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
            "cidade": rnd.choice(CIDADES),
        })

    if injeta_cliente_html:
        # ligação com nome com HTML e queda de consumo enorme (precisa aparecer no Top 100)
        ligacoes.append({"lig": "999999", "grupo": grupos[0], "cliente": NOME_MALICIOSO, "categoria": "RESIDENCIAL",
                         "situacao": "ATIVA", "conta": "EM ANALISE", "eco": "Residencial", "n_eco": 1, "base": 500.0})

    fat, consumos = [], {}
    rnd_sit = random.Random(semente + 1)               # sorteio à parte: não muda os demais números gerados
    for (mm, aa) in meses:
        ref_leitura = f"15/{mm:02d}/{aa}"
        linhas_consumo = []
        for l in ligacoes:
            if rnd.random() < 0.03:                       # ligação ausente no mês
                continue
            consumo = max(0.0, l["base"] * rnd.uniform(0.6, 1.3))
            if (mm, aa) == (m, a):
                consumo *= tendencia_atual
            if rnd.random() < 0.05:
                consumo = 0.0
            if l["lig"] == "999999":
                consumo = 10.0 if (mm, aa) == (m, a) else 500.0
            valor_agua = round(consumo * rnd.uniform(4.0, 6.0), 2)
            valor_esg = round(valor_agua * 0.8, 2)
            extras = [(r, -20.0) for r in CANCELAMENTOS] if com_dre and rnd.random() < 0.1 else []
            # grupo que ainda não faturou no mês atual (os sorteios acontecem igual, para comparar com o mês completo)
            falta_no_mes = (mm, aa) == (m, a) and grupos_faltando and l["grupo"] in grupos[-grupos_faltando:]
            sit_lanc = rnd_sit.choices(SITUACOES_LANCAMENTO, [40, 25, 10, 8, 7, 6, 4])[0]
            for rub, val in (("VALOR DE AGUA", valor_agua), ("VALOR DE ESGOTO", valor_esg), ("VALOR DE OUTRO", 3.5), *extras):
                if falta_no_mes:
                    continue
                fat.append({
                    "N. da Ligacao": l["lig"], "Grupo": l["grupo"], "Nome Cliente": l["cliente"],
                    "Categoria": l["categoria"], "Situacao Ligacao": l["situacao"], "Situacao Conta": l["conta"],
                    "Situação Lançamento": sit_lanc, "Rubrica": rub, "Valor Parcela": _br(val),
                    "Data de Vencimento": f"28/{mm:02d}/{aa}", "Referencia de Leitura": ref_leitura,
                    **({"Nome da Localidade": l["cidade"], "Endereco Ligacao": "RUA X, 1"} if com_dre else {}),
                })
            eco = {f"Qtd. Economia {t}": 0 for t in ("Residencial", "Comercial", "Industrial", "Publica", "Outros")}
            eco[f"Qtd. Economia {l['eco']}"] = l["n_eco"]
            leitura = round(rnd.uniform(100, 9000))
            if falta_no_mes:
                continue
            linhas_consumo.append({
                "N. Ligacao": l["lig"], "Leitura Atual": leitura,
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
    if com_dre:
        _gera_dre(destino, rnd, ligacoes, meses, (m, a))
    pd.DataFrame({
        "Grupo": grupos,
        "Data da Leitura": [f"{5 + i:02d}/{m:02d}/{a}" for i in range(len(grupos))],
        "Qts. Dias": [28 + (i % 4) for i in range(len(grupos))],
    }).to_csv(os.path.join(destino, "Cronograma.csv"), sep=";", index=False, encoding="utf-8-sig")
    return destino


def _gera_dre(destino, rnd, ligacoes, meses, mes_atual):
    """Serviço avulso (2 meses) e planilhas de orçado RF / RF SUP no formato dos arquivos reais."""
    linhas = []
    for (mm, aa) in meses:
        for l in ligacoes[:60]:
            rub, val = rnd.choice(AVULSOS)
            linhas.append({"N. da Ligacao": l["lig"], "Nome Cliente": "", "Categoria": l["categoria"],
                           "Nome da Localidade": l["cidade"], "Rubrica": rub, "Valor Parcela": _br(val),
                           "Referencia de Leitura": f"{MESES_ABREV[mm - 1]}/{str(aa)[-2:]}",
                           "Data de Vencimento": f"04/{mm:02d}/{aa}", "Situacao Ligacao": "A-Ativa",
                           "Endereco Ligacao": "RUA X", "Grupo": l["grupo"]})
    pd.DataFrame(linhas).to_csv(os.path.join(destino, "Servico avulso 09-2026.csv"), sep=";", index=False, encoding="utf-8-sig")

    rubricas = ["Faturamento Bruto", "Fat. Bruto de água - Direto", "Fat. Bruto de água - Indireto",
                "Fat. Bruto de esgoto - Direto", "Fat. Bruto de esgoto - Indireto", "(-) Cancelamentos",
                "Economias de Água Faturadas", "Volume de Água Faturado", "RI Cortes/Recorte"]
    colunas = [f"{MESES_ABREV[i]}/26" for i in range(12)]

    def planilha(nome, sups, fator):
        linhas = []
        for sup in sups:
            for rub in rubricas:
                base = 1000.0 if "Cancel" not in rub else -100.0
                linhas.append({"Sup": sup, "Rubrica": rub, **{c: base * fator * (i + 1) for i, c in enumerate(colunas)}})
        pd.DataFrame(linhas).to_excel(os.path.join(destino, nome), index=False)

    # RF antigo (RF3T25): colunas "Soma de dd/mm/aaaa" e linhas numeradas
    antigas = [("01.01.01.01. Fat. Bruto de água - Direto", 2000), ("01.01.01.02. Fat. Bruto de esgoto - Direto", 1000),
               ("01.01.01.06. Cancelamento", -300), ("02.02.01.01. Economias de Água - Faturadas", 50),
               ("02.03.01.01. Vol. Total Faturado - Água", 700), ("01. DRE", 99)]
    pd.DataFrame([{"Sup": "Interior", "Rubrica": rub, **{f"Soma de 01/{i:02d}/2026": v * i for i in range(1, 13)}}
                  for rub, v in antigas]).to_excel(os.path.join(destino, "RF3T25.xlsx"), index=False)
    planilha("RF01T26.xlsx", ["Interior"], 10)
    planilha("RF SUP.xlsx", ["LAGOS", "LESTE"], 6)
