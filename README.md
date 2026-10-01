# Análise de Faturamento — Água e Esgoto

Pipeline em Python (pandas) que compara o faturamento de água e esgoto do mês atual com o mês anterior e gera:

- `Top100_Quedas_Consumo.xlsx`: ranking das maiores quedas de consumo (água e esgoto)
- `Relatorio_Comparativo.html`: relatório com KPIs, gráfico, insights e tabelas filtráveis

## Pelo site (sem instalar nada)

Abra https://raniere3000-tech.github.io/analise-faturamento-agua-esgoto/, clique em **Selecionar pasta e analisar** e escolha a pasta com os arquivos. Depois de ler os arquivos, o site mostra o **Top 20 clientes com maior consumo** (Consumo Faturado do mês atual): você pode alterar o consumo ou o valor total (água + esgoto) de cada um e clicar em **Aplicar alterações e gerar relatório** (ou **Pular**). A alteração vale só para essa análise e só para o mês atual; os arquivos da pasta não mudam, e o relatório avisa quando há valores ajustados. Quando a análise chega a 100%, o relatório abre sozinho em tela cheia, com botões para baixar o HTML e o Top 100 em Excel. No Chrome e no Edge, o botão **Atualizar** relê a mesma pasta depois que você coloca arquivos novos nela.

O processamento roda no navegador: o site executa este mesmo script Python com o [Pyodide](https://pyodide.org) (`analisador.worker.js` + `executor_web.py`). Os arquivos não são enviados para nenhum servidor. Na primeira vez, o navegador baixa o Python (cerca de 30 MB), que depois fica em cache.

## Como usar o script

Defina `MODO_ORIGEM` no início do script:

| Modo | Onde roda | O que faz |
|---|---|---|
| `"upload"` | Google Colab | Mostra um botão para escolher os arquivos do computador e baixa os relatórios no final |
| `"drive"` | Google Colab | Lê os arquivos de uma pasta do Google Drive (`PASTA_DRIVE`) |
| `"local"` | No seu PC | Abre a janela para selecionar a pasta; salva os relatórios nela |

Para rodar localmente:

```bash
pip install pandas numpy openpyxl tqdm
python acompanhamento_faturamento.py
```

## Premissas

- O nome do arquivo de consumo contém o mês (ex.: `09-2026`)
- O nº da ligação é o mesmo em todas as bases
- Só considera as rubricas `VALOR DE AGUA` e `VALOR DE ESGOTO`
- Uma linha por ligação por mês
- O cronograma é cruzado por grupo, não por mês
