# -*- coding: utf-8 -*-
"""Conferência do Top 20 (ligações EM ANALISE) e ajustes manuais opcionais."""
import pandas as pd

from .config import SITUACAO_CONTA_EM_ANALISE
from .formatacao import normaliza_texto, ref_mais_recente


def _ref_atual_base(ctx):
    return ref_mais_recente(ctx.base_final["Referencia de Leitura"].dropna().unique())


def _coluna_situacao_conta(ctx):
    for c in ctx.base_final.columns:
        if normaliza_texto(c).startswith("SITUACAO CONTA"):
            return c
    return None


def _sup_da_linha(ctx):
    """Superintendência de uma linha: pela cidade da ligação; senão pela cidade do grupo no cronograma (Localidade)."""
    from .config import SUP_POR_CIDADE, chave_texto, sup_da_localidade
    from .leitura import chave_grupo
    grupo_cidade = {chave_grupo(g): c for g, c in (getattr(ctx, "grupo_localidade", None) or {}).items()}

    def sup(r):
        cidade = r.get("Nome da Localidade")
        if cidade is not None and not pd.isna(cidade) and SUP_POR_CIDADE.get(chave_texto(cidade)):
            return SUP_POR_CIDADE[chave_texto(cidade)]
        cidade = grupo_cidade.get(chave_grupo(r.get("Grupo", "")))
        return (sup_da_localidade(cidade) or "SEM SUP") if cidade else "SEM SUP"
    return sup


def _numero(v):
    """float sem NaN (o resultado vai em JSON para o site); vazio/inválido = 0."""
    v = pd.to_numeric(v, errors="coerce")
    return 0.0 if pd.isna(v) else float(v)


def calcula_top20_maior_consumo(ctx, n=20):
    """Todas as ligações com Situacao Conta = EM ANALISE no mês atual (rubrica VALOR DE AGUA),
    ordenadas por Consumo Faturado. Sem a coluna Situacao Conta, devolve só o Top n.
    Valor = água + esgoto da ligação no mês atual."""
    ref = _ref_atual_base(ctx)
    ref_ant = (pd.to_datetime(ref, format="%m/%Y") - pd.DateOffset(months=1)).strftime("%m/%Y")
    mes, valor_total, consumo_lig = _mes_por_ligacao(ctx, ref)
    _, valor_ant, consumo_ant = _mes_por_ligacao(ctx, ref_ant)
    agua = mes[mes["Rubrica"].str.contains("AGUA", case=False, na=False)]
    col_sit = _coluna_situacao_conta(ctx)
    if col_sit:
        agua = agua[agua[col_sit].map(normaliza_texto) == SITUACAO_CONTA_EM_ANALISE]
    agua = agua.sort_values("Consumo Faturado", ascending=False).drop_duplicates("N. Ligação")
    if not col_sit:            # sem a coluna Situacao Conta, limita ao Top n para não listar a base toda
        agua = agua.head(n)
    sup_da = _sup_da_linha(ctx)
    linhas = []
    for _, r in agua.iterrows():
        linhas.append({
            "ligacao": str(r["N. Ligação"]),
            "grupo": str(r.get("Grupo", "")),
            "cliente": "" if pd.isna(r.get("Nome Cliente")) else str(r.get("Nome Cliente")),
            "categoria": "" if pd.isna(r.get("Categoria")) else str(r.get("Categoria")),
            "situacao": str(r[col_sit]) if col_sit else "",
            "sup": sup_da(r),
            "economias": _numero(r.get("Economias_Totais")),          # economias da ligação no mês (do consumo)
            "consumo": float(r["Consumo Faturado"]),
            "valor": round(float(valor_total.get(r["N. Ligação"], 0)), 2),
            # mês anterior (só para conferência; None = a ligação não faturou no mês anterior)
            "consumo_ant": _ou_none(consumo_ant.get(r["N. Ligação"])),
            "valor_ant": _ou_none(valor_ant.get(r["N. Ligação"]), 2),
        })
    return {"refAtual": ref, "refAnterior": ref_ant, "linhas": linhas, "colunaSituacao": col_sit or "",
            "grupos": _totais_por_grupo(ctx, mes, valor_total, consumo_lig, valor_ant, consumo_ant)}


def _ou_none(v, casas=None):
    if v is None or pd.isna(v):
        return None
    return round(float(v), casas) if casas is not None else float(v)


def _mes_por_ligacao(ctx, ref):
    """(linhas do mês, valor total por ligação, consumo por ligação). Consumo = maior Consumo Faturado das linhas de água
    da ligação (o mesmo número que a conferência mostra e altera)."""
    mes = ctx.base_final[ctx.base_final["Referencia de Leitura"] == ref].copy()
    mes["Consumo Faturado"] = pd.to_numeric(mes["Consumo Faturado"], errors="coerce").fillna(0)
    mes["Valor (R$)"] = pd.to_numeric(mes["Valor (R$)"], errors="coerce").fillna(0)
    valor = mes.groupby("N. Ligação")["Valor (R$)"].sum()
    agua = mes[mes["Rubrica"].str.contains("AGUA", case=False, na=False)]
    consumo = agua.groupby("N. Ligação")["Consumo Faturado"].max()
    return mes, valor, consumo


def _totais_por_grupo(ctx, mes, valor, consumo, valor_ant, consumo_ant):
    """Totais de cada grupo de leitura (todas as ligações do grupo, não só as da conferência): consumo e valor no mês
    atual e no anterior. O site soma a diferença das alterações feitas na tabela a esses totais."""
    from .comparativo import _sup_dos_grupos
    from .leitura import chave_grupo
    if not len(mes):
        return []
    grupo_lig = mes.drop_duplicates("N. Ligação").set_index("N. Ligação")["Grupo"].astype(str)
    t = pd.DataFrame({"grupo": grupo_lig, "valor": valor.reindex(grupo_lig.index).fillna(0),
                      "consumo": consumo.reindex(grupo_lig.index).fillna(0),
                      "valor_ant": valor_ant.reindex(grupo_lig.index), "consumo_ant": consumo_ant.reindex(grupo_lig.index)})
    g = t.groupby("grupo").agg(valor=("valor", "sum"), consumo=("consumo", "sum"), valor_ant=("valor_ant", "sum"),
                               consumo_ant=("consumo_ant", "sum"), ligacoes=("valor", "size"))
    # mês anterior do grupo inteiro (inclusive ligações que não faturaram neste mês)
    base = ctx.base_final
    sup_grupo = _sup_dos_grupos(ctx, base)
    ant = base[base["Referencia de Leitura"] == (pd.to_datetime(mes["Referencia de Leitura"].iloc[0], format="%m/%Y")
                                                    - pd.DateOffset(months=1)).strftime("%m/%Y")]
    if len(ant):
        ga = ant.drop_duplicates("N. Ligação").set_index("N. Ligação")["Grupo"].astype(str)
        g["valor_ant"] = valor_ant.groupby(ga.reindex(valor_ant.index)).sum().reindex(g.index).fillna(0)
        g["consumo_ant"] = consumo_ant.groupby(ga.reindex(consumo_ant.index)).sum().reindex(g.index).fillna(0)
    def chave(x):
        n = chave_grupo(x)
        return (0, int(n)) if n.isdigit() else (1, n)
    return [{"grupo": grp, "sup": sup_grupo.get(chave_grupo(grp), "SEM SUP"), "ligacoes": int(r.ligacoes),
             "consumo": round(float(r.consumo), 2), "valor": round(float(r.valor), 2),
             "consumo_ant": round(float(r.consumo_ant), 2), "valor_ant": round(float(r.valor_ant), 2)}
            for grp, r in sorted(g.iterrows(), key=lambda x: chave(x[0]))]


def aplica_ajustes_top20(ctx, ajustes):
    """ajustes: lista de {ligacao, consumo, valor} (campo None = não alterado).
    Consumo Faturado vale para todas as linhas da ligação no mês atual.
    O valor total novo é repartido entre água e esgoto mantendo a proporção original
    (se o original era 0, vai tudo para a linha de água)."""
    ref = _ref_atual_base(ctx)
    feitos = 0
    for a in ajustes or []:
        lig = str(a.get("ligacao"))
        mask = (ctx.base_final["N. Ligação"].astype(str) == lig) & (ctx.base_final["Referencia de Leitura"] == ref)
        if not mask.any():
            continue
        if a.get("consumo") is not None:
            ctx.base_final.loc[mask, "Consumo Faturado"] = float(a["consumo"])
        if a.get("valor") is not None:
            novo = float(a["valor"])
            vals = pd.to_numeric(ctx.base_final.loc[mask, "Valor (R$)"], errors="coerce").fillna(0)
            antigo = vals.sum()
            if antigo > 0:
                ctx.base_final.loc[mask, "Valor (R$)"] = vals * (novo / antigo)
            else:
                novos = vals * 0
                eh_agua = ctx.base_final.loc[mask, "Rubrica"].str.contains("AGUA", case=False, na=False)
                alvo = (eh_agua[eh_agua].index[:1].tolist() or vals.index[:1].tolist())
                novos.loc[alvo] = novo
                ctx.base_final.loc[mask, "Valor (R$)"] = novos
        feitos += 1
    if feitos:
        print(f"✏️ {feitos} ligação(ões) ajustada(s) manualmente.")
        ctx.ajustes_feitos = feitos
        ctx.aviso_ajustes_html = (
            f'<div class="card" style="border-left:4px solid #C2560C;padding:10px 16px;font-size:.88rem;">'
            f'<strong>Atenção:</strong> este relatório usa {feitos} ligação(ões) da conferência '
            f'com valores ajustados manualmente (referência {ref}).</div>'
        )
