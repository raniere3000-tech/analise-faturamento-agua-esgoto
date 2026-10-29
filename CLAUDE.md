# Regras do repositório

## Dois repositórios, o MESMO código

Este código é publicado em dois repositórios da conta `raniere3000-tech`, que devem ter **sempre os mesmos arquivos**
(fora `.github/`, que pode ter workflows próprios):

| Repositório | Site | Painel |
|---|---|---|
| `analise-faturamento-agua-esgoto` (original) | https://raniere3000-tech.github.io/analise-faturamento-agua-esgoto/ | todas as SUPs |
| `previa_de_fat_leste` (Leste) | https://raniere3000-tech.github.io/previa_de_fat_leste/ | só a LESTE |

- **Toda alteração vale para os dois.** Faça a mudança, teste e publique a mesma versão nos dois repositórios
  (mesmos arquivos, mesmo número de versão, mesma mensagem de commit). Não deixe um repositório à frente do outro.
- **Nada de código separado por painel.** O painel é reconhecido pelo endereço do site (`PAINEL` no `index.html`) ou,
  no PC/Colab, pelo nome da pasta do repositório (`painel_atual()` em `faturamento/config.py`). O que muda entre os
  painéis fica em `faturamento/regras.json` → `"paineis"` (hoje só `sup_do_painel`). O prefixo do armazenamento do
  navegador fica em `PAINEIS_COM_ESCOPO` no `index.html` (o original fica sem prefixo para manter o que já estava
  guardado). Para uma diferença nova entre os painéis, crie uma chave em `"paineis"` — não edite um repositório só.

## Versão (a partir da v2.0)

- A versão é **v2.0**, e **cada alteração soma 0.1 no número depois do ponto**: v2.0 → v2.1 → v2.2 → … → v2.9 →
  **v2.10** → v2.11 … (não vira v3.0 sozinha). Só passa para **v3.0** quando o dono pedir uma mudança grande.
- Em `index.html`: aumente `VERSAO_SITE` (ex.: `"v2.0-20261029"` → `"v2.1-AAAAMMDD"`, com a data do dia) e o texto do
  `<span id="versao">` para o mesmo número (ex.: `v2.1`). O teste `test_selo_de_versao_igual_a_versao_do_site` confere.
- A mensagem do commit começa com essa versão (ex.: `v2.1: ...`). A mesma versão vai para os dois repositórios.
- Versões antigas (v1 a v142 no original, v1 a v123 na Leste) ficaram no histórico; a v2.0 juntou as duas.

## Antes de publicar

- Rode `python -m pytest tests -q` antes de enviar.
- Arquivo novo no pacote `faturamento/` precisa entrar em `ARQUIVOS_PY` no `analisador.worker.js`.
- Mudou a leitura dos arquivos? Aumente `VERSAO` em `faturamento/cache_arquivos.py` (descarta o que o navegador guardou).
- **Publicação autorizada:** o dono do repositório autorizou mesclar sempre. Depois de validar
  (testes passando), abra o PR da branch de trabalho para a `main` e mescle — a `main` é o que o
  GitHub Pages publica. Antes de mesclar, confira que o PR já contém o último commit enviado.
  Faça isso **nos dois repositórios**.
