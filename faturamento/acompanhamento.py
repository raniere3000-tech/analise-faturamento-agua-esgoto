# -*- coding: utf-8 -*-
"""Export "Acompanhamento Mensal": as tabelas da planilha de acompanhamento semanal, prontas para copiar e colar.

Um arquivo Excel com uma aba por tabela (mesma ordem de colunas da planilha), para a superintendência escolhida no
mês vigente:
  1 Faturamento (por ciclo: data de leitura, orçado SUP, liberado e em análise — água e esgoto)
  2 Cancelamento (por ciclo)
  3/5 Economias faturadas água/esgoto (mês atual × anterior, com as economias da categoria Social)
  4/6 Volume faturado água/esgoto
  7/8 Indiretas por dia útil — valor (R$) e quantidade de eventos, orçado SUP:
      dias que já passaram: Orçado = Realizado; o realizado de cada semana (entre um export e o seguinte) é dividido
      igualmente pelos dias úteis da semana — o serviço avulso não traz a data do serviço, então cada export guarda o
      realizado acumulado ("foto") no ajustes_relatorio.json e o próximo usa a diferença;
      dias que faltam: (orçado do mês − realizado acumulado) ÷ dias que faltam. Corte não conta sextas nem vésperas de
      feriado.
Não aparece no painel nem no PDF: é gerado sob demanda pelo botão "Acompanhamento" do site.
"""
import calendar
import datetime as dt
import io

import pandas as pd

from .config import SITUACAO_CONTA_EM_ANALISE
from .formatacao import nome_mes, nome_mes_curto, normaliza_texto

CLASSES = [("CORTE", "ri_CORTE"), ("RELIGAÇÃO", "ri_RELIGAÇÃO"), ("LNA", "ri_LNA"), ("SANÇÃO", "ri_SANÇÃO"), ("LNE", "iE")]
TODAS = "TODAS"


# ---------------------------------------------------------------- dias úteis
def calendario(ref):
    """[(data, é dia de corte)] dos dias úteis do mês `ref` (MM/AAAA)."""
    from .previsao import _eh_util, feriados
    m, a = int(ref[:2]), int(ref[3:])
    fer = feriados(a) | feriados(a + 1)
    dias = [dt.date(a, m, n) for n in range(1, calendar.monthrange(a, m)[1] + 1)]
    return [(d, d.weekday() != 4 and (d + dt.timedelta(days=1)) not in fer) for d in dias if _eh_util(d, fer)]


def distribui(dias, corte, fotos, acumulado, orcado_mes, so_corte):
    """Realizado e orçado por dia útil de uma classe.

    dias: [(data, é dia de corte)]; corte: data até onde há dados (D-1); fotos: [(data, acumulado)] dos exports
    anteriores; acumulado: realizado do mês até `corte`. Devolve {data: (orçado, realizado ou None)}."""
    eleg = [d for d, c in dias if c or not so_corte]
    real = {d: 0.0 for d, _ in dias}
    pontos = sorted((f for f in fotos if f[0] < corte), key=lambda f: f[0]) + [(corte, acumulado)]
    ant_data, ant_acc = None, 0.0
    for ate, acc in pontos:
        periodo = [d for d in eleg if (ant_data is None or d > ant_data) and d <= ate]
        if periodo:                                   # realizado do período ÷ dias úteis do período
            for d in periodo:
                real[d] = (acc - ant_acc) / len(periodo)
            ant_acc = acc
        ant_data = ate
    sobra = acumulado - ant_acc                       # período sem dia útil elegível: vai para o último dia que passou
    passados = [d for d in eleg if d <= corte]
    if abs(sobra) > 1e-9 and passados:
        real[passados[-1]] += sobra
    futuros = [d for d in eleg if d > corte]
    por_dia = (orcado_mes - acumulado) / len(futuros) if futuros else 0.0
    out = {}
    for d, _ in dias:
        if d <= corte:
            v = real[d] if d in eleg else 0.0
            out[d] = (v, v)
        else:
            out[d] = (por_dia if d in futuros else 0.0, None)
    return out


# ---------------------------------------------------------------- dados
def rf_mais_recente(fontes):
    """A planilha RF mais nova pelo nome RFnnTaa (ex.: RF02T26 > RF01T26 > RF3T25); sem o padrão, a primeira."""
    import re
    def chave(f):
        m = re.search(r"RF\s*0*(\d+)\s*T\s*(\d{2})", str(f).upper())
        return (int(m.group(2)), int(m.group(1))) if m else (-1, -1)
    return max(fontes, key=chave) if fontes else None


def _num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _base_sup(ctx, sup):
    from .dre import prepara
    prepara(ctx)
    b = ctx.base_completa if getattr(ctx, "base_completa", None) is not None else ctx.base_final
    if sup != TODAS and "__sup" in b.columns:
        b = b[b["__sup"] == sup]
    return b


def _grupos_da_sup(ctx, sup):
    from .dre import sup_por_grupo
    from .leitura import chave_grupo
    mapa = sup_por_grupo(ctx)
    grupos = {k for k, s in mapa.items() if sup == TODAS or s == sup}
    crono = getattr(ctx, "cronograma_leitura", None)
    datas = {}
    if crono is not None and len(crono) and "Referencia Cronograma" in crono.columns:
        c = crono[crono["Referencia Cronograma"] == ctx.ref_atual]
        from .leitura import converte_datas
        dd = converte_datas(c["Data da Leitura"])
        for g, d in zip(c["Grupo"], dd):
            if pd.notna(g) and pd.notna(d):
                k = chave_grupo(g)
                if sup == TODAS or mapa.get(k) == sup:
                    datas[k] = min(datas.get(k, d.date()), d.date())
                    grupos.add(k)
    chave = lambda g: (int(g) if str(g).isdigit() else 10 ** 9, str(g))
    return sorted(grupos, key=chave), datas


def _por_grupo(df, valores, grupo="Grupo"):
    from .leitura import chave_grupo
    if df is None or not len(df):
        return {}
    g = df[grupo].map({x: chave_grupo(x) for x in df[grupo].dropna().unique()})
    return valores.groupby(g.values).sum().to_dict()


def dados_acompanhamento(ctx, sup):
    """Tudo o que o arquivo precisa, para a superintendência `sup` (ou TODAS) no mês vigente."""
    from .dre import _indiretas_mes, fontes_rf, fontes_sup, orcado
    from .orcado_ciclo import pesos_por_ciclo
    from .previsao import data_corte, eventos_indiretas
    ra, rn = ctx.ref_atual, ctx.ref_anterior
    grupos, datas = _grupos_da_sup(ctx, sup)
    b = _base_sup(ctx, sup)
    serv = b["__serv"]
    ref = b["Referencia de Leitura"]
    cons, val = _num(b["Consumo Faturado"]), _num(b["Valor (R$)"])
    eco = _num(b["Economias_Totais"]) if "Economias_Totais" in b.columns else cons * 0
    pos = cons > 0
    social = (b["Categoria"].astype(str).map(normaliza_texto).str.contains("SOCIAL") if "Categoria" in b.columns
              else pd.Series(False, index=b.index))
    sit = b["Situacao Conta"].astype(str).map(normaliza_texto) if "Situacao Conta" in b.columns else pd.Series("", index=b.index)
    analise = sit == SITUACAO_CONTA_EM_ANALISE

    def agrega(mascara, serie):
        return _por_grupo(b[mascara], serie[mascara])

    # orçado das indiretas = orçado SUP; orçado das diretas por ciclo (aba Faturamento) = RF mais recente (ex.: RF02T26)
    fontes = fontes_sup(ctx)
    fonte = fontes[0] if fontes else None
    orc = orcado(ctx, fonte, sup, ra) if fonte else {}
    fonte_rf = rf_mais_recente(fontes_rf(ctx))
    orc_rf = orcado(ctx, fonte_rf, sup, ra) if fonte_rf else {}
    orc_ciclo = {}
    for s, k, rub in (("A", "dA", "AGUA"), ("E", "dE", "ESGOTO")):
        from .leitura import chave_grupo
        pesos = {}
        for g0, v in pesos_por_ciclo(ctx, rub).get("valor", {}).items():     # "02" no resumo = "2" na chave do grupo
            pesos[chave_grupo(g0)] = pesos.get(chave_grupo(g0), 0.0) + v
        p = {g: pesos.get(g, 0.0) for g in grupos}
        tot = sum(p.values())
        orc_ciclo[s] = {g: (p[g] / tot) * (orc_rf.get(k) or 0.0) if tot else 0.0 for g in grupos}

    fat = {}
    for s in ("A", "E"):
        m = (serv == s) & (ref == ra)
        fat[s] = {"lib": agrega(m & ~analise, val), "ana": agrega(m & analise, val)}
    eco_t, soc_t, vol_t = {}, {}, {}
    for s in ("A", "E"):
        for r in (ra, rn):
            m = (serv == s) & (ref == r) & pos
            eco_t[(s, r)] = agrega(m, eco)
            soc_t[(s, r)] = agrega(m & social, eco)
            vol_t[(s, r)] = agrega(m, cons)
    from .dre import _filtra
    canc = _filtra(ctx.cancelamento, sup)
    canc_g = {}
    if canc is not None and len(canc) and "Grupo" in canc.columns:
        canc = canc[canc["Referencia de Leitura"] == ra]
        canc_g = _por_grupo(canc, _num(canc["Valor Parcela"]))

    # indiretas: orçado SUP do mês (valor e eventos) e realizado acumulado
    mes = _indiretas_mes(ctx, sup, ra)
    ev = eventos_indiretas(ctx, sup, ra)
    orc_ev = ev["orcado"].get(fonte, {}) if fonte else {}
    indiretas = {cl: {"orc_valor": float(orc.get(k) or 0.0), "orc_qtd": float(orc_ev.get("ev_" + k) or 0.0),
                      "real_valor": float(mes[cl][1]), "real_qtd": float(mes[cl][0])} for cl, k in CLASSES}
    linhas = []
    for g in grupos:
        f = lambda d: float(d.get(g, 0.0) or 0.0)
        linhas.append({
            "grupo": g, "data": datas.get(g),
            "orcA": orc_ciclo["A"].get(g, 0.0), "libA": f(fat["A"]["lib"]), "anaA": f(fat["A"]["ana"]),
            "orcE": orc_ciclo["E"].get(g, 0.0), "libE": f(fat["E"]["lib"]), "anaE": f(fat["E"]["ana"]),
            "canc": f(canc_g),
            **{f"eco{s}_{i}": f(eco_t[(s, r)]) for s in ("A", "E") for i, r in (("at", ra), ("an", rn))},
            **{f"soc{s}_{i}": f(soc_t[(s, r)]) for s in ("A", "E") for i, r in (("at", ra), ("an", rn))},
            **{f"vol{s}_{i}": f(vol_t[(s, r)]) for s in ("A", "E") for i, r in (("at", ra), ("an", rn))},
        })
    return {"sup": sup, "ref": ra, "ref_anterior": rn, "mes": nome_mes(ra), "corte": data_corte(ctx),
            "fonte": fonte or "", "fonte_rf": fonte_rf or "", "linhas": linhas, "indiretas": indiretas}


# ---------------------------------------------------------------- Excel
def gera_xlsx(dados, fotos=None):
    """Bytes do .xlsx + a "foto" do realizado acumulado das indiretas (para guardar e usar no próximo export).
    fotos: [{"ate": "AAAA-MM-DD", "valor": {classe: acumulado}, "qtd": {classe: acumulado}}] dos exports anteriores."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L

    CAB, SUB, ZEB = PatternFill("solid", fgColor="0F2A3D"), PatternFill("solid", fgColor="1F4E79"), PatternFill("solid", fgColor="DDEBF7")
    PASSOU, NEG = PatternFill("solid", fgColor="E7E6E6"), PatternFill("solid", fgColor="FFC7CE")
    B, N, NB = Font(bold=True, color="FFFFFF", name="Calibri", size=10), Font(name="Calibri", size=10), Font(name="Calibri", size=10, bold=True)
    fino = Side(style="thin", color="BFBFBF")
    BORDA = Border(left=fino, right=fino, top=fino, bottom=fino)
    C = Alignment(horizontal="center", vertical="center", wrap_text=True)
    MOEDA = '_("R$"* #,##0.00_);_("R$"* \\(#,##0.00\\);_("R$"* "-"??_);_(@_)'
    INT, PCT, DATA, DEC = "#,##0", "0.0%", "dd/mm/yyyy", "#,##0.00"
    sup_nome = "Todas as superintendências" if dados["sup"] == TODAS else dados["sup"]
    at, an = nome_mes_curto(dados["ref"]), nome_mes_curto(dados["ref_anterior"])
    corte = dados["corte"]
    wb = Workbook()
    wb.remove(wb.active)

    def aba(nome, titulo, cab1, cab2, linhas, fmts, total=None, larg=None, nota=None, sombra=None):
        ws = wb.create_sheet(nome)
        ws["A1"] = titulo
        ws["A1"].font = Font(bold=True, size=13, color="0F2A3D", name="Calibri")
        if nota:
            ws["A2"] = nota
            ws["A2"].font = Font(italic=True, size=9, color="595959", name="Calibri")
        r0 = 4
        if cab1:
            c = 1
            for txt, span in cab1:
                ws.cell(r0, c, txt)
                if span > 1:
                    ws.merge_cells(start_row=r0, start_column=c, end_row=r0, end_column=c + span - 1)
                for k in range(c, c + span):
                    x = ws.cell(r0, k)
                    x.fill, x.font, x.alignment, x.border = CAB, B, C, BORDA
                c += span
            r0 += 1
        for j, t in enumerate(cab2, 1):
            x = ws.cell(r0, j, t)
            x.fill, x.font, x.alignment, x.border = SUB, B, C, BORDA
        for i, lin in enumerate(linhas):
            for j, val in enumerate(lin, 1):
                x = ws.cell(r0 + 1 + i, j, val)
                x.font, x.border, x.alignment = N, BORDA, Alignment(horizontal="center")
                if fmts[j - 1]:
                    x.number_format = fmts[j - 1]
                if sombra and sombra(i):
                    x.fill = PASSOU
                elif i % 2:
                    x.fill = ZEB
                if fmts[j - 1] == PCT and isinstance(val, (int, float)) and val < 0:
                    x.fill = NEG
        if total:
            rt = r0 + 1 + len(linhas)
            for j, val in enumerate(total, 1):
                x = ws.cell(rt, j, val)
                x.fill, x.font, x.border, x.alignment = CAB, B, BORDA, Alignment(horizontal="center")
                if fmts[j - 1]:
                    x.number_format = fmts[j - 1]
        for j, w in enumerate(larg or [], 1):
            ws.column_dimensions[L(j)].width = w
        ws.freeze_panes = ws.cell(r0 + 1, 2)
        return ws, r0 + 1 + len(linhas) + (1 if total else 0)

    lin = dados["linhas"]
    num = lambda g: int(g) if str(g).isdigit() else g
    pct = lambda a, b: (a / b - 1) if b else 0
    # 1 Faturamento
    corpo = [[l["data"], num(l["grupo"]), l["orcA"], l["libA"], l["anaA"], l["orcE"], l["libE"], l["anaE"]] for l in lin]
    tot = ["", "Total Geral"] + [sum(x[k] or 0 for x in corpo) for k in range(2, 8)]
    aba("1 Faturamento", f"Faturamento {dados['mes']} — {sup_nome} (por ciclo)", [("", 2), ("Água", 3), ("Esgoto", 3)],
        ["Data leitura", "Ciclo", "Orçado", "Liberado", "Em Análise", "Orçado", "Liberado", "Em Análise"], corpo,
        [DATA, None, MOEDA, MOEDA, MOEDA, MOEDA, MOEDA, MOEDA], tot, [13, 8, 17, 17, 17, 17, 17, 17],
        f"Orçado por ciclo = orçado {dados.get('fonte_rf') or 'RF'} do mês × participação do ciclo no faturado (média dos últimos meses). "
        "Liberado / Em Análise = faturado pela Situação Conta.")
    # 2 Cancelamento
    corpo = [[num(l["grupo"]), l["canc"] or None] for l in lin]
    aba("2 Cancelamento", f"Cancelamento por ciclo — {dados['mes']} — {sup_nome}", None, ["Ciclo", "Cancelamento (R$)"], corpo,
        [None, MOEDA], ["Total Geral", sum(l["canc"] for l in lin)], [10, 20])
    # 3/5 Economias, 4/6 Volume
    for s, serv in (("A", "Água"), ("E", "Esgoto")):                       # 3 Economias Água, 4 Volume Água, 5 e 6 de esgoto
        nome, tit = f"{3 if s == 'A' else 5} Economias {serv}", f"Economias faturadas — {serv}"
        corpo = [[num(l["grupo"]), l[f"eco{s}_at"], l[f"soc{s}_at"], l[f"eco{s}_an"], l[f"soc{s}_an"],
                  pct(l[f"eco{s}_at"], l[f"eco{s}_an"]), l[f"eco{s}_at"] - l[f"eco{s}_an"]] for l in lin]
        t = [sum(x[k] for x in corpo) for k in range(1, 5)]
        aba(nome, f"{tit} — {sup_nome}", [("", 1), (at, 2), (an, 2), ("", 2)], ["Ciclo", "Economias", "Social", "Economias", "Social", "∆ (%)", "∆"],
            corpo, [None, INT, INT, INT, INT, PCT, INT], ["Total"] + t + [pct(t[0], t[2]), t[0] - t[2]], [8, 12, 10, 12, 10, 10, 10])
        nome, tit = f"{4 if s == 'A' else 6} Volume {serv}", f"Volume faturado — {serv}"
        corpo = [[num(l["grupo"]), l[f"vol{s}_at"], l[f"vol{s}_an"], (l[f"vol{s}_at"] / l[f"vol{s}_an"]) if l[f"vol{s}_an"] else 0,
                  l[f"vol{s}_at"] - l[f"vol{s}_an"]] for l in lin]
        a, b_ = sum(x[1] for x in corpo), sum(x[2] for x in corpo)
        aba(nome, f"{tit} — {sup_nome}", None, ["Ciclo", f"{at} (m³)", f"{an} (m³)", "∆ (%)", "∆ (m³)"], corpo, [None, INT, INT, PCT, INT],
            ["Total", a, b_, (a / b_) if b_ else 0, a - b_], [8, 13, 13, 10, 12], f"∆ (%) no mesmo critério da planilha: {at} ÷ {an}.")
    # 7/8 Indiretas
    dias = calendario(dados["ref"])
    fotos = fotos or []
    foto_nova = {"ate": corte.isoformat(), "valor": {}, "qtd": {}}
    sem = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    for nome, tit, tipo, fmt in (("7 Indiretas R$", "Indiretas — valor (R$) por dia útil", "valor", MOEDA),
                                 ("8 Indiretas Qtd", "Indiretas — quantidade de eventos por dia útil", "qtd", DEC)):
        por_classe, memoria = [], []
        for cl, _ in CLASSES:
            d = dados["indiretas"][cl]
            acc, orc_mes = d["real_" + tipo], d["orc_" + tipo]
            f_cl = []
            for f in fotos:
                try:
                    f_cl.append((dt.date.fromisoformat(f["ate"]), float((f.get(tipo) or {}).get(cl, 0.0))))
                except (KeyError, ValueError, TypeError):
                    continue
            por_classe.append(distribui(dias, corte, f_cl, acc, orc_mes, cl == "CORTE"))
            foto_nova[tipo][cl] = acc
            n_fut = sum(1 for dd, c in dias if dd > corte and (c or cl != "CORTE"))
            memoria.append([cl, orc_mes, acc, orc_mes - acc, n_fut, (orc_mes - acc) / n_fut if n_fut else 0])
        corpo = []
        for dd, c in dias:
            l = [dd, sem[dd.weekday()], "Sim" if c else "Não"]
            for k in range(len(CLASSES)):
                o, r = por_classe[k][dd]
                l += [o, r, (pct(r, o) if o else "") if r is not None else ""]
            corpo.append(l)
        tot = ["Total", "", ""]
        for k in range(len(CLASSES)):
            tot += [sum(x[3 + 3 * k] or 0 for x in corpo), sum(x[4 + 3 * k] or 0 for x in corpo), ""]
        ws, fim = aba(nome, f"{tit} — {dados['mes']} — {sup_nome}", [("", 3)] + [(cl, 3) for cl, _ in CLASSES],
                      ["Dia", "Semana", "Corte?"] + ["Orçado", "Realizado", "∆ (%)"] * len(CLASSES), corpo,
                      [DATA, None, None] + [fmt, fmt, PCT] * len(CLASSES), tot, [12, 8, 8] + [15, 15, 15] * len(CLASSES),
                      f"Dados até {corte:%d/%m/%Y} (cinza): Orçado = Realizado — o realizado de cada semana é dividido pelos dias úteis "
                      "da semana. Dias seguintes: (orçado do mês − realizado acumulado) ÷ dias que faltam. Corte não conta sextas nem "
                      f"vésperas de feriado. Orçado: {dados['fonte'] or 'SUP'}.",
                      sombra=lambda i: dias[i][0] <= corte)
        r = fim + 2
        ws.cell(r, 4, "Memória do cálculo").font = NB
        for j, t in enumerate(["Classe", "Orçado do mês", "Realizado acumulado", "Falta", "Dias que faltam", "Orçado por dia restante"], 1):
            x = ws.cell(r + 1, j + 3, t)
            x.fill, x.font, x.alignment, x.border = SUB, B, C, BORDA
        for k, m in enumerate(memoria):
            for j, val in enumerate(m, 1):
                x = ws.cell(r + 2 + k, j + 3, val)
                x.border, x.font = BORDA, N
                if j in (2, 3, 4, 6):
                    x.number_format = fmt
    # Leia-me
    ws = wb.create_sheet("Leia-me", 0)
    texto = [f"Acompanhamento Mensal — {dados['mes']} — {sup_nome}", "",
             f"Dados até {corte:%d/%m/%Y} (D-1) · Orçado — faturamento por ciclo: {dados.get('fonte_rf') or 'RF'}; indiretas: {dados['fonte'] or 'SUP'} · Gerado em {dt.datetime.now():%d/%m/%Y %H:%M}", "",
             "Uma aba por tabela da planilha de acompanhamento, na mesma ordem de colunas: copie e cole como valores.",
             "1 Faturamento · 2 Cancelamento · 3 Economias Água · 4 Volume Água · 5 Economias Esgoto · 6 Volume Esgoto · 7 Indiretas R$ · 8 Indiretas Qtd",
             "", "Indiretas: nos dias que já passaram (cinza), Orçado = Realizado. O realizado de cada semana (entre um export e o seguinte)",
             "é dividido igualmente pelos dias úteis da semana; o que falta do orçado do mês é dividido pelos dias que faltam.",
             "Corte: só dias úteis que não são sexta nem véspera de feriado. A memória do cálculo fica embaixo de cada tabela."]
    for i, t in enumerate(texto, 1):
        ws.cell(i, 1, t).font = Font(bold=(i == 1), size=13 if i == 1 else 10, color="0F2A3D" if i == 1 else "000000", name="Calibri")
    ws.column_dimensions["A"].width = 130
    for w in wb.worksheets:
        w.sheet_properties.pageSetUpPr.fitToPage = True
        w.page_setup.fitToWidth, w.page_setup.fitToHeight, w.page_setup.orientation = 1, 1, "landscape"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), foto_nova


def nome_arquivo(dados):
    sup = "Todas" if dados["sup"] == TODAS else dados["sup"].title()
    return f"Acompanhamento_{sup}_{dados['ref'].replace('/', '-')}_ate_{dados['corte']:%d-%m}.xlsx"
