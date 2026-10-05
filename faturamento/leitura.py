# -*- coding: utf-8 -*-
"""Leitura e classificação dos arquivos (consumo, fatura e cronograma)."""
import glob
import io
import os
import re
import zipfile

import numpy as np
import pandas as pd

from .config import (COLUNAS_CONSUMO, COLUNAS_CRONOGRAMA, COLUNAS_ECONOMIA_TODAS, COLUNAS_FATURA,
                     NOMES_LIGACAO, NOMES_SAIDA_LEGADOS, NOME_RELATORIO_HTML,
                     NOME_TOP100_XLSX, RUBRICAS_VALIDAS, CHAVES_CANCELAMENTO,
                     CLASSE_INDIRETA_POR_RUBRICA, chave_texto)

# Erros esperados ao abrir/ler planilhas e CSVs (arquivo corrompido, formato inesperado, falta de leitor)
ERROS_LEITURA = (OSError, ValueError, ImportError, KeyError, zipfile.BadZipFile)

CABECALHOS_CONHECIDOS = COLUNAS_CONSUMO | COLUNAS_FATURA | COLUNAS_CRONOGRAMA


def _texto_csv(caminho):
    """Lê o CSV como texto (UTF-8 com BOM; se não der, Latin-1)."""
    with open(caminho, "rb") as f_bytes:
        raw = f_bytes.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def detecta_linha_cabecalho(caminho, sheet_name=0, max_linhas=10):
    """Índice da linha do cabeçalho (nas primeiras linhas) ou None se não achar.

    Falhar aqui não é erro: devolve None e a leitura usa a primeira linha. Isso também
    cobre CSVs do Excel que começam com a linha "sep=;" (a detecção falha e `le_dataframe`
    pula essa linha sozinha).
    """
    ext = os.path.splitext(caminho)[1].lower()
    try:
        if ext in (".xlsx", ".xls"):
            df_raw = pd.read_excel(caminho, sheet_name=sheet_name, header=None, dtype=str, nrows=max_linhas)
        else:
            df_raw = pd.read_csv(io.StringIO(_texto_csv(caminho)), sep=";", header=None, dtype=str, nrows=max_linhas)
    except ERROS_LEITURA:
        return None
    for i in range(len(df_raw)):
        valores_linha = set(str(v).strip() for v in df_raw.iloc[i].tolist())
        if len(valores_linha & CABECALHOS_CONHECIDOS) >= 2:
            return i
    return None


def le_dataframe(caminho, nrows=None, sheet_name=0):
    ext = os.path.splitext(caminho)[1].lower()
    linha_header = detecta_linha_cabecalho(caminho, sheet_name=sheet_name)
    if linha_header is None:
        linha_header = 0
    if ext == ".csv":
        f = io.StringIO(_texto_csv(caminho))
        primeira_linha = f.readline()
        skip = linha_header
        if primeira_linha.strip().lower().startswith("sep="):
            skip += 1
        f.seek(0)
        df = pd.read_csv(f, sep=";", skiprows=skip, dtype=str)
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(caminho, dtype=str, header=linha_header)
    else:
        return None
    df.columns = df.columns.astype(str).str.strip().str.replace('"', '').str.replace('ï»¿', '')
    df.columns = [c.replace("P?blica", "Publica").replace("Pública", "Publica") for c in df.columns]
    return df


MES_ABREV = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
             "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
_RE_COL_MES = re.compile(r"^([a-zç]{3}/\d{2}|soma de \d{2}/\d{2}/\d{4})$", re.I)
_RE_PREFIXO_NUM = re.compile(r"^\d+(?:\.\d+)*\.?\s+")


def colunas_de_mes(colunas):
    return [c for c in colunas if _RE_COL_MES.match(str(c).strip())]


def identifica_tipo(colunas, nome=""):
    colunas = set(colunas)
    if {"Sup", "Rubrica"}.issubset(colunas) and len(colunas_de_mes(colunas)) >= 3:
        return "orcado"
    # O serviço avulso tem as mesmas colunas da fatura (inclusive endereço e localidade),
    # então só o nome do arquivo o diferencia.
    if "avulso" in chave_texto(nome).lower() and COLUNAS_FATURA.issubset(colunas):
        return "avulso"
    if COLUNAS_CONSUMO.issubset(colunas):
        return "consumo"
    if COLUNAS_FATURA.issubset(colunas):
        return "fatura"
    if COLUNAS_CRONOGRAMA.issubset(colunas):
        return "cronograma"
    return "desconhecido"


def referencia_mes(valor):
    """'ago/26', '08/2026', '15/08/2026' ou data -> 'MM/AAAA' (ou None)."""
    t = re.sub(r"^soma de\s+", "", str(valor).strip().lower())
    m = re.match(r"^([a-zç]{3})[a-z]*[/\-. ](\d{2}|\d{4})$", t)
    if m and m.group(1) in MES_ABREV:
        ano = m.group(2) if len(m.group(2)) == 4 else "20" + m.group(2)
        return f"{MES_ABREV[m.group(1)]:02d}/{ano}"
    dt = pd.to_datetime(t, format="%d/%m/%Y", errors="coerce")
    if pd.isna(dt):
        dt = pd.to_datetime(t, format="%m/%Y", errors="coerce")
    return None if pd.isna(dt) else dt.strftime("%m/%Y")


def padroniza_referencia(serie):
    """Qualquer formato comum de data/mês -> 'MM/AAAA' (dd/mm/aaaa, mm/aaaa, aaaa-mm-dd hh:mm:ss, 'out/26'...)."""
    serie = serie.astype(str).str.strip()
    dt = pd.to_datetime(serie, format="%d/%m/%Y", errors="coerce")
    for formato in ("%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m", "%m-%Y"):
        faltam = dt.isna()
        if not faltam.any():
            break
        dt.loc[faltam] = pd.to_datetime(serie[faltam], format=formato, errors="coerce")
    faltam = dt.isna()
    if faltam.any():                       # nomes de mês ('out/26', 'Outubro/2026') e o que sobrar
        texto = serie[faltam].str.replace(r"(?i)^([a-zç]{3})[a-zç]*", lambda m: m.group(1), regex=True)
        refs = texto.map(referencia_mes)
        dt.loc[faltam] = pd.to_datetime(refs, format="%m/%Y", errors="coerce")
    return dt.dt.strftime("%m/%Y")


def acha_coluna_ligacao(df, tipo, caminho):
    col = next((c for c in NOMES_LIGACAO if c in df.columns), None)
    if col is None:
        raise KeyError(
            f"Coluna de nº de ligação não encontrada no arquivo de {tipo} "
            f"{os.path.basename(caminho)}. Colunas disponíveis: {list(df.columns)}"
        )
    return col


def referencia_do_nome(nome_arquivo):
    """Mês de referência (MM/AAAA) a partir do nome do arquivo de consumo ('Consumo 09-2026.csv', 'Consumo out-26.csv'...)."""
    match = re.search(r"(?<!\d)(\d{2})[-/._ ](\d{4})(?!\d)", nome_arquivo)
    if match and 1 <= int(match.group(1)) <= 12:
        return f"{match.group(1)}/{match.group(2)}"
    match = re.search(r"(?i)([a-zç]{3})[a-zç]*[-/._ ](\d{4}|\d{2})(?!\d)", nome_arquivo)
    if match and match.group(1).lower() in MES_ABREV:
        ano = match.group(2) if len(match.group(2)) == 4 else "20" + match.group(2)
        return f"{MES_ABREV[match.group(1).lower()]:02d}/{ano}"
    return np.nan


def processa_consumo(caminho):
    print(f"   ⚙️ Processando CONSUMO: {os.path.basename(caminho)}")
    df = le_dataframe(caminho)
    col_ligacao = acha_coluna_ligacao(df, "CONSUMO", caminho)

    for c in ["Leitura Atual", "Consumo Medido", "Consumo Faturado"] + COLUNAS_ECONOMIA_TODAS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    df["Total Economias"] = df[COLUNAS_ECONOMIA_TODAS].sum(axis=1)
    df["Qtd. Tipos de Economia"] = (df[COLUNAS_ECONOMIA_TODAS] > 0).sum(axis=1)
    df["Economia Mista"] = df["Qtd. Tipos de Economia"].apply(lambda x: "Sim" if x > 1 else "Não")
    df["Referência"] = referencia_do_nome(os.path.basename(caminho))

    df["N. Ligação_consumo"] = df[col_ligacao].astype(str).str.strip()

    colunas_conflito = ["Grupo", "Situacao Ligacao", "Nome Cliente", "Categoria", col_ligacao]
    df = df.drop(columns=[c for c in colunas_conflito if c in df.columns], errors="ignore")

    return df.drop_duplicates(subset=["N. Ligação_consumo", "Referência"])


def _valor_br(serie):
    return pd.to_numeric(serie.str.replace(".", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")


def processa_fatura(caminho):
    return processa_fatura_completa(caminho)[0]


def processa_fatura_completa(caminho):
    """Devolve (linhas de água/esgoto, linhas de cancelamento) da fatura."""
    print(f"   ⚙️ Processando FATURA: {os.path.basename(caminho)}")
    df = le_dataframe(caminho)
    col_ligacao = acha_coluna_ligacao(df, "FATURA", caminho)

    df["N. da Ligacao"] = df[col_ligacao].astype(str).str.strip()

    df["Valor Parcela"] = (
        df["Valor Parcela"]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )
    df_filter = df[df["Rubrica"].isin(RUBRICAS_VALIDAS)].copy()
    df_filter["Grupo"] = df_filter["Grupo"].astype(str).str.strip()
    df_filter["Referencia de Leitura"] = padroniza_referencia(df_filter["Referencia de Leitura"])

    chaves = df["Rubrica"].map(chave_texto)
    canc = df[chaves.map(lambda k: any(k.startswith(c) if c.startswith("COFINS") else k == c for c in CHAVES_CANCELAMENTO))].copy()
    canc["Referencia de Leitura"] = padroniza_referencia(canc["Referencia de Leitura"])
    return df_filter, canc


def processa_avulso(caminho):
    """Serviços avulsos (receita indireta): uma linha por lançamento, com a classe da rubrica."""
    print(f"   ⚙️ Processando SERVIÇO AVULSO: {os.path.basename(caminho)}")
    df = le_dataframe(caminho)
    df = df.dropna(how="all")
    df = df[df["Rubrica"].notna()].copy()
    df["Valor Parcela"] = _valor_br(df["Valor Parcela"].astype(str).str.strip())
    df["Referencia"] = df["Referencia de Leitura"].map(referencia_mes)
    df["Classe"] = df["Rubrica"].map(lambda r: CLASSE_INDIRETA_POR_RUBRICA.get(chave_texto(r)))
    return df


def processa_orcado(caminho, aba=0):
    """Planilha de orçado (RF / RF SUP): colunas Sup, Rubrica e um mês por coluna.
    Devolve formato longo: Sup, Rubrica, Referencia (MM/AAAA), Valor."""
    print(f"   ⚙️ Processando ORÇADO: {os.path.basename(caminho)}")
    df = le_dataframe(caminho, sheet_name=aba)
    meses = colunas_de_mes(df.columns)
    longo = df.melt(id_vars=["Sup", "Rubrica"], value_vars=meses, var_name="Mes", value_name="Valor")
    longo["Valor"] = pd.to_numeric(longo["Valor"], errors="coerce")
    longo = longo.dropna(subset=["Valor"])
    longo["Referencia"] = longo["Mes"].map(referencia_mes)
    longo["Sup"] = longo["Sup"].astype(str).str.strip()
    # o RF antigo numera as linhas ("01.01.01.01. Fat. Bruto de água - Direto"): tira o número
    longo["Rubrica"] = longo["Rubrica"].astype(str).str.strip().str.replace(_RE_PREFIXO_NUM, "", regex=True)
    return longo[["Sup", "Rubrica", "Referencia", "Valor"]]


def processa_cronograma(caminho):
    print(f"   ⚙️ Processando CRONOGRAMA: {os.path.basename(caminho)}")
    nome = os.path.basename(caminho)
    ext = os.path.splitext(caminho)[1].lower()
    frames = []
    if ext in (".xlsx", ".xls"):
        try:
            abas = pd.ExcelFile(caminho).sheet_names
        except Exception as exc:   # arquivo problemático não derruba a análise; o motivo é informado
            print(f"   ⚠️ Cronograma {nome} não pôde ser aberto ({exc}); ignorado.")
            return pd.DataFrame()
        for aba in abas:
            try:
                df = le_dataframe(caminho, sheet_name=aba)
            except Exception as exc:
                print(f"   ⚠️ Aba '{aba}' de {nome} ignorada ({exc}).")
                continue
            if df is not None and COLUNAS_CRONOGRAMA.issubset(set(df.columns)):
                df["Aba/Mês Cronograma"] = str(aba)
                frames.append(df)
    else:
        df = le_dataframe(caminho)
        if df is not None and COLUNAS_CRONOGRAMA.issubset(set(df.columns)):
            df["Aba/Mês Cronograma"] = nome
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["Grupo", "Data da Leitura", "Qts. Dias", "Aba/Mês Cronograma"])
    df_final = pd.concat(frames, ignore_index=True)
    df_final["Grupo"] = df_final["Grupo"].astype(str).str.strip()
    df_final = df_final[df_final["Grupo"] != ""]
    df_final["Qts. Dias"] = pd.to_numeric(df_final["Qts. Dias"], errors="coerce")
    return df_final.drop_duplicates(subset=["Grupo", "Aba/Mês Cronograma"])


def lista_arquivos_entrada(pasta):
    """CSV/XLSX/XLS da pasta, sem os arquivos que o próprio pipeline gera."""
    saidas = {os.path.abspath(os.path.join(pasta, n))
              for n in (NOME_RELATORIO_HTML, NOME_TOP100_XLSX) + NOMES_SAIDA_LEGADOS}
    brutos = []
    for ext in ("csv", "xlsx", "xls"):
        brutos += glob.glob(os.path.join(pasta, f"*.{ext}"))
    return [c for c in brutos if os.path.abspath(c) not in saidas]


def classifica_arquivos(pasta, progresso=None):
    """Descobre o tipo de cada arquivo. Devolve dict com listas de caminhos por tipo
    e `ignorados`: lista de {arquivo, motivo} para os que não foram reconhecidos."""
    arquivos = lista_arquivos_entrada(pasta)
    print(f"🔍 {len(arquivos)} arquivo(s) encontrado(s) em: {pasta}\n")
    if progresso:
        progresso.atualiza(2, "Varrendo arquivos")
    if not arquivos:
        if progresso:
            progresso.atualiza(18, "Nenhum arquivo")
        raise FileNotFoundError(f"Nenhum arquivo CSV/XLSX/XLS em {pasta}")

    classificados, ignorados = [], []
    for idx, caminho in enumerate(arquivos, start=1):
        nome = os.path.basename(caminho)
        tipo_achado = None
        try:
            if caminho.lower().endswith((".xlsx", ".xls")):
                for aba in pd.ExcelFile(caminho).sheet_names:
                    df_head = le_dataframe(caminho, nrows=5, sheet_name=aba)
                    if df_head is None:
                        continue
                    tipo = identifica_tipo(df_head.columns, nome)
                    if tipo != "desconhecido":
                        classificados.append({"caminho": caminho, "tipo": tipo, "aba": aba})
                        tipo_achado = tipo
                        break
            else:
                df_head = le_dataframe(caminho, nrows=5)
                if df_head is not None:
                    tipo = identifica_tipo(df_head.columns, nome)
                    if tipo != "desconhecido":
                        classificados.append({"caminho": caminho, "tipo": tipo, "aba": 0})
                        tipo_achado = tipo
            if tipo_achado is None:
                motivo = "colunas não correspondem a consumo, fatura ou cronograma"
                if df_head is not None and {"Sup", "Rubrica"}.issubset(df_head.columns):
                    motivo = "planilha de orçado fora do modelo (esperado: colunas Sup, Rubrica e meses como jan/26, igual ao RF01T26)"
                ignorados.append({"arquivo": nome, "motivo": motivo})
        except Exception as exc:   # um arquivo ilegível é ignorado, mas listado com o motivo
            print(f"   ⚠️ {nome} ignorado: não foi possível ler ({exc})")
            ignorados.append({"arquivo": nome, "motivo": f"não foi possível ler: {exc}"})
        if progresso:
            progresso.etapa(idx, len(arquivos), 2, 18, f"Classificando ({idx}/{len(arquivos)})")

    resultado = {t: [c["caminho"] for c in classificados if c["tipo"] == t]
                 for t in ("consumo", "fatura", "cronograma", "avulso")}
    resultado["orcado"] = [(c["caminho"], c["aba"]) for c in classificados if c["tipo"] == "orcado"]
    resultado["ignorados"] = ignorados
    print(f"📁 Consumo: {len(resultado['consumo'])} | Fatura: {len(resultado['fatura'])} | "
          f"Cronograma: {len(resultado['cronograma'])} | "
          f"Serviço avulso: {len(resultado['avulso'])} | Orçado: {len(resultado['orcado'])}")
    for ig in ignorados:
        print(f"   ⚠️ Ignorado: {ig['arquivo']} — {ig['motivo']}")

    faltando = [nome for nome, lista in (("FATURA", resultado["fatura"]), ("CONSUMO", resultado["consumo"])) if not lista]
    if faltando:
        raise FileNotFoundError(
            "Nenhum arquivo de " + " nem de ".join(faltando) + " foi identificado na pasta. "
            "Confira se os arquivos têm as colunas esperadas "
            f"(fatura: {sorted(COLUNAS_FATURA)}; consumo: {sorted(COLUNAS_CONSUMO)})."
            + (" Arquivos ignorados: " + "; ".join(f"{i['arquivo']} ({i['motivo']})" for i in ignorados) if ignorados else "")
        )
    return resultado
