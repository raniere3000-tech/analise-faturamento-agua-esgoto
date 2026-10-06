# Regras do repositório

- **Toda atualização muda a versão do cabeçalho do site.** Em `index.html`, aumente `VERSAO_SITE`
  (ex.: `"v16-20261006"` → `"v17-AAAAMMDD"`, com a data do dia) e o texto do `<span id="versao">`
  para o mesmo número. A mensagem do commit começa com essa versão (ex.: `v17: ...`).
- Rode `python -m pytest tests -q` antes de enviar.
- Arquivo novo no pacote `faturamento/` precisa entrar em `ARQUIVOS_PY` no `analisador.worker.js`.
