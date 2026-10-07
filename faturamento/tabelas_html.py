# -*- coding: utf-8 -*-
"""Tabelas HTML do relatório (comparativo, ciclos, migração de grupos, consumo mínimo, Top 100)."""
import base64
import html
import io

import pandas as pd

from .analises import calcula_minimo_matricula, minimo_matricula_vetorizado
from .config import DESTAQUE_QUEDA_PCT_TOP100, MINIMO_POR_TIPO_ECONOMIA
from .formatacao import fmt_int_br, fmt_moeda_br, fmt_num


def gera_tabela(ctx, comp, titulo, slug, *, com_dias=True, rot_atual=None, rot_ant=None, card_attrs=""):
    rot_atual = rot_atual or ctx.mes_atual_curto
    rot_ant = rot_ant or ctx.mes_anterior_curto
    detalhe = {"dias-atual", "dias-anterior", "vm-atual", "vm-anterior", "delta-vm", "delta-pct-vm"}
    def cl(campo):
        return ' class="x-det"' if campo in detalhe else ""
    def td(campo, valor):
        return f'<td data-field="{campo}"{cl(campo)}>{valor}</td>'
    def deltac(campo, valor, dec=2, pct=False):
        cor = "#C2560C" if valor<0 else "#05050D"
        txt = f"{valor*100:.1f}%".replace(".", ",") if pct else fmt_num(valor,dec)
        return f'<td data-field="{campo}"{cl(campo)} style="color:{cor};">{txt}</td>'
    def linha(grupo, d, is_media=False):
        delta_fat = d["Faturamento_atual"] - d["Faturamento_anterior"]
        delta_eco = d["Economias_atual"] - d["Economias_anterior"]
        delta_pct_eco = (delta_eco / d["Economias_anterior"]) if d["Economias_anterior"] else 0
        delta_vol = d["Volume_Faturado_atual"] - d["Volume_Faturado_anterior"]
        delta_pct_vol = (delta_vol / d["Volume_Faturado_anterior"]) if d["Volume_Faturado_anterior"] else 0
        delta_vm = d["Volume_Medio_atual"] - d["Volume_Medio_anterior"]
        delta_tar = d["Tarifa_Media_atual"] - d["Tarifa_Media_anterior"]
        delta_tic = d["Ticket_Medio_atual"] - d["Ticket_Medio_anterior"]
        pct = lambda dif, ant: (dif / ant) if ant else 0          # Δ % sobre o mês anterior (0 quando não havia base)
        delta_pct_fat = pct(delta_fat, d["Faturamento_anterior"])
        delta_pct_vm = pct(delta_vm, d["Volume_Medio_anterior"])
        delta_pct_tar = pct(delta_tar, d["Tarifa_Media_anterior"])
        delta_pct_tic = pct(delta_tic, d["Ticket_Medio_anterior"])
        g_attr = "" if is_media else html.escape(str(grupo), quote=True)
        classe = "linha-media" if is_media else ""
        attrs=""
        if not is_media:
            attrs = (
                (f'data-dias-atual="{d["Dias_Leitura_atual"]}" data-dias-anterior="{d["Dias_Leitura_anterior"]}" ' if com_dias else "") + (
                f'data-fat-atual="{d["Faturamento_atual"]}" data-fat-anterior="{d["Faturamento_anterior"]}" '
                f'data-eco-atual="{d["Economias_atual"]}" data-eco-anterior="{d["Economias_anterior"]}" '
                f'data-vol-atual="{d["Volume_Faturado_atual"]}" data-vol-anterior="{d["Volume_Faturado_anterior"]}"')
            )
        return f"""
        <tr class="{classe}" data-grupo="{g_attr}" {attrs}>
            {td("grupo", html.escape(str(grupo), quote=True))}
            {td("dias-atual", fmt_num(d["Dias_Leitura_atual"],1)) + td("dias-anterior", fmt_num(d["Dias_Leitura_anterior"],1)) if com_dias else ""}
            {td("fat-atual", fmt_num(d["Faturamento_atual"]))}
            {td("fat-anterior", fmt_num(d["Faturamento_anterior"]))}
            {deltac("delta-fat", delta_fat, dec=0)}
            {deltac("delta-pct-fat", delta_pct_fat, pct=True)}
            {td("eco-atual", fmt_num(d["Economias_atual"]))}
            {td("eco-anterior", fmt_num(d["Economias_anterior"]))}
            {deltac("delta-eco", delta_eco, dec=0)}
            {deltac("delta-pct-eco", delta_pct_eco, pct=True)}
            {td("vol-atual", fmt_num(d["Volume_Faturado_atual"]))}
            {td("vol-anterior", fmt_num(d["Volume_Faturado_anterior"]))}
            {deltac("delta-vol", delta_vol, dec=0)}
            {deltac("delta-pct-vol", delta_pct_vol, pct=True)}
            {td("vm-atual", fmt_num(d["Volume_Medio_atual"],2))}
            {td("vm-anterior", fmt_num(d["Volume_Medio_anterior"],2))}
            {deltac("delta-vm", delta_vm)}
            {deltac("delta-pct-vm", delta_pct_vm, pct=True)}
            {td("tar-atual", fmt_num(d["Tarifa_Media_atual"],2))}
            {td("tar-anterior", fmt_num(d["Tarifa_Media_anterior"],2))}
            {deltac("delta-tar", delta_tar)}
            {deltac("delta-pct-tar", delta_pct_tar, pct=True)}
            {td("tic-atual", fmt_num(d["Ticket_Medio_atual"],2))}
            {td("tic-anterior", fmt_num(d["Ticket_Medio_anterior"],2))}
            {deltac("delta-tic", delta_tic)}
            {deltac("delta-pct-tic", delta_pct_tic, pct=True)}
        </tr>
        """
    linhas_html = ""
    for _, r in comp.iterrows():
        linhas_html += linha(r["Grupo"], r)
    media = {
        "Dias_Leitura_atual": media_dias(comp["Dias_Leitura_atual"]) if len(comp) else 0,      # só grupos com leitura no mês
        "Dias_Leitura_anterior": media_dias(comp["Dias_Leitura_anterior"]) if len(comp) else 0,
        "Faturamento_atual": comp["Faturamento_atual"].sum(),
        "Faturamento_anterior": comp["Faturamento_anterior"].sum(),
        "Economias_atual": comp["Economias_atual"].sum(),
        "Economias_anterior": comp["Economias_anterior"].sum(),
        "Volume_Faturado_atual": comp["Volume_Faturado_atual"].sum(),
        "Volume_Faturado_anterior": comp["Volume_Faturado_anterior"].sum(),
    }
    media["Volume_Medio_atual"] = (media["Volume_Faturado_atual"] / media["Economias_atual"]) if media["Economias_atual"] else 0
    media["Volume_Medio_anterior"] = (media["Volume_Faturado_anterior"] / media["Economias_anterior"]) if media["Economias_anterior"] else 0
    media["Tarifa_Media_atual"] = (media["Faturamento_atual"] / media["Volume_Faturado_atual"]) if media["Volume_Faturado_atual"] else 0
    media["Tarifa_Media_anterior"] = (media["Faturamento_anterior"] / media["Volume_Faturado_anterior"]) if media["Volume_Faturado_anterior"] else 0
    media["Ticket_Medio_atual"] = (media["Faturamento_atual"] / media["Economias_atual"]) if media["Economias_atual"] else 0
    media["Ticket_Medio_anterior"] = (media["Faturamento_anterior"] / media["Economias_anterior"]) if media["Economias_anterior"] else 0
    linhas_html += linha("Total / Média", media, is_media=True)
    sub = f'<th>{rot_atual}</th><th>{rot_ant}</th>'
    subd = f'<th class="x-det">{rot_atual}</th><th class="x-det">{rot_ant}</th>'
    th_dias = '<th colspan="2" class="x-det">Dias Leitura</th>' if com_dias else ""
    dif = '<th>Abs</th><th>%</th>'                     # cada Δ: diferença absoluta e percentual (sobre o mês anterior)
    difd = '<th class="x-det">Abs</th><th class="x-det">%</th>'
    sub_dias = subd if com_dias else ""
    cabecalho = f"""
    <tr class="header-grupo">
        <th rowspan="2">Grupo</th>
        {th_dias}
        <th colspan="2">Faturamento</th>
        <th colspan="2">Δ Fat.</th>
        <th colspan="2">Economias</th>
        <th colspan="2">Δ Economias</th>
        <th colspan="2">Volume Faturado</th>
        <th colspan="2">Δ Volume</th>
        <th colspan="2" class="x-det">Volume Médio</th>
        <th colspan="2" class="x-det">Δ Vol. Médio</th>
        <th colspan="2">Tarifa Média</th>
        <th colspan="2">Δ Tarifa</th>
        <th colspan="2">Ticket Médio</th>
        <th colspan="2">Δ Ticket</th>
    </tr>
    <tr class="header-sub">
        {sub_dias}
        {sub}
        {dif}
        {sub}
        {dif}
        {sub}
        {dif}
        {subd}
        {difd}
        {sub}
        {dif}
        {sub}
        {dif}
    </tr>
    """
    return f"""
    <div class="card"{card_attrs}>
    <h2>{titulo}</h2>
    <table class="tabela-comparativo" id="tabela-{slug}">
        <thead>{cabecalho}</thead>
        <tbody>{linhas_html}</tbody>
    </table>
    </div>
    """


def monta_quadro_ciclos_situacao(ctx):
    print("📊 Montando quadro ciclos (Ativa x Cortada)...")
    df = ctx.base_final
    if "Situacao Ligacao" not in df.columns:
        html_vazio = "<div class='card'><h2>Ciclos (Ativa x Cortada)</h2><p>Coluna 'Situacao Ligacao' não encontrada</p></div>"
        return html_vazio, pd.DataFrame(columns=["Grupo","Ativa_Atual","Ativa_Ant","Cortada_Atual","Cortada_Ant"])

    # ------------------------------------------------------------------
    # Filtra apenas Rubrica AGUA para não duplicar economia (AGUA + ESGOTO)
    # Mesma base usada no Comparativo Água
    # ------------------------------------------------------------------
    # só as linhas e colunas usadas (dois meses, água) — sem copiar a base inteira
    df = df[df["Referencia de Leitura"].isin([ctx.ref_atual, ctx.ref_anterior])]
    agua = (df["__serv"] == "A") if "__serv" in df.columns else df["Rubrica"].str.contains("AGUA", case=False, na=False)
    df = df.loc[agua, ["Grupo", "Referencia de Leitura", "Situacao Ligacao", "Consumo Faturado", "Economias_Totais"]].copy()

    def norm_sit(s):
        s = str(s).upper()
        if "ATIV" in s: return "Ativa"
        elif "CORT" in s: return "Cortada"
        return None
    sit = df["Situacao Ligacao"]
    df["Situacao_Norm"] = sit.map({v: norm_sit(v) for v in sit.dropna().unique()})   # uma vez por situação distinta
    df = df[df["Situacao_Norm"].notna()]

    def conta_por(referencia, sit):
        subset = df[
            (df["Referencia de Leitura"] == referencia) &
            (df["Situacao_Norm"] == sit) &
            (df["Consumo Faturado"] > 0)
        ]
        return subset.groupby("Grupo")["Economias_Totais"].sum()

    aa = conta_por(ctx.ref_atual, "Ativa")
    ac = conta_por(ctx.ref_atual, "Cortada")
    aa2 = conta_por(ctx.ref_anterior, "Ativa")
    ac2 = conta_por(ctx.ref_anterior, "Cortada")
    grupos = sorted(set(aa.index) | set(ac.index) | set(aa2.index) | set(ac2.index))
    linhas=[]
    for g in grupos:
        aa_g=int(aa.get(g,0))
        ac_g=int(ac.get(g,0))
        aa2_g=int(aa2.get(g,0))
        ac2_g=int(ac2.get(g,0))
        linhas.append({
            "Grupo": str(g),
            "Ativa_Atual": aa_g,
            "Cortada_Atual": ac_g,
            "Ativa_Ant": aa2_g,
            "Cortada_Ant": ac2_g,
            "Dif_Ativas": aa_g - aa2_g,
            "Dif_Cortadas": ac_g - ac2_g
        })
    df_ciclo_raw=pd.DataFrame(linhas)
    if df_ciclo_raw.empty:
        return "<div class='card'><h2>Ciclos (Ativa x Cortada)</h2><p>Sem dados</p></div>", df_ciclo_raw

    df_ciclo = df_ciclo_raw.copy()
    df_ciclo["Grupo"] = df_ciclo["Grupo"].apply(lambda g: html.escape(g, quote=True))

    total_ativa = df_ciclo["Ativa_Atual"].sum()
    total_cort = df_ciclo["Cortada_Atual"].sum()
    total_ant_ativa = df_ciclo["Ativa_Ant"].sum()
    total_ant_cort = df_ciclo["Cortada_Ant"].sum()
    total_dif_ativa = total_ativa - total_ant_ativa
    total_dif_cort = total_cort - total_ant_cort
    def fmt(v): return f"{v:,.0f}".replace(",",".")

    linhas_html = ""
    for _, r in df_ciclo.iterrows():
        cor_dif_ativa = "#C2560C" if r["Dif_Ativas"]<0 else "#05050D"
        cor_dif_cort = "#C2560C" if r["Dif_Cortadas"]<0 else "#05050D"
        linhas_html += f"""
        <tr data-grupo="{r['Grupo']}"
            data-ativa-atual="{r['Ativa_Atual']}" data-ativa-anterior="{r['Ativa_Ant']}"
            data-cortada-atual="{r['Cortada_Atual']}" data-cortada-anterior="{r['Cortada_Ant']}">
            <td style="text-align:center;">{r['Grupo']}</td>
            <td style="text-align:center;">{fmt(r['Ativa_Atual'])}</td>
            <td style="text-align:center;">{fmt(r['Ativa_Ant'])}</td>
            <td style="text-align:center;">{fmt(r['Cortada_Atual'])}</td>
            <td style="text-align:center;">{fmt(r['Cortada_Ant'])}</td>
            <td style="text-align:center; color:{cor_dif_ativa};">{fmt(r['Dif_Ativas'])}</td>
            <td style="text-align:center; color:{cor_dif_cort};">{fmt(r['Dif_Cortadas'])}</td>
        </tr>
        """
    cor_total_ativa = "#C2560C" if total_dif_ativa<0 else "#05050D"
    cor_total_cort = "#C2560C" if total_dif_cort<0 else "#05050D"
    linhas_html += f"""
    <tr class="linha-total">
        <td style="text-align:center;">Total</td>
        <td style="text-align:center;" data-field="ativa-atual">{fmt(total_ativa)}</td>
        <td style="text-align:center;" data-field="ativa-anterior">{fmt(total_ant_ativa)}</td>
        <td style="text-align:center;" data-field="cortada-atual">{fmt(total_cort)}</td>
        <td style="text-align:center;" data-field="cortada-anterior">{fmt(total_ant_cort)}</td>
        <td style="text-align:center; color:{cor_total_ativa};" data-field="delta-ativa">{fmt(total_dif_ativa)}</td>
        <td style="text-align:center; color:{cor_total_cort};" data-field="delta-cortada">{fmt(total_dif_cort)}</td>
    </tr>
    """
    cab = f"""
    <tr class="header-grupo">
        <th rowspan="2">Ciclos</th>
        <th colspan="2">A-Ativa</th>
        <th colspan="2">C-Cortada</th>
        <th colspan="2">Diferença</th>
    </tr>
    <tr class="header-sub">
        <th>{ctx.mes_atual}</th><th>{ctx.mes_anterior}</th><th>{ctx.mes_atual}</th><th>{ctx.mes_anterior}</th>
        <th>Dif. Ativa<br>({ctx.mes_atual} - {ctx.mes_anterior})</th>
        <th>Dif. Cortada<br>({ctx.mes_atual} - {ctx.mes_anterior})</th>
    </tr>
    """
    html_tabela = f"""
    <div class="card">
    <h2>Economias faturadas por ciclo — ativas x cortadas</h2>
    <table class="tabela-ativa-cortada">{cab}{linhas_html}</table>
    </div>
    """
    return html_tabela, df_ciclo_raw


def botao_download_xlsx(rotulo, nome_arquivo, conteudo):
    """Botão que baixa um .xlsx embutido no próprio relatório (funciona dentro do iframe e offline)."""
    if not conteudo:
        return ""
    b64 = base64.b64encode(conteudo).decode("ascii")
    # só a seta; o que o botão baixa aparece ao passar o mouse (title) e para leitores de tela (aria-label)
    r = html.escape(rotulo, quote=True)
    return (f'<button type="button" class="btn-just btn-baixar" data-arquivo="{html.escape(nome_arquivo)}" '
            f'title="{r}" aria-label="{r}" data-b64="{b64}">&#11015;</button>')


def media_dias(serie):
    from .painel_html import media_dias as m
    return m(serie)


def filtra_sup(ctx, df, sup):
    """Linhas de df da superintendência `sup` (TODAS: df inteiro). Usa a coluna de SUP se houver; senão, o grupo
    (coluna "Grupo…" → SUP do grupo pelo cronograma). Linhas sem grupo da SUP (ex.: Total) ficam de fora."""
    from .dre import TODAS
    from .leitura import chave_grupo
    if df is None or not len(df) or sup == TODAS:
        return df
    for col in ("__sup", "Superintendência"):
        if col in df.columns:
            return df[df[col] == sup]
    col = next((c for c in df.columns if str(c).startswith("Grupo")), None)
    if col is None:
        return df
    mapa = getattr(ctx, "grupo_sup", None) or {}
    da_sup = {g: mapa.get(chave_grupo(g)) == sup for g in df[col].unique()}     # uma vez por grupo, não por linha
    return df[df[col].map(da_sup).astype(bool)]


def botoes_por_sup(ctx, rotulo, nome_arquivo, abas_da_sup):
    """Um botão de download por superintendência; o filtro Superintendência do relatório mostra só o da SUP escolhida.
    abas_da_sup(sup) -> {nome_da_aba: DataFrame}. Abas vazias saem; SUP sem nenhuma aba não ganha botão.
    rotulo: texto ou função(abas) -> texto."""
    from .dre import TODAS, lista_sups, prepara
    prepara(ctx)
    base, ext = nome_arquivo.rsplit(".", 1)
    partes = []
    for sup in lista_sups(ctx):
        abas = {k: v for k, v in (abas_da_sup(sup) or {}).items() if v is not None and len(v)}
        if not abas:
            continue
        r = rotulo(abas) if callable(rotulo) else rotulo
        r = r if sup == TODAS else f"{r} — {sup}"
        n = nome_arquivo if sup == TODAS else f"{base}_{''.join(c for c in sup if c.isalnum())}.{ext}"
        oculto = "" if sup == TODAS else ' style="display:none"'
        partes.append(f'<span class="sup-dl" data-sup="{html.escape(sup, quote=True)}"{oculto}>'
                      f'{botao_download_xlsx(r, n, xlsx_bytes(abas))}</span>')
    return "".join(partes)


def motor_excel():
    """Gravador de .xlsx disponível: xlsxwriter (mais rápido) ou openpyxl; None se nenhum (os botões de Excel somem)."""
    import importlib.util
    for motor in ("xlsxwriter", "openpyxl"):
        if importlib.util.find_spec(motor) is not None:
            return motor
    return None


def xlsx_bytes(abas):
    """abas: {nome_da_aba: DataFrame} -> bytes de um .xlsx (b"" se não houver gravador de Excel)."""
    motor = motor_excel()
    if motor is None:
        return b""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine=motor) as w:
        for nome, df in abas.items():
            df.to_excel(w, sheet_name=nome[:31], index=False)
    return buf.getvalue()


def lista_sem_faturamento(ctx, merge):
    """Ligações que faturaram no mês anterior e não faturaram no atual (coluna 'Sem Faturamento Atual')."""
    sem = merge[merge["Grupo_Atual"] == "Sem Faturamento Atual"][["N. Ligação", "Grupo_Anterior", "Eco_Anterior"]].copy()
    base = ctx.base_final
    ant = base[(base["Referencia de Leitura"] == ctx.ref_anterior)]
    cols = {c: c for c in ("Nome Cliente", "Categoria") if c in ant.columns}
    if cols:
        info = ant[["N. Ligação"] + list(cols)].drop_duplicates("N. Ligação")
        sem = sem.merge(info, on="N. Ligação", how="left")
    sem = sem.rename(columns={"Grupo_Anterior": f"Grupo {ctx.mes_anterior}", "Eco_Anterior": f"Economias {ctx.mes_anterior}"})
    ordem = ["N. Ligação"] + list(cols) + [f"Grupo {ctx.mes_anterior}", f"Economias {ctx.mes_anterior}"]
    return sem[ordem].sort_values([f"Grupo {ctx.mes_anterior}", "N. Ligação"]).reset_index(drop=True)


def gera_matriz_migracao_grupos(ctx):
    print("📊 Montando matriz de migração de grupos...")

    base = ctx.base_final
    base = base[base["Referencia de Leitura"].isin([ctx.ref_atual, ctx.ref_anterior])]      # só os dois meses comparados
    df = base[["N. Ligação", "Grupo", "Referencia de Leitura", "Consumo Faturado", "Economias_Totais", "Rubrica"]
              + (["__serv"] if "__serv" in base.columns else [])].dropna(subset=["Grupo"])

    # Filtra apenas Rubrica AGUA — evita duplicar economia (AGUA + ESGOTO)
    df = df[(df["__serv"] == "A") if "__serv" in df.columns else df["Rubrica"].str.contains("AGUA", case=False, na=False)].copy()

    df["Consumo Faturado"] = pd.to_numeric(df["Consumo Faturado"], errors="coerce").fillna(0)
    df = df[df["Consumo Faturado"] > 0]
    df = df.drop_duplicates(subset=["N. Ligação", "Referencia de Leitura"])

    ant = df[df["Referencia de Leitura"] == ctx.ref_anterior][
        ["N. Ligação", "Grupo", "Economias_Totais"]
    ].rename(columns={"Grupo": "Grupo_Anterior", "Economias_Totais": "Eco_Anterior"})

    at = df[df["Referencia de Leitura"] == ctx.ref_atual][
        ["N. Ligação", "Grupo", "Economias_Totais"]
    ].rename(columns={"Grupo": "Grupo_Atual", "Economias_Totais": "Eco_Atual"})

    merge = ant.merge(at, on="N. Ligação", how="outer")
    merge["Grupo_Anterior"] = merge["Grupo_Anterior"].fillna("Sem Faturamento Anterior")
    merge["Grupo_Atual"] = merge["Grupo_Atual"].fillna("Sem Faturamento Atual")

    merge["Valor_Economia"] = merge["Eco_Atual"].fillna(0)
    sem_atual = merge["Grupo_Atual"] == "Sem Faturamento Atual"
    merge.loc[sem_atual, "Valor_Economia"] = merge.loc[sem_atual, "Eco_Anterior"].fillna(0)

    crosstab = pd.crosstab(
        merge["Grupo_Anterior"], merge["Grupo_Atual"],
        values=merge["Valor_Economia"], aggfunc="sum"
    ).fillna(0)

    ctx.resultados["matriz"] = crosstab.reset_index()
    ctx.resultados["sem_faturamento"] = lista_sem_faturamento(ctx, merge)
    if crosstab.empty:
        return "<div class='card'><h2>Matriz de Migração de Grupos</h2><p>Sem dados</p></div>"

    grupos_origem = sorted([g for g in crosstab.index if g not in ("Sem Faturamento Anterior",)]) + \
                    (["Sem Faturamento Anterior"] if "Sem Faturamento Anterior" in crosstab.index else [])
    grupos_destino = sorted([g for g in crosstab.columns if g not in ("Sem Faturamento Atual",)]) + \
                     (["Sem Faturamento Atual"] if "Sem Faturamento Atual" in crosstab.columns else [])

    def esc(v): return html.escape(str(v), quote=True)

    max_desvio = 0
    for go in grupos_origem:
        for gd in grupos_destino:
            if go == gd:
                continue
            valor = int(crosstab.loc[go, gd]) if (go in crosstab.index and gd in crosstab.columns) else 0
            if valor > max_desvio:
                max_desvio = valor
    max_desvio = max_desvio if max_desvio > 0 else 1

    def cor_desvio(valor, go, gd):
        if valor <= 0:
            return "transparent"
        if go == gd:
            return "#F2F2F2"
        if gd == "Sem Faturamento Atual":
            return "#FCE4D2"
        if go == "Sem Faturamento Anterior":
            return "#E1E7F0"
        intensidade = min(1.0, valor / max_desvio)
        r1, g1, b1 = 185, 198, 217   # #B9C6D9
        r2, g2, b2 = 57, 77, 115     # #394D73
        r = int(r1 + (r2 - r1) * intensidade)
        g = int(g1 + (g2 - g1) * intensidade)
        b = int(b1 + (b2 - b1) * intensidade)
        return f"rgb({r},{g},{b})"

    ths_destino = "".join(f'<th data-destino="{esc(g)}">{html.escape(str(g))}</th>' for g in grupos_destino)
    cabecalho = f"""
    <tr>
        <th>Grupo Anterior \\ Grupo Atual</th>
        {ths_destino}
        <th data-field="total-linha-header">Total</th>
    </tr>
    """

    linhas_html = ""
    for go in grupos_origem:
        tds = ""
        total_linha = 0
        for gd in grupos_destino:
            valor = int(crosstab.loc[go, gd]) if (go in crosstab.index and gd in crosstab.columns) else 0
            total_linha += valor
            cor = cor_desvio(valor, go, gd)
            migrou = valor > 0 and go != gd and gd != "Sem Faturamento Atual" and go != "Sem Faturamento Anterior"
            if migrou:
                fonte_cor = "#FFFFFF" if valor / max_desvio > 0.5 else "#05050D"
            elif valor > 0 and gd == "Sem Faturamento Atual":
                fonte_cor = "#C2560C"
            else:
                fonte_cor = "#05050D"
            peso = "font-weight:700;" if (valor > 0 and go != gd) else ""
            tds += (
                f'<td data-destino="{esc(gd)}" data-valor="{valor}" '
                f'style="background:{cor}; color:{fonte_cor}; {peso}">{fmt_int_br(valor)}</td>'
            )
        linhas_html += f"""
        <tr data-grupo="{esc(go)}">
            <td style="text-align:left; font-weight:600;">{html.escape(str(go))}</td>
            {tds}
            <td data-field="total-linha" style="font-weight:700; background:#E1E7F0;">{fmt_int_br(total_linha)}</td>
        </tr>
        """

    tds_total = ""
    total_geral = 0
    for gd in grupos_destino:
        total_col = int(crosstab[gd].sum()) if gd in crosstab.columns else 0
        total_geral += total_col
        tds_total += f'<td data-destino="{esc(gd)}" data-field="total-coluna">{fmt_int_br(total_col)}</td>'
    linhas_html += f"""
    <tr class="linha-total">
        <td style="text-align:left;">Total</td>
        {tds_total}
        <td data-field="total-geral" style="background:#E1E7F0;">{fmt_int_br(total_geral)}</td>
    </tr>
    """

    sem_fat = lista_sem_faturamento(ctx, merge)
    botao_sem_fat = botoes_por_sup(              # um botão por SUP (pelo grupo do mês anterior), com a contagem de cada uma
        ctx, lambda abas: f"Baixar matrículas sem faturamento ({len(abas['Sem faturamento'])})",
        f"Matriculas_Sem_Faturamento_{ctx.mes_atual.replace('/', '-')}.xlsx",
        lambda sup: {"Sem faturamento": filtra_sup(ctx, sem_fat, sup)})
    if len(sem_fat):                              # com grupos desmarcados, o botão baixa (CSV) só os grupos marcados
        from .situacao_lancamento import _csv_gz_b64
        col = html.escape(f"Grupo {ctx.mes_anterior}", quote=True)
        botao_sem_fat = (f'<span data-csv-filtrado="semfat" data-nome="Matriculas_Sem_Faturamento_{ctx.mes_atual.replace("/", "-")}">'
                         f'{botao_sem_fat}</span><script type="application/octet-stream" id="semfat-dados" data-col-grupo="{col}">'
                         f'{_csv_gz_b64(sem_fat)}</script>')

    return f"""
    <div class="card">
    <h2 style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">Matriz de migração de grupos — {ctx.mes_anterior} → {ctx.mes_atual} {botao_sem_fat}</h2>
    <p style="font-size:0.8em; color:#49668C; margin-top:-6px;">
        Cada linha mostra em quais grupos as economias que faturaram em <b>{ctx.mes_anterior}</b> estão faturando em <b>{ctx.mes_atual}</b>.<br>
        <span style="background:#F2F2F2; border:1px solid #DCE1E9; padding:2px 6px; border-radius:4px;">Cinza</span> = permaneceu no mesmo grupo &nbsp;|&nbsp;
        <span style="background:#394D73; color:#FFFFFF; padding:2px 6px; border-radius:4px;">Azul</span> = migrou para outro grupo (mais escuro = mais ligações) &nbsp;|&nbsp;
        <span style="background:#FCE4D2; color:#C2560C; padding:2px 6px; border-radius:4px;">Laranja</span> = deixou de faturar &nbsp;|&nbsp;
        <span style="background:#E1E7F0; padding:2px 6px; border-radius:4px;">Azul claro</span> = novo faturamento
    </p>
    <table class="tabela-matriz-grupo">
        <thead>{cabecalho}</thead>
        <tbody>{linhas_html}</tbody>
    </table>
    </div>
    """


def gera_alerta_categorias_sem_minimo(ctx):
    if not ctx.categorias_sem_minimo:
        return ""
    itens = "".join(
        f"<li><strong>{html.escape(str(c))}</strong> — {int(q):,} economias".replace(",", ".") + "</li>"
        for c, q in sorted(ctx.categorias_sem_minimo.items())
    )
    return f"""
<div id="alerta-minimo" role="alertdialog" aria-modal="true" aria-labelledby="alerta-minimo-titulo"
     style="position:fixed;inset:0;background:rgba(5,5,13,.55);display:flex;align-items:center;justify-content:center;z-index:9999;padding:16px;">
  <div style="background:#fff;max-width:460px;width:100%;border-radius:10px;padding:22px 24px;border-top:4px solid #C2560C;box-shadow:0 12px 40px rgba(5,5,13,.35);font-family:'IBM Plex Sans',sans-serif;color:#1A2740;">
    <h3 id="alerta-minimo-titulo" style="margin:0 0 8px;font-size:1.05rem;color:#05050D;">Categorias sem consumo mínimo cadastrado</h3>
    <p style="margin:0 0 10px;font-size:.88rem;line-height:1.45;">Estas categorias <strong>ficaram fora</strong> da tabela “Economias Acima/Abaixo do Consumo Mínimo”. Cadastre o mínimo delas no script para incluí-las:</p>
    <ul style="margin:0 0 16px;padding-left:18px;font-size:.88rem;line-height:1.6;">{itens}</ul>
    <button onclick="document.getElementById('alerta-minimo').remove()"
            style="background:#1A2740;color:#fff;border:0;border-radius:6px;padding:8px 18px;font-size:.88rem;cursor:pointer;">Entendi</button>
  </div>
</div>"""


def gera_tabela_acima_abaixo_minimo(ctx):
    print("📊 Montando tabela Acima x Abaixo do Consumo Mínimo...")
    df = ctx.base_final

    if "Categoria" not in df.columns:
        html_vazio = "<div class='card'><h2>Economias Acima/Abaixo do Consumo Mínimo</h2><p>Coluna 'Categoria' não encontrada</p></div>"
        return html_vazio, pd.DataFrame(columns=["Grupo","Acima_Atual","Acima_Ant","Abaixo_Atual","Abaixo_Ant"])

    # Somente rubrica AGUA (evita duplicar economia com ESGOTO) e só os dois meses comparados
    df = df[df["Referencia de Leitura"].isin([ctx.ref_atual, ctx.ref_anterior])]
    df = df[(df["__serv"] == "A") if "__serv" in df.columns else df["Rubrica"].str.contains("AGUA", case=False, na=False)].copy()

    df["Consumo Faturado"] = pd.to_numeric(df.get("Consumo Faturado", 0), errors="coerce").fillna(0)
    for c in MINIMO_POR_TIPO_ECONOMIA:
        df[c] = pd.to_numeric(df.get(c, 0), errors="coerce").fillna(0)
    df["Economias_Totais"] = df[list(MINIMO_POR_TIPO_ECONOMIA)].sum(axis=1)

    # Fora: sem consumo faturado ou sem economia
    df = df[(df["Consumo Faturado"] > 0) & (df["Economias_Totais"] > 0)].copy()

    df["Minimo_Matricula"] = minimo_matricula_vetorizado(df)

    sem_minimo = df[df["Minimo_Matricula"].isna()]
    ctx.categorias_sem_minimo.clear()
    for cat, qtd in sem_minimo.groupby(sem_minimo["Categoria"].astype(str))["Economias_Totais"].sum().items():
        ctx.categorias_sem_minimo[cat] = qtd
    if ctx.categorias_sem_minimo:
        print("⚠️ Categorias sem consumo mínimo cadastrado (ficam fora da tabela):", ", ".join(sorted(ctx.categorias_sem_minimo)))
    ctx.alerta_minimo_html = gera_alerta_categorias_sem_minimo(ctx)

    df = df[df["Minimo_Matricula"].notna()].copy()
    df["Classificacao_Minimo"] = (df["Consumo Faturado"] > df["Minimo_Matricula"]).map({True: "Acima", False: "Abaixo"})

    def conta_por(referencia, classe):
        subset = df[
            (df["Referencia de Leitura"] == referencia) &
            (df["Classificacao_Minimo"] == classe)
        ]
        return subset.groupby("Grupo")["Economias_Totais"].sum()

    acima_at  = conta_por(ctx.ref_atual, "Acima")
    abaixo_at = conta_por(ctx.ref_atual, "Abaixo")
    acima_ant  = conta_por(ctx.ref_anterior, "Acima")
    abaixo_ant = conta_por(ctx.ref_anterior, "Abaixo")

    grupos = sorted(set(acima_at.index) | set(abaixo_at.index) | set(acima_ant.index) | set(abaixo_ant.index))

    linhas = []
    for g in grupos:
        aa = int(acima_at.get(g, 0))
        ab = int(abaixo_at.get(g, 0))
        aa2 = int(acima_ant.get(g, 0))
        ab2 = int(abaixo_ant.get(g, 0))
        linhas.append({
            "Grupo": str(g),
            "Acima_Atual": aa,
            "Abaixo_Atual": ab,
            "Acima_Ant": aa2,
            "Abaixo_Ant": ab2,
            "Dif_Acima": aa - aa2,
            "Dif_Abaixo": ab - ab2,
        })

    df_tab_raw = pd.DataFrame(linhas)

    if df_tab_raw.empty:
        html_vazio = "<div class='card'><h2>Economias Acima/Abaixo do Consumo Mínimo</h2><p>Sem dados</p></div>"
        return html_vazio, df_tab_raw

    df_tab = df_tab_raw.copy()
    df_tab["Grupo"] = df_tab["Grupo"].apply(lambda g: html.escape(g, quote=True))

    total_acima_at = df_tab["Acima_Atual"].sum()
    total_abaixo_at = df_tab["Abaixo_Atual"].sum()
    total_acima_ant = df_tab["Acima_Ant"].sum()
    total_abaixo_ant = df_tab["Abaixo_Ant"].sum()
    total_dif_acima = total_acima_at - total_acima_ant
    total_dif_abaixo = total_abaixo_at - total_abaixo_ant

    def fmt(v): return f"{v:,.0f}".replace(",", ".")

    linhas_html = ""
    for _, r in df_tab.iterrows():
        cor_dif_acima = "#C2560C" if r["Dif_Acima"] < 0 else "#1A2740"
        cor_dif_abaixo = "#C2560C" if r["Dif_Abaixo"] > 0 else "#1A2740"
        linhas_html += f"""
        <tr data-grupo="{r['Grupo']}"
            data-acima-atual="{r['Acima_Atual']}" data-acima-anterior="{r['Acima_Ant']}"
            data-abaixo-atual="{r['Abaixo_Atual']}" data-abaixo-anterior="{r['Abaixo_Ant']}">
            <td style="text-align:center;">{r['Grupo']}</td>
            <td style="text-align:center;">{fmt(r['Acima_Atual'])}</td>
            <td style="text-align:center;">{fmt(r['Acima_Ant'])}</td>
            <td style="text-align:center;">{fmt(r['Abaixo_Atual'])}</td>
            <td style="text-align:center;">{fmt(r['Abaixo_Ant'])}</td>
            <td style="text-align:center; color:{cor_dif_acima};">{fmt(r['Dif_Acima'])}</td>
            <td style="text-align:center; color:{cor_dif_abaixo};">{fmt(r['Dif_Abaixo'])}</td>
        </tr>
        """

    cor_total_acima = "#C2560C" if total_dif_acima < 0 else "#1A2740"
    cor_total_abaixo = "#C2560C" if total_dif_abaixo > 0 else "#1A2740"
    linhas_html += f"""
    <tr class="linha-total">
        <td style="text-align:center;">Total</td>
        <td style="text-align:center;" data-field="acima-atual">{fmt(total_acima_at)}</td>
        <td style="text-align:center;" data-field="acima-anterior">{fmt(total_acima_ant)}</td>
        <td style="text-align:center;" data-field="abaixo-atual">{fmt(total_abaixo_at)}</td>
        <td style="text-align:center;" data-field="abaixo-anterior">{fmt(total_abaixo_ant)}</td>
        <td style="text-align:center; color:{cor_total_acima};" data-field="delta-acima">{fmt(total_dif_acima)}</td>
        <td style="text-align:center; color:{cor_total_abaixo};" data-field="delta-abaixo">{fmt(total_dif_abaixo)}</td>
    </tr>
    """

    cab = f"""
    <tr class="header-grupo">
        <th rowspan="2">Grupo</th>
        <th colspan="2">Acima do Mínimo</th>
        <th colspan="2">Abaixo do Mínimo</th>
        <th colspan="2">Diferença</th>
    </tr>
    <tr class="header-sub">
        <th>{ctx.mes_atual}</th><th>{ctx.mes_anterior}</th>
        <th>{ctx.mes_atual}</th><th>{ctx.mes_anterior}</th>
        <th>Dif. Acima<br>({ctx.mes_atual} - {ctx.mes_anterior})</th>
        <th>Dif. Abaixo<br>({ctx.mes_atual} - {ctx.mes_anterior})</th>
    </tr>
    """

    html_tabela = f"""
    <div class="card">
    <h2>Economias acima x abaixo do consumo mínimo — {ctx.mes_atual} vs {ctx.mes_anterior}</h2>
    <p style="font-size:0.8em; color:#49668C; margin-top:-6px;">
        Mínimo da matrícula = consumo mínimo da categoria × quantidade de economias. Acima: consumo faturado maior que o mínimo; abaixo: faturado igual ou menor que o mínimo.
    </p>
    <table class="tabela-min-consumo">{cab}{linhas_html}</table>
    </div>
    """
    return html_tabela, df_tab_raw


def gera_tabela_dados_resumo_html(df_resumo):
    linhas_html = ""
    for _, r in df_resumo.iterrows():
        grupo_esc = html.escape(str(r["Grupo"]), quote=True)
        linhas_html += f"""
        <tr data-grupo="{grupo_esc}"
            data-fat-atual="{r['Fat_Atual']}" data-fat-anterior="{r['Fat_Anterior']}"
            data-fatagua-atual="{r['FatAgua_Atual']}" data-fatagua-anterior="{r['FatAgua_Anterior']}"
            data-fatesgoto-atual="{r['FatEsgoto_Atual']}" data-fatesgoto-anterior="{r['FatEsgoto_Anterior']}"
            data-eco-atual="{r['Eco_Atual']}" data-eco-anterior="{r['Eco_Anterior']}"
            data-volfat-atual="{r['VolFat_Atual']}" data-volfat-anterior="{r['VolFat_Anterior']}"
            data-acima-atual="{r['Acima_Atual']}" data-acima-anterior="{r['Acima_Ant']}"
            data-dias-atual="{r['Dias_Leitura_Atual']}" data-dias-anterior="{r['Dias_Leitura_Anterior']}">
            <td style="text-align:center;">{html.escape(str(r['Grupo']))}</td>
            <td style="text-align:center;">{fmt_moeda_br(r['Fat_Atual'])}</td>
            <td style="text-align:center;">{fmt_moeda_br(r['Fat_Anterior'])}</td>
            <td style="text-align:center;">{fmt_int_br(r['Eco_Atual'])}</td>
            <td style="text-align:center;">{fmt_int_br(r['VolFat_Atual'])}</td>
        </tr>
        """
    cab = """
    <tr>
        <th>Grupo</th><th>Faturamento Atual</th><th>Faturamento Anterior</th>
        <th>Economias</th><th>Volume Faturado</th>
    </tr>
    """
    return f"""
    <div class="card">
    <h2>Resumo consolidado por grupo</h2>
    <table id="tabela-dados-resumo">
        <thead>{cab}</thead>
        <tbody>{linhas_html}</tbody>
    </table>
    </div>
    """


def gera_tabela_top100_html(df, titulo, slug, botao_extra="", aumento=False, chave=""):
    """chave: nome da lista em #top100-dados ("queda-agua"...) — o filtro de grupos refaz a tabela com ela no navegador."""
    tipo = "aumento" if aumento else "queda"
    prefixo = "Aumento" if aumento else "Queda"
    cabecalho = f"Top 100 clientes com maior {tipo} de consumo — {titulo}"
    if df.empty:
        return f"<div class='card'><h2>{cabecalho} {botao_extra}</h2><p>Sem dados</p></div>"

    colunas = df.columns.tolist()

    # Colunas que exigem formatação especial
    colunas_moeda = [c for c in colunas if c.startswith("Valor R$") or c == f"{prefixo}_Valor_R$"]
    colunas_pct = [c for c in colunas if c == f"{prefixo}_%"]
    colunas_num = [c for c in colunas if c.startswith("Consumo ") or c == f"{prefixo}_Consumo"]
    cor = "#176b9c" if aumento else "#C2560C"

    def formata_valor(col, v):
        if col in colunas_moeda:
            return "R$ " + fmt_num(v, 2)
        if col in colunas_pct:
            return "—" if pd.isna(v) else f"{fmt_num(v, 1)}%"
        if col in colunas_num:
            return fmt_num(v, 2)
        return html.escape(str(v))

    ths = "".join(f"<th>{html.escape(str(c).replace('_', ' '))}</th>" for c in colunas)

    linhas_html = ""
    for _, r in df.iterrows():
        tds = ""
        for c in colunas:
            v = r[c]
            texto = formata_valor(c, v)
            alinhamento = "left" if c in ("Nome_Cliente", "Grupo", "Categoria") or str(c).startswith("Situação Lançamento") else "center"
            destaque = ""
            if c == f"{prefixo}_%" and isinstance(v, (int, float)) and v >= DESTAQUE_QUEDA_PCT_TOP100:
                destaque = f"color:{cor}; font-weight:700;"
            tds += f"<td style='text-align:{alinhamento}; {destaque}'>{texto}</td>"
        linhas_html += f"<tr>{tds}</tr>"

    explicacao = ("Ranking dos clientes com maior crescimento de consumo faturado entre os dois meses comparados (só ligações que faturaram nos dois meses; "
                  "\"—\" no Aumento % = sem consumo no mês anterior)."
                  if aumento else "Ranking dos clientes com maior redução de consumo faturado entre os dois meses comparados.")
    cor_nome = "Azul" if aumento else "Laranja"
    return f"""
    <div class="card">
    <h2 style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">{cabecalho} {botao_extra}</h2>
    <p style="font-size:0.8em; color:#49668C; margin-top:-6px;">
        {explicacao}
        <span style="color:{cor}; font-weight:700;">{cor_nome}</span> = {tipo} igual ou superior a {DESTAQUE_QUEDA_PCT_TOP100}%.
    </p>
    <table class="tabela-top100-{slug}"{f' data-top="{chave}"' if chave else ""}>
        <thead><tr>{ths}</tr></thead>
        <tbody>{linhas_html}</tbody>
    </table>
    </div>
    """
