# -*- coding: utf-8 -*-
"""Análise de faturamento de água e esgoto — mês atual x mês anterior.

Ponto de entrada para rodar no PC ou no Google Colab. A lógica está no pacote `faturamento/`.

ORIGEM DOS ARQUIVOS (ajuste MODO_ORIGEM abaixo ou use --modo):
  "upload" → (Colab) botão para escolher os arquivos do seu computador
  "drive"  → (Colab) usa uma pasta do Google Drive (PASTA_DRIVE)
  "local"  → (PC) abre a janela para selecionar a pasta

Uso no PC:      python acompanhamento_faturamento.py            (ou --pasta CAMINHO)
Uso no Colab:   !git clone https://github.com/raniere3000-tech/analise-faturamento-agua-esgoto
                %cd analise-faturamento-agua-esgoto
                !pip install -q xlsxwriter
                %run acompanhamento_faturamento.py
"""
import argparse
import os
import sys

MODO_ORIGEM = "upload"
PASTA_DRIVE = "/content/drive/MyDrive/Faturamento"   # usado só no modo "drive"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from faturamento import executar                                  # noqa: E402
from faturamento.config import NOME_RELATORIO_HTML, NOME_TOP100_XLSX   # noqa: E402
from faturamento.origem import define_pasta_arquivos, em_colab    # noqa: E402


def principal(argv=None):
    ap = argparse.ArgumentParser(description="Comparativo de faturamento de água e esgoto")
    ap.add_argument("--pasta", help="pasta com os arquivos (pula a seleção interativa)")
    ap.add_argument("--modo", choices=["upload", "drive", "local"], default=MODO_ORIGEM)
    args, _ = ap.parse_known_args(argv)   # parse_known_args: o Colab/Jupyter injeta argumentos próprios

    if args.pasta:
        os.environ["FATURAMENTO_PASTA"] = args.pasta
    pasta = define_pasta_arquivos(modo=args.modo, pasta_drive=PASTA_DRIVE)
    executar(pasta)

    # Colab (upload): baixa os resultados automaticamente
    if em_colab() and args.modo == "upload":
        from google.colab import files
        for nome in (NOME_RELATORIO_HTML, NOME_TOP100_XLSX):
            caminho = os.path.join(pasta, nome)
            if os.path.exists(caminho):
                files.download(caminho)


if __name__ == "__main__":
    principal()
