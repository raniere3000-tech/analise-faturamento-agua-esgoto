# -*- coding: utf-8 -*-
"""Orquestra a análise. Duas fases, para o site poder pausar na conferência do Top 20:

    sessao = Sessao(pasta, progresso=callback)
    top20  = sessao.preparar()            # lê a pasta, monta a base e devolve o Top 20
    sessao.continuar(ajustes)             # aplica ajustes (opcional) e gera os relatórios

Rodando direto (`executar`), as duas fases acontecem em sequência.
"""
import os

from .analises import exporta_top100, monta_dados_resumo_grupo
from .base import monta_base
from .comparativo import calcula_comparativos, define_referencias
from .dados import gera_aba_dados_html
from .previsao import gera_aba_forecast_html
from .dre import gera_aba_dre_html, gera_aba_indiretas_html, gera_filtros_dre_html, gera_info_filtros_json
from .config import NOME_RELATORIO_HTML, NOME_TOP100_XLSX, TEXTO_JUSTIFICATIVA_PADRAO
from .contexto import Contexto
from .orcado_ciclo import gera_tabelas_orcado_ciclo_html
from .painel_html import (gera_card_leitura_html, gera_cards_insights_html, gera_cards_kpis_html,
                          gera_grafico_faturamento_html)
from .progresso import Progresso
from .relatorio import gera_filtro_html, gera_justificativa_html, monta_html
from .tabelas_html import (gera_matriz_migracao_grupos, gera_tabela, gera_tabela_acima_abaixo_minimo,
                           gera_tabela_dados_resumo_html, botao_download_xlsx, gera_tabela_top100_html, monta_quadro_ciclos_situacao)
from .top20 import aplica_ajustes_top20, calcula_top20_maior_consumo


class Sessao:
    def __init__(self, pasta, progresso=None):
        """`progresso`: função opcional `callback(percentual, descricao)` (usada pelo site)."""
        self.ctx = Contexto(pasta=pasta, progresso=Progresso(progresso))
        self.caminho_html = os.path.join(pasta, NOME_RELATORIO_HTML)
        self.caminho_top100 = os.path.join(pasta, NOME_TOP100_XLSX)
        os.makedirs(pasta, exist_ok=True)

    # ---- fase 1 ----
    def preparar(self):
        monta_base(self.ctx)
        return calcula_top20_maior_consumo(self.ctx)

    # ---- fase 2 ----
    def continuar(self, ajustes=None, texto_justificativa=None):
        ctx = self.ctx
        progresso = ctx.progresso
        if ajustes:
            aplica_ajustes_top20(ctx, ajustes)

        print("Colunas relacionadas à situação de leitura/lançamento:",
              [c for c in ctx.base_final.columns if "situa" in c.lower() or "lanc" in c.lower() or "lanç" in c.lower()])

        print("=" * 70)
        print("ETAPA 4/6 — DIAGNÓSTICO")
        print("=" * 70)
        b = ctx.base_final
        print(f"Linhas: {len(b)}")
        print(f"Referências disponíveis: {sorted(b['Referencia de Leitura'].dropna().unique(), key=lambda r: (r[3:], r[:2]))}")
        print(f"Match no consumo: {(b['Encontrado no Consumo'] == 'Sim').sum()}")
        print(f"Sem match: {(b['Encontrado no Consumo'] == 'Não').sum()}")
        print(f"Economia Mista: {(b['Economia Mista'] == 'Sim').sum()}")
        print(f"Grupos com cronograma: {(b['Encontrado no Cronograma'] == 'Sim').sum()}")
        progresso.atualiza(58, "Base processada")

        print("=" * 70)
        print("ETAPA 5/6 — COMPARATIVOS")
        print("=" * 70)
        define_referencias(ctx)
        calcula_comparativos(ctx)
        progresso.atualiza(68, "Comparativos")

        print("📊 Gerando tabelas e insights auxiliares...")
        quadro_ciclos_html, df_ciclos_por_grupo = monta_quadro_ciclos_situacao(ctx)
        progresso.atualiza(74, "Ciclos ativo/cortada finalizado")

        matriz_html = gera_matriz_migracao_grupos(ctx)
        progresso.atualiza(78, "Matriz de migração finalizada")

        tabela_minimo_html, ctx.df_minimo_por_grupo = gera_tabela_acima_abaixo_minimo(ctx)
        progresso.atualiza(82, "Tabela de consumo mínimo finalizada")

        top_agua_df, top_esg_df = exporta_top100(ctx.df_atual, ctx.df_anterior, ctx.ref_atual,
                                                 ctx.ref_anterior, self.caminho_top100)
        progresso.atualiza(86, "Top100 exportado")

        with open(self.caminho_top100, "rb") as f:
            botao_top100 = botao_download_xlsx("Baixar Top 100 (Excel)", NOME_TOP100_XLSX, f.read())
        tabela_top100_agua_html = gera_tabela_top100_html(top_agua_df, "Água", "agua", botao_top100)
        tabela_top100_esgoto_html = gera_tabela_top100_html(top_esg_df, "Esgoto", "esgoto")
        progresso.atualiza(88, "Tabelas Top100 geradas")

        df_resumo_grupo = monta_dados_resumo_grupo(ctx)
        ctx.resultados.update({"resumo": df_resumo_grupo, "ciclos": df_ciclos_por_grupo, "minimo": ctx.df_minimo_por_grupo,
                               "top_agua": top_agua_df, "top_esgoto": top_esg_df})
        progresso.atualiza(90, "Resumo por grupo consolidado")

        cards_kpis_html = gera_cards_kpis_html(df_resumo_grupo)
        grafico_faturamento_html = gera_grafico_faturamento_html(ctx, df_resumo_grupo)
        card_leitura_html = gera_card_leitura_html(ctx, df_resumo_grupo)
        cards_insights_html = gera_cards_insights_html(ctx, ctx.comp_agua, ctx.comp_esgoto, df_ciclos_por_grupo,
                                                       top_agua_df, top_esg_df)
        tabela_dados_resumo_html = gera_tabela_dados_resumo_html(df_resumo_grupo)
        progresso.atualiza(93, "KPIs, gráfico e insights gerados")

        print("=" * 70)
        print("ETAPA 6/6 — GERAÇÃO HTML COM ABAS")
        print("=" * 70)
        if texto_justificativa is None:
            texto_justificativa = TEXTO_JUSTIFICATIVA_PADRAO
        html_final = monta_html(
            ctx,
            alerta_minimo_html=ctx.alerta_minimo_html,
            aviso_ajustes_html=ctx.aviso_ajustes_html,
            filtro_html=gera_filtro_html(ctx),
            cards_kpis_html=cards_kpis_html,
            grafico_faturamento_html=grafico_faturamento_html,
            card_leitura_html=card_leitura_html,
            cards_insights_html=cards_insights_html,
            tabela_dados_resumo_html=tabela_dados_resumo_html,
            justificativa_html=gera_justificativa_html(ctx, texto_justificativa),
            tabela_agua_html=gera_tabela(ctx, ctx.comp_agua, "Comparativo Água Mês a Mês", "agua"),
            tabela_esgoto_html=gera_tabela(ctx, ctx.comp_esgoto, "Comparativo Esgoto Mês a Mês", "esgoto"),
            tabelas_orcado_ciclo_html=gera_tabelas_orcado_ciclo_html(ctx),
            quadro_ciclos_html=quadro_ciclos_html,
            matriz_html=matriz_html,
            tabela_minimo_html=tabela_minimo_html,
            tabela_top100_agua_html=tabela_top100_agua_html,
            tabela_top100_esgoto_html=tabela_top100_esgoto_html,
            aba_dre_html=gera_aba_dre_html(ctx),
            aba_indiretas_html=gera_aba_indiretas_html(ctx),
            aba_dados_html=gera_aba_dados_html(ctx),
            aba_forecast_html=gera_aba_forecast_html(ctx),
            filtros_dre_html=gera_filtros_dre_html(ctx),
            info_filtros_json=gera_info_filtros_json(ctx),
        )
        with open(self.caminho_html, "w", encoding="utf-8") as f:
            f.write(html_final)

        progresso.atualiza(100, "Finalizado")
        progresso.fecha()
        print(f"✅ Relatório gerado em: {self.caminho_html}")
        return ctx.ref_atual, ctx.ref_anterior


def executar(pasta, ajustes=None, progresso=None):
    """Roda a análise completa. Devolve (ref_atual, ref_anterior)."""
    sessao = Sessao(pasta, progresso=progresso)
    sessao.preparar()
    return sessao.continuar(ajustes)
