# -*- coding: utf-8 -*-
"""De onde vêm os arquivos: upload no Colab, Google Drive ou pasta do computador."""
import os

from .config import EXTENSOES_VALIDAS


def em_colab():
    try:
        import google.colab  # noqa: F401
        return True
    except ImportError:
        return False


def seleciona_pasta_local():
    """Abre a janela do sistema para escolher a pasta (execução no PC)."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    pasta = filedialog.askdirectory(
        title="Selecione a pasta com os arquivos de consumo, fatura e cronograma"
    )
    root.destroy()
    if not pasta:
        raise SystemExit("Nenhuma pasta selecionada. Execução cancelada.")
    return pasta


def envia_arquivos_colab(destino, limpar_antes=True):
    """Mostra o botão 'Escolher arquivos' e copia o que foi enviado para a pasta de trabalho."""
    from google.colab import files
    os.makedirs(destino, exist_ok=True)
    if limpar_antes:
        for arq in os.listdir(destino):
            caminho = os.path.join(destino, arq)
            if os.path.isfile(caminho):
                os.remove(caminho)
    print("📤 Clique em 'Escolher arquivos', abra a pasta do seu computador")
    print("   e selecione TODOS os arquivos (Ctrl+A) → Abrir.\n")
    enviados = files.upload()
    if not enviados:
        raise SystemExit("Nenhum arquivo enviado. Execução cancelada.")
    for nome, conteudo in enviados.items():
        if not nome.lower().endswith(EXTENSOES_VALIDAS):
            print(f"   ⚠️ Ignorado (extensão não suportada): {nome}")
        else:
            with open(os.path.join(destino, nome), "wb") as f:
                f.write(conteudo)
            print(f"   ✅ {nome}")
        # files.upload() também grava no diretório atual — remove a cópia extra
        copia_extra = os.path.join(os.getcwd(), nome)
        if os.path.abspath(copia_extra) != os.path.abspath(os.path.join(destino, nome)) and os.path.exists(copia_extra):
            os.remove(copia_extra)
    return destino


def define_pasta_arquivos(modo="upload", pasta_drive="/content/drive/MyDrive/Faturamento"):
    """Escolhe a pasta de trabalho.

    modo: "upload" (Colab: botão para enviar arquivos), "drive" (Colab: pasta do Google Drive)
          ou "local" (PC: janela para escolher a pasta).
    A variável de ambiente FATURAMENTO_PASTA, se existir, tem prioridade (uso por agendadores/testes).
    """
    pasta_externa = os.environ.get("FATURAMENTO_PASTA")
    if pasta_externa:
        pasta = pasta_externa
    elif modo == "local" or not em_colab():
        pasta = seleciona_pasta_local()
    elif modo == "drive":
        from google.colab import drive
        drive.mount("/content/drive")
        pasta = pasta_drive
        if not os.path.isdir(pasta):
            raise FileNotFoundError(f"Pasta não encontrada no Drive: {pasta}")
    else:
        pasta = envia_arquivos_colab("/content/Arquivo")
    print(f"📂 Pasta de trabalho: {pasta}\n")
    return pasta
