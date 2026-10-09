# -*- coding: utf-8 -*-
"""Orquestra a análise. Duas fases, para o site poder pausar na conferência do Top 20:

    sessao = Sessao(pasta, progresso=callback)
    top20  = sessao.preparar()            # lê a pasta, monta a base e devolve o Top 20
    sessao.continuar(ajustes)             # aplica ajustes (opcional) e gera os relatórios

Rodando direto (`executar`), as duas fases acontecem em sequência.
"""
import html
import json
import os

from .analitico import gera_analitico_html, seta_detalhe
from .analises import exporta_top100, gera_top100_aumentos, gera_top100_quedas, monta_dados_resumo_grupo
from .base import monta_base
from .comparativo import calcula_comparativos, define_referencias
from .dados import gera_aba_dados_html
from .previsao import gera_aba_forecast_html
from .dre import gera_aba_dre_html, gera_aba_indiretas_html, gera_filtros_dre_html, gera_info_filtros_json
from .config import NOME_RELATORIO_HTML, NOME_TOP100_XLSX, TEXTO_JUSTIFICATIVA_PADRAO
from .contexto import Contexto
from .orcado_ciclo import gera_tabelas_orcado_ciclo_html
from .painel_html import (gera_card_leitura_html, gera_cards_insights_html, gera_cards_kpis_html, gera_destaques_html,
                          gera_grafico_faturamento_html)
from .progresso import Progresso
from .relatorio import gera_filtro_html, gera_justificativa_html, monta_html
from .tabelas_html import (gera_matriz_migracao_grupos, gera_tabela, gera_tabela_acima_abaixo_minimo,
                           gera_tabela_dados_resumo_html, botao_download_xlsx, gera_tabela_top100_html, monta_quadro_ciclos_situacao,
                           xlsx_bytes)
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
        from . import cache_arquivos
        monta_base(self.ctx)
        resultado = calcula_top20_maior_consumo(self.ctx)
        resultado["leitura"] = cache_arquivos.resumo()          # o site mostra quantos arquivos foram lidos / reaproveitados
        return resultado

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
        # Cada etapa avisa ANTES de começar o que está sendo criado (o site mostra o item atual e os já concluídos)
        passo = progresso.atualiza

        print("=" * 70)
        print("ETAPA 5/6 — COMPARATIVOS")
        print("=" * 70)
        passo(59, "Calculando: comparativos de água e esgoto por grupo")
        define_referencias(ctx)
        from .dre import prepara as marca_sup_e_servico
        marca_sup_e_servico(ctx)                       # SUP e serviço (água/esgoto) de cada linha uma vez: as tabelas
                                                       # seguintes usam a marca em vez de procurar texto na Rubrica
        calcula_comparativos(ctx)

        print("📊 Gerando tabelas e insights auxiliares...")
        passo(66, "Criando tabela: Economias faturadas por ciclo (ativas × cortadas)")
        quadro_ciclos_html, df_ciclos_por_grupo = monta_quadro_ciclos_situacao(ctx)

        passo(70, "Criando tabela: Matriz de migração de grupos")
        matriz_html = gera_matriz_migracao_grupos(ctx)

        passo(74, "Criando tabela: Economias acima × abaixo do consumo mínimo")
        tabela_minimo_html, ctx.df_minimo_por_grupo = gera_tabela_acima_abaixo_minimo(ctx)

        passo(78, "Criando tabelas: Top 100 maior queda de consumo (água e esgoto)")
        from .dre import lista_sups, prepara, _nome_sup
        prepara(ctx)                                   # marca a superintendência de cada linha (Top 100 por SUP)
        top_agua_df, top_esg_df = exporta_top100(ctx.df_atual, ctx.df_anterior, ctx.ref_atual,
                                                 ctx.ref_anterior, self.caminho_top100)
        aum_agua_df, aum_esg_df = gera_top100_aumentos(ctx.df_atual, ctx.df_anterior, ctx.ref_atual, ctx.ref_anterior)

        # um conjunto de rankings por superintendência (o filtro Superintendência mostra o da SUP escolhida)
        blocos_queda, blocos_aumento = [], []
        top_por_sup = {}                               # para os Destaques do mês de cada superintendência
        for sup in lista_sups(ctx):
            if sup == "TODAS":
                qa, qe, aa, ae, suf, nome_sup = top_agua_df, top_esg_df, aum_agua_df, aum_esg_df, "", ""
            else:
                # mesma comparação por ligação de Todas (cache), só filtrada pela SUP: não refaz a soma por ligação
                qa, qe = (gera_top100_quedas(ctx.df_atual, ctx.df_anterior, rub, ctx.ref_atual, ctx.ref_anterior, sup=sup)
                          for rub in ("AGUA", "ESGOTO"))
                aa, ae = gera_top100_aumentos(ctx.df_atual, ctx.df_anterior, ctx.ref_atual, ctx.ref_anterior, sup=sup)
                suf, nome_sup = f" ({_nome_sup(sup)})", f" {sup}"
            top_por_sup[sup] = (qa, qe)
            ctx.resultados.setdefault("top_sup", {})[sup] = (qa, qe, aa, ae)      # para os downloads da aba Dados
            sl = "".join(c for c in sup.lower() if c.isalnum())
            ds = html.escape(sup, quote=True)
            # ⬇≡ = ranking completo (todas as ligações com queda/aumento), com o analítico de cada uma
            det = lambda k: seta_detalhe("top-" + k, sup, "Baixar o ranking completo com o analítico por matrícula (CSV)")
            blocos_queda.append(f'<div class="sup-top-bloco" data-sup="{ds}">'
                                + gera_tabela_top100_html(qa, "Água" + suf, "agua-" + sl, det("queda-agua"), chave="queda-agua")
                                + gera_tabela_top100_html(qe, "Esgoto" + suf, "esgoto-" + sl, det("queda-esgoto"), chave="queda-esgoto")
                                + "</div>")
            blocos_aumento.append(f'<div class="sup-top-bloco" data-sup="{ds}">'
                                  + gera_tabela_top100_html(aa, "Água" + suf, "aumento-agua-" + sl, det("aumento-agua"), aumento=True,
                                                            chave="aumento-agua")
                                  + gera_tabela_top100_html(ae, "Esgoto" + suf, "aumento-esgoto-" + sl, det("aumento-esgoto"), aumento=True,
                                                            chave="aumento-esgoto")
                                  + "</div>")
        # candidatos para o filtro de grupos: as 100 maiores de cada grupo (Todas as SUPs), embutidas uma vez
        candidatos = {}
        for chave, rub, aum in (("queda-agua", "AGUA", False), ("queda-esgoto", "ESGOTO", False),
                                ("aumento-agua", "AGUA", True), ("aumento-esgoto", "ESGOTO", True)):
            candidatos[chave] = json.loads(gera_top100_quedas(ctx.df_atual, ctx.df_anterior, rub, ctx.ref_atual, ctx.ref_anterior,
                                                               aumento=aum, por_grupo=True).to_json(orient="split", index=False))
        from .config import DESTAQUE_QUEDA_PCT_TOP100
        candidatos["destaque"] = DESTAQUE_QUEDA_PCT_TOP100
        dados_top = ('<script type="application/json" id="top100-dados">'
                     + json.dumps(candidatos, ensure_ascii=False).replace("</", "<\\/") + "</script>")
        tabela_top100_agua_html, tabela_top100_esgoto_html = "".join(blocos_queda) + dados_top, ""
        passo(80, "Criando tabelas: Top 100 maior aumento de consumo (água e esgoto)")
        tabela_aumento_agua_html, tabela_aumento_esgoto_html = "".join(blocos_aumento), gera_analitico_html(ctx)
        passo(81, "Criando cards: Situação de lançamento (por que analisar cada código)")
        from .situacao_lancamento import gera_cards_situacao_html
        cards_situacao_html = gera_cards_situacao_html(ctx)

        passo(82, "Calculando: resumo consolidado por grupo")
        df_resumo_grupo = monta_dados_resumo_grupo(ctx)
        ctx.resultados.update({"resumo": df_resumo_grupo, "ciclos": df_ciclos_por_grupo, "minimo": ctx.df_minimo_por_grupo,
                               "top_agua": top_agua_df, "top_esgoto": top_esg_df,
                               "aumento_agua": aum_agua_df, "aumento_esgoto": aum_esg_df})

        passo(83, "Criando KPIs do Resumo (8 cards)")
        cards_kpis_html = gera_cards_kpis_html(df_resumo_grupo)
        passo(84, "Criando gráfico: Faturamento total por grupo")
        grafico_faturamento_html = gera_grafico_faturamento_html(ctx, df_resumo_grupo)
        passo(84.5, "Criando quadro: Dias de leitura (média)")
        card_leitura_html = gera_card_leitura_html(ctx, df_resumo_grupo)
        passo(85, "Criando cards: Destaques do mês")
        cards_insights_html = gera_destaques_html(ctx, df_ciclos_por_grupo, top_agua_df, top_esg_df, top_por_sup)
        passo(85.5, "Criando tabela: Resumo consolidado por grupo")
        tabela_dados_resumo_html = gera_tabela_dados_resumo_html(df_resumo_grupo)

        print("=" * 70)
        print("ETAPA 6/6 — GERAÇÃO HTML COM ABAS")
        print("=" * 70)
        if texto_justificativa is None:
            texto_justificativa = TEXTO_JUSTIFICATIVA_PADRAO
        passo(86, "Criando tabelas: Comparativo Água e Esgoto mês a mês")
        tabela_agua_html = gera_tabela(ctx, ctx.comp_agua, "Comparativo Água Mês a Mês", "agua", detalhe="diretas-agua", pendentes=True)
        tabela_esgoto_html = gera_tabela(ctx, ctx.comp_esgoto, "Comparativo Esgoto Mês a Mês", "esgoto", detalhe="diretas-esgoto", pendentes=True)
        passo(87, "Criando tabelas: Orçado por ciclo (água e esgoto)")
        tabelas_orcado_ciclo_html = gera_tabelas_orcado_ciclo_html(ctx)
        passo(88, "Criando aba DRE: tabela realizado × orçado por superintendência e mês")
        aba_dre_html = gera_aba_dre_html(ctx)
        passo(90, "Criando aba Indiretas: orçado × realizado, gráfico de evolução e ticket médio")
        aba_indiretas_html = gera_aba_indiretas_html(ctx)
        passo(92, "Criando aba Forecast: projeção por grupo, indiretas e cancelamento")
        aba_forecast_html = gera_aba_forecast_html(ctx)
        passo(94, "Criando aba Dados: explicação de cada cálculo e bases para download")
        aba_dados_html = gera_aba_dados_html(ctx)
        passo(98, "Montando o relatório final (HTML)")
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
            tabela_agua_html=tabela_agua_html,
            tabela_esgoto_html=tabela_esgoto_html,
            tabelas_orcado_ciclo_html=tabelas_orcado_ciclo_html,
            quadro_ciclos_html=quadro_ciclos_html,
            matriz_html=matriz_html,
            tabela_minimo_html=tabela_minimo_html,
            cards_situacao_html=cards_situacao_html,
            tabela_top100_agua_html=tabela_top100_agua_html,
            tabela_top100_esgoto_html=tabela_top100_esgoto_html,
            tabela_aumento_agua_html=tabela_aumento_agua_html,
            tabela_aumento_esgoto_html=tabela_aumento_esgoto_html,
            aba_dre_html=aba_dre_html,
            aba_indiretas_html=aba_indiretas_html,
            aba_dados_html=aba_dados_html,
            aba_forecast_html=aba_forecast_html,
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
