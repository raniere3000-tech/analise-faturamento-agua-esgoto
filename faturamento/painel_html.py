# -*- coding: utf-8 -*-
"""Blocos do painel Resumo: KPIs, gráfico de faturamento, dias de leitura e destaques."""
import html

from .config import ALERTA_VARIACAO_GRAFICO
from .formatacao import fmt_int_br, fmt_num


def gera_cards_kpis_html(df_resumo):
    t_fatagua_at = df_resumo["FatAgua_Atual"].sum()
    t_fatagua_ant = df_resumo["FatAgua_Anterior"].sum()
    t_fatesgoto_at = df_resumo["FatEsgoto_Atual"].sum()
    t_fatesgoto_ant = df_resumo["FatEsgoto_Anterior"].sum()
    t_eco_at = df_resumo["Eco_Atual"].sum()
    t_eco_ant = df_resumo["Eco_Anterior"].sum()
    t_vol_at = df_resumo["VolFat_Atual"].sum()
    t_vol_ant = df_resumo["VolFat_Anterior"].sum()

    tarifa_at = (t_fatagua_at + t_fatesgoto_at) / t_vol_at if t_vol_at else 0
    tarifa_ant = (t_fatagua_ant + t_fatesgoto_ant) / t_vol_ant if t_vol_ant else 0
    vm_at = t_vol_at / t_eco_at if t_eco_at else 0
    vm_ant = t_vol_ant / t_eco_ant if t_eco_ant else 0
    ticket_at = (t_fatagua_at + t_fatesgoto_at) / t_eco_at if t_eco_at else 0
    ticket_ant = (t_fatagua_ant + t_fatesgoto_ant) / t_eco_ant if t_eco_ant else 0

    def delta_pct(at, ant):
        if not ant:
            return 0
        return (at - ant) / ant * 100

    def card(icone, titulo, field, valor_at, valor_ant, moeda=False, sufixo="", dec=0):
        pct = delta_pct(valor_at, valor_ant)
        seta = "▲" if pct >= 0 else "▼"
        cor = "#1A2740" if pct >= 0 else "#C2560C"
        if moeda:
            valor_txt = "R$ " + fmt_num(valor_at, 2)
        else:
            valor_txt = fmt_num(valor_at, dec) + sufixo
        return f"""
        <div class="kpi-card{' negativo' if pct < 0 else ''}">
            <h3>{titulo}</h3>
            <p class="kpi-valor" data-field="{field}-valor">{valor_txt}</p>
            <p class="kpi-delta" data-field="{field}-delta" style="color:{cor};">{seta} {abs(pct):.1f}% vs mês anterior</p>
        </div>
        """.replace(".1f}", ".1f}".replace(",", "."))

    cards = ""
    cards += card("", "Faturamento Total", "fattotal", t_fatagua_at + t_fatesgoto_at, t_fatagua_ant + t_fatesgoto_ant, moeda=True)
    cards += card("", "Faturamento Água", "fatagua", t_fatagua_at, t_fatagua_ant, moeda=True)
    cards += card("", "Faturamento Esgoto", "fatesgoto", t_fatesgoto_at, t_fatesgoto_ant, moeda=True)
    cards += card("", "Economias Faturadas", "eco", t_eco_at, t_eco_ant)
    cards += card("", "Volume Faturado", "volfat", t_vol_at, t_vol_ant, sufixo=" m³")
    cards += card("", "Tarifa Média", "tarifa", tarifa_at, tarifa_ant, moeda=True)
    cards += card("", "Volume Médio", "vm", vm_at, vm_ant, sufixo=" m³", dec=2)
    cards += card("", "Ticket Médio", "ticket", ticket_at, ticket_ant, moeda=True)
    return cards


def gera_grafico_faturamento_html(ctx, df_resumo):
    labels = [html.escape(str(g), quote=True) for g in df_resumo["Grupo"]]
    atuais = df_resumo["Fat_Atual"].round(2).tolist()
    anteriores = df_resumo["Fat_Anterior"].round(2).tolist()

    # Detecta anomalias: grupos cujo faturamento atual variou mais de 40% vs anterior
    cores_atual = []
    for at, ant in zip(atuais, anteriores):
        variacao = ((at - ant) / ant) if ant else 0
        if variacao > ALERTA_VARIACAO_GRAFICO:
            cores_atual.append("#49668C")   # azul médio — crescimento atípico
        elif variacao < -ALERTA_VARIACAO_GRAFICO:
            cores_atual.append("#E8710A")   # laranja — queda atípica
        else:
            cores_atual.append("#1A2740")   # azul marinho padrão

    return f"""
    <div class="card">
    <h2>Faturamento total por grupo — {ctx.mes_atual} vs {ctx.mes_anterior}</h2>
    <p class="nota-secao">Barras do mês atual em laranja indicam queda acima de 40%; em azul médio, crescimento acima de 40%. Passe o mouse sobre as barras para ver os valores.</p>
    <div class="grafico-area"><canvas id="graficoFaturamento"></canvas></div>
    <script>
    (function() {{
        const ctx = document.getElementById('graficoFaturamento').getContext('2d');

        const listaAtual = {atuais};
        const listaAnterior = {anteriores};

        window.dadosGraficoOriginal = {{
            labels: {labels},
            atual: listaAtual,
            anterior: listaAnterior,
            cores: {cores_atual}
        }};

        const maxValor = Math.max(...listaAtual, ...listaAnterior, 0);

        function formatoCompacto(v) {{
            if (v >= 1000000) return (v / 1000000).toFixed(1).replace('.', ',') + ' mi';
            if (v >= 1000) return (v / 1000).toFixed(0) + ' mil';
            return v.toFixed(0);
        }}

        // ------------------------------------------------------------
        // Plugin customizado: rótulo apenas no dataset "atual", compacto
        // ------------------------------------------------------------
        const plugRotulos = {{
            id: 'rotulosBarras',
            afterDatasetsDraw(chart) {{
                const {{ ctx }} = chart;
                const alturaMinima = chart.chartArea.height * 0.08;
                ctx.save();
                ctx.textAlign = 'center';
                ctx.textBaseline = 'bottom';

                const dataset = chart.data.datasets[1]; // apenas mês atual
                const meta = chart.getDatasetMeta(1);
                meta.data.forEach((bar, i) => {{
                    const valor = dataset.data[i];
                    if (!valor) return;

                    const alturaBarra = chart.chartArea.bottom - bar.y;
                    if (alturaBarra < alturaMinima) return;

                    ctx.fillStyle = '#1A2740';
                    ctx.font = "600 11px 'IBM Plex Sans Condensed', 'Segoe UI', Arial, sans-serif";
                    ctx.fillText(formatoCompacto(valor), bar.x, bar.y - 4);
                }});
                ctx.restore();
            }}
        }};

        Chart.defaults.font.family = "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif";
        Chart.defaults.color = '#394D73';
        window.graficoFaturamentoChart = new Chart(ctx, {{
            type: 'bar',
            data: {{
                labels: {labels},
                datasets: [
                    {{
                        label: '{ctx.mes_anterior}',
                        data: listaAnterior,
                        backgroundColor: '#A7B5CB',
                        borderRadius: 3,
                        categoryPercentage: 0.65,
                        barPercentage: 0.85
                    }},
                    {{
                        label: '{ctx.mes_atual}',
                        data: listaAtual,
                        backgroundColor: {cores_atual},
                        borderRadius: 3,
                        categoryPercentage: 0.65,
                        barPercentage: 0.85
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                layout: {{
                    padding: {{ top: 28 }}
                }},
                plugins: {{
                    legend: {{
                        position: 'top',
                        labels: {{
                            usePointStyle: true,
                            pointStyle: 'circle',
                            font: {{ size: 11 }},
                            generateLabels: function(chart) {{
                                return [
                                    {{ text: '{ctx.mes_anterior}', fillStyle: '#A7B5CB', strokeStyle: '#A7B5CB', pointStyle: 'circle' }},
                                    {{ text: '{ctx.mes_atual}', fillStyle: '#1A2740', strokeStyle: '#1A2740', pointStyle: 'circle' }},
                                    {{ text: 'Alerta (±40%)', fillStyle: '#E8710A', strokeStyle: '#E8710A', pointStyle: 'circle' }}
                                ];
                            }}
                        }}
                    }},
                    tooltip: {{
                        enabled: true,
                        backgroundColor: '#1A2740',
                        titleColor: '#FFFFFF',
                        bodyColor: '#FFFFFF',
                        padding: 10,
                        cornerRadius: 6,
                        callbacks: {{
                            label: function(context) {{
                                const v = context.parsed.y;
                                return context.dataset.label + ': R$ ' + v.toLocaleString('pt-BR', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
                            }}
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        grid: {{ display: false, drawBorder: false }},
                        ticks: {{ font: {{ size: 11 }}, color: '#394D73' }}
                    }},
                    y: {{
                        beginAtZero: true,
                        suggestedMax: maxValor * 1.20,
                        display: false,
                        grid: {{ display: false, drawBorder: false }}
                    }}
                }}
            }},
            plugins: [plugRotulos]
        }});
    }})();
    </script>
    </div>
    """


def media_dias(serie):
    """Média dos dias de leitura só dos grupos com leitura no mês (0 = grupo ainda sem leitura / sem cronograma)."""
    s = serie[serie > 0] if serie is not None else []
    return float(s.mean()) if len(s) else 0.0


def gera_card_leitura_html(ctx, df_resumo):
    # o filtro de grupos / Superintendência refaz as médias no navegador (recalcularKPIsResumo)
    dias_at = media_dias(df_resumo["Dias_Leitura_Atual"]) if len(df_resumo) else 0
    dias_ant = media_dias(df_resumo["Dias_Leitura_Anterior"]) if len(df_resumo) else 0
    diff = dias_at - dias_ant
    cor = "#C2560C" if diff < 0 else "#1A2740"
    return f"""
    <div class="card card-faixa">
    <h2>Dias de leitura (média)</h2>
    <p class="obs-dias">
        {ctx.mes_atual}: <b data-field="dias-media-atual">{fmt_num(dias_at,1)}</b> dias &nbsp;|&nbsp;
        {ctx.mes_anterior}: <b data-field="dias-media-anterior">{fmt_num(dias_ant,1)}</b> dias &nbsp;|&nbsp;
        <span data-field="dias-media-delta" style="color:{cor}; font-weight:700;">Δ {fmt_num(diff,1)} dias</span>
    </p>
    </div>
    """


def gera_cards_insights_html(ctx, comp_agua, comp_esgoto, df_ciclos, top_agua_df, top_esg_df):
    def top_variacao(comp, n=3, crescimento=True):
        c = comp.copy()
        c["Delta"] = c["Faturamento_atual"] - c["Faturamento_anterior"]
        c = c.sort_values("Delta", ascending=not crescimento).head(n)
        itens = ""
        for _, r in c.iterrows():
            itens += f"<li>Grupo {html.escape(str(r['Grupo']))}: faturamento R$ {fmt_num(abs(r['Delta']),2)} {'acima' if crescimento else 'abaixo'}</li>"
        return itens or "<li>Sem dados</li>"

    total_cort_at = int(df_ciclos["Cortada_Atual"].sum()) if not df_ciclos.empty else 0
    total_cort_ant = int(df_ciclos["Cortada_Ant"].sum()) if not df_ciclos.empty else 0
    total_ativa_at = int(df_ciclos["Ativa_Atual"].sum()) if not df_ciclos.empty else 0
    total_ativa_ant = int(df_ciclos["Ativa_Ant"].sum()) if not df_ciclos.empty else 0

    card_cortes = f"""
    <div class="insight-card">
        <h4>Cortes</h4>
        <ul>
            <li>{fmt_int_br(total_cort_at)} ligações cortadas ({fmt_int_br(total_cort_at-total_cort_ant)} vs {ctx.mes_anterior})</li>
            <li>{fmt_int_br(total_ativa_at)} ligações ativas ({fmt_int_br(total_ativa_at-total_ativa_ant)} vs {ctx.mes_anterior})</li>
        </ul>
    </div>
    """

    card_cresc_esgoto = f"""
    <div class="insight-card">
        <h4>Crescimento — Esgoto</h4>
        <ul>{top_variacao(comp_esgoto, crescimento=True)}</ul>
    </div>
    """
    card_cresc_agua = f"""
    <div class="insight-card">
        <h4>Crescimento — Água</h4>
        <ul>{top_variacao(comp_agua, crescimento=True)}</ul>
    </div>
    """
    card_queda_esgoto = f"""
    <div class="insight-card">
        <h4>Queda — Esgoto</h4>
        <ul>{top_variacao(comp_esgoto, crescimento=False)}</ul>
    </div>
    """
    card_queda_agua = f"""
    <div class="insight-card">
        <h4>Queda — Água</h4>
        <ul>{top_variacao(comp_agua, crescimento=False)}</ul>
    </div>
    """

    def top_clientes(df, n=2):
        if df.empty:
            return "<li>Sem dados</li>"
        itens = ""
        for _, r in df.head(n).iterrows():
            itens += f"<li>{r['Ranking']}ª maior queda: {r['N. Ligação']} ({r['Grupo']}) — {fmt_num(r['Queda_Consumo'],0)} m³</li>"
        itens += f"<li>Total de clientes com queda: {len(df)}</li>"
        return itens

    card_top100_esgoto = f"""
    <div class="insight-card">
        <h4>Top 100 — Esgoto</h4>
        <ul>{top_clientes(top_esg_df)}</ul>
    </div>
    """
    card_top100_agua = f"""
    <div class="insight-card">
        <h4>Top 100 — Água</h4>
        <ul>{top_clientes(top_agua_df)}</ul>
    </div>
    """

    return f"""
    <div class="insights-grid">
        {card_cortes}
        {card_cresc_esgoto}
        {card_cresc_agua}
        {card_queda_esgoto}
        {card_queda_agua}
        {card_top100_esgoto}
        {card_top100_agua}
    </div>
    """


def gera_destaques_html(ctx, df_ciclos, top_agua_df, top_esg_df, top_por_sup):
    """Destaques do mês: um quadro por superintendência (LAGOS, LESTE...), cada um só com os dados dela.
    O filtro Superintendência mostra o quadro escolhido (Todas: todos os quadros). Sem SUP identificada, um quadro geral."""
    from .comparativo import monta_comparativo
    from .dre import SEM_SUP, TODAS, _nome_sup, lista_sups
    from .leitura import chave_grupo
    sups = [s for s in lista_sups(ctx) if s not in (TODAS, SEM_SUP)] if "__sup" in ctx.df_atual.columns else []
    titulo = f"Destaques do mês — {ctx.mes_atual}"
    if not sups:
        return (f'<div class="card"><h2>{titulo}</h2>'
                + gera_cards_insights_html(ctx, ctx.comp_agua, ctx.comp_esgoto, df_ciclos, top_agua_df, top_esg_df) + "</div>")
    grupo_sup = getattr(ctx, "grupo_sup", None) or {}
    blocos = []
    for sup in sups:
        at, an = ctx.df_atual[ctx.df_atual["__sup"] == sup], ctx.df_anterior[ctx.df_anterior["__sup"] == sup]
        comp_a, comp_e = monta_comparativo(at, an, "AGUA"), monta_comparativo(at, an, "ESGOTO")
        ciclos = df_ciclos
        if df_ciclos is not None and len(df_ciclos):
            ciclos = df_ciclos[df_ciclos["Grupo"].astype(str).map(lambda g: grupo_sup.get(chave_grupo(g)) == sup)]
        qa, qe = top_por_sup.get(sup, (top_agua_df.iloc[:0], top_esg_df.iloc[:0]))
        blocos.append(f'<div class="card sup-dest" data-sup="{html.escape(sup, quote=True)}"><h2>{titulo} — {html.escape(_nome_sup(sup))}</h2>'
                      + gera_cards_insights_html(ctx, comp_a, comp_e, ciclos, qa, qe) + "</div>")
    return "".join(blocos)
