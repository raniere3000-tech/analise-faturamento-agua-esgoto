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
    from .config import SUP_POR_CIDADE, chave_texto
    from .leitura import chave_grupo
    grupo_cidade = {chave_grupo(g): c for g, c in (getattr(ctx, "grupo_localidade", None) or {}).items()}

    def sup(r):
        cidade = r.get("Nome da Localidade")
        if cidade is not None and not pd.isna(cidade) and SUP_POR_CIDADE.get(chave_texto(cidade)):
            return SUP_POR_CIDADE[chave_texto(cidade)]
        cidade = grupo_cidade.get(chave_grupo(r.get("Grupo", "")))
        return SUP_POR_CIDADE.get(chave_texto(cidade), "SEM SUP") if cidade else "SEM SUP"
    return sup


def calcula_top20_maior_consumo(ctx, n=20):
    """Todas as ligações com Situacao Conta = EM ANALISE no mês atual (rubrica VALOR DE AGUA),
    ordenadas por Consumo Faturado. Sem a coluna Situacao Conta, devolve só o Top n.
    Valor = água + esgoto da ligação no mês atual."""
    ref = _ref_atual_base(ctx)
    mes = ctx.base_final[ctx.base_final["Referencia de Leitura"] == ref].copy()
    mes["Consumo Faturado"] = pd.to_numeric(mes["Consumo Faturado"], errors="coerce").fillna(0)
    mes["Valor (R$)"] = pd.to_numeric(mes["Valor (R$)"], errors="coerce").fillna(0)
    valor_total = mes.groupby("N. Ligação")["Valor (R$)"].sum()
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
            "consumo": float(r["Consumo Faturado"]),
            "valor": round(float(valor_total.get(r["N. Ligação"], 0)), 2),
        })
    return {"refAtual": ref, "linhas": linhas, "colunaSituacao": col_sit or ""}


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
