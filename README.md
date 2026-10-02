# Análise de Faturamento — Água e Esgoto

Pipeline em Python (pandas) que compara o faturamento de água e esgoto do mês atual com o mês anterior e gera:

- `Top100_Quedas_Consumo.xlsx`: ranking das maiores quedas de consumo (água e esgoto)
- `Relatorio_Comparativo.html`: relatório com KPIs, gráfico, insights e tabelas filtráveis

## Pelo site (sem instalar nada)

Abra https://raniere3000-tech.github.io/analise-faturamento-agua-esgoto/, clique em **Selecionar pasta e analisar** e escolha a pasta com os arquivos. Depois de ler os arquivos, o site mostra **todos os clientes com Situação Conta = EM ANALISE** do mês atual (ordenados por valor): você pode alterar o consumo ou o valor total (água + esgoto) de cada um e clicar em **Aplicar alterações e gerar relatório** (ou **Pular**). A alteração vale só para essa análise e só para o mês atual; os arquivos da pasta não mudam, e o relatório avisa quando há valores ajustados. Quando a análise chega a 100%, o relatório abre sozinho em tela cheia, com botões para baixar o HTML e o Top 100 em Excel. No Chrome e no Edge, o botão **Atualizar** relê a mesma pasta depois que você coloca arquivos novos nela.

O processamento roda no navegador: o site executa este mesmo script Python com o [Pyodide](https://pyodide.org) (`analisador.worker.js` + `executor_web.py`). Os arquivos não são enviados para nenhum servidor. Na primeira vez, o navegador baixa o Python (cerca de 30 MB), que depois fica em cache.

## Abas DRE e Indiretas

Além do comparativo (aba **Diretas**), o relatório tem a aba **DRE** (Projeto/Linha × Orçado RF × Orçado SUP × Realizado, com Δ% e Δ R$) e a aba **Indiretas**, com filtros no cabeçalho do site, como no DRE_Unificado: **Superintendência** (Todas, LAGOS, LESTE, SEM SUP), **Referência** (RF + SUP, só RF, só RF SUP), **Mês** e **Grupo** (vale para Resumo e Diretas). A aba Indiretas traz orçado × realizado por classe, evolução mensal por classe (com gráfico) e quantidade/ticket médio. Coloque na mesma pasta:

| Arquivo | Como é reconhecido | Usado para |
|---|---|---|
| Serviço avulso | nome com "avulso" (ou colunas Endereco Ligacao/Nome da Localidade) | Indiretas (rubrica → classe: CORTE, RELIGAÇÃO, LNA, LNE, SANÇÃO, OUTROS) |
| Fatura do ciclo | colunas Rubrica/Valor Parcela | Diretas e Cancelamento (rubricas de cancelamento) |
| RF (ex.: `RF01T26.xlsx`) | colunas Sup, Rubrica e um mês por coluna | Orçado RF |
| RF SUP | mesmo modelo, com "SUP" no nome | Orçado SUP |

A relação rubrica → classe, as rubricas de cancelamento e cidade → SUP ficam em `faturamento/regras.json`. A SUP vem da cidade (`Nome da Localidade`) da fatura ou do serviço avulso.

## Estrutura do código

O script do Colab foi dividido no pacote `faturamento/` (leitura, base, comparativo, análises, tabelas/painel HTML, relatório, pipeline). As regras de negócio (consumo mínimo, textos padrão, alertas) ficam em `faturamento/regras.json`; CSS e JS do relatório ficam em `faturamento/assets/`. `acompanhamento_faturamento.py` é só a linha de comando: `python acompanhamento_faturamento.py --pasta DADOS --modo local`.

## Testes

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Os testes usam dados sintéticos e rodam também no GitHub Actions a cada push. Se criar um arquivo novo no pacote, inclua-o em `ARQUIVOS_PY` no `analisador.worker.js` (um teste confere).

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

- Na conferência do Top 20, só entram contas com `Situacao Conta` = EM ANALISE (coluna do arquivo de fatura ou consumo)
- O nome do arquivo de consumo contém o mês (ex.: `09-2026`)
- O nº da ligação é o mesmo em todas as bases
- Só considera as rubricas `VALOR DE AGUA` e `VALOR DE ESGOTO`
- Uma linha por ligação por mês
- O cronograma é cruzado por grupo, não por mês
