// Roda o pipeline Python dentro do navegador (Pyodide), fora da thread da página.
// Nada é enviado para servidor: os arquivos ficam numa pasta virtual na memória.

const PYODIDE_VERSAO = "0.29.5";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSAO}/full/`;
const PASTA = "/dados";
// Arquivos do pacote Python que o site copia para o Pyodide (caminho no site -> pasta virtual /app)
const ARQUIVOS_PY = [
  "faturamento/__init__.py", "faturamento/analises.py", "faturamento/base.py", "faturamento/comparativo.py",
  "faturamento/dre.py", "faturamento/dados.py",
  "faturamento/config.py", "faturamento/contexto.py", "faturamento/formatacao.py", "faturamento/leitura.py",
  "faturamento/origem.py", "faturamento/painel_html.py", "faturamento/pipeline.py", "faturamento/progresso.py",
  "faturamento/relatorio.py", "faturamento/tabelas_html.py", "faturamento/top20.py",
  "faturamento/regras.json", "faturamento/assets/relatorio.css", "faturamento/assets/relatorio.js",
];
const SAIDAS = [
  "Relatorio_Comparativo.html",
  "Top100_Quedas_Consumo.xlsx",
];

importScripts(PYODIDE_URL + "pyodide.js");

let pyodidePronto = null;

function avisa(tipo, dados, transferir = []) {
  self.postMessage({ tipo, ...dados }, transferir);
}

async function preparaPython() {
  avisa("etapa", { texto: "Carregando o Python no navegador…" });
  const pyodide = await loadPyodide({ indexURL: PYODIDE_URL });
  pyodide.setStdout({ batched: (linha) => avisa("log", { linha }) });
  pyodide.setStderr({ batched: (linha) => avisa("log", { linha }) });

  avisa("etapa", { texto: "Instalando pandas e leitores de Excel…" });
  await pyodide.loadPackage(["pandas", "micropip"]);
  const micropip = pyodide.pyimport("micropip");
  await micropip.install(["openpyxl", "xlrd", "xlsxwriter"]);

  avisa("etapa", { texto: "Carregando o programa de análise…" });
  const FS = pyodide.FS;
  for (const caminho of ARQUIVOS_PY) {
    const resp = await fetch(caminho, { cache: "no-cache" });
    if (!resp.ok) throw new Error(`Não foi possível baixar ${caminho} (HTTP ${resp.status}).`);
    const destino = `/app/${caminho}`;
    FS.mkdirTree(destino.substring(0, destino.lastIndexOf("/")));
    FS.writeFile(destino, new Uint8Array(await resp.arrayBuffer()));
  }
  const executor = await (await fetch("executor_web.py", { cache: "no-cache" })).text();
  pyodide.runPython(executor);
  return pyodide;
}

function limpaPasta(pyodide) {
  const FS = pyodide.FS;
  try {
    for (const nome of FS.readdir(PASTA)) {
      if (nome !== "." && nome !== "..") FS.unlink(`${PASTA}/${nome}`);
    }
  } catch (e) {
    FS.mkdirTree(PASTA);
  }
}

function mensagemAmigavel(erro) {
  const texto = String(erro && erro.message ? erro.message : erro);
  const linhas = texto.trim().split("\n").filter(Boolean);
  const ultima = linhas[linhas.length - 1] || texto;
  return { resumo: ultima.replace(/^\w+(Error|Exception|Exit):\s*/, ""), detalhe: texto };
}

async function iniciaPyodide() {
  if (!pyodidePronto) {
    pyodidePronto = preparaPython().catch((e) => { pyodidePronto = null; throw e; });
  }
  return pyodidePronto;
}

// Fase 1: lê a pasta e devolve o Top 20 para o usuário conferir
async function fasePreparar(arquivos) {
  const pyodide = await iniciaPyodide();
  avisa("etapa", { texto: "Copiando os arquivos para análise…" });
  limpaPasta(pyodide);
  for (const arq of arquivos) {
    pyodide.FS.writeFile(`${PASTA}/${arq.nome}`, new Uint8Array(arq.conteudo));
  }
  avisa("etapa", { texto: "Lendo e cruzando os arquivos…" });
  const preparar = pyodide.globals.get("preparar");
  const progresso = (n, desc) => avisa("progresso", { pct: n, texto: desc });
  const json = preparar(PASTA, progresso);
  preparar.destroy();
  avisa("top20", { dados: JSON.parse(json) });
}

// Fase 2: aplica os ajustes (se houver) e gera o relatório
async function faseContinuar(ajustes) {
  const pyodide = await iniciaPyodide();
  avisa("etapa", { texto: "Processando…" });
  const continuar = pyodide.globals.get("continuar");
  const refs = continuar(JSON.stringify(ajustes || [])).toJs();
  continuar.destroy();

  const saidas = [];
  for (const nome of SAIDAS) {
    const caminho = `${PASTA}/${nome}`;
    if (pyodide.FS.analyzePath(caminho).exists) {
      const bytes = pyodide.FS.readFile(caminho);
      saidas.push({ nome, conteudo: bytes.buffer });
    }
  }
  avisa("concluido", { saidas, refAtual: refs[0], refAnterior: refs[1] },
    saidas.map((s) => s.conteudo));
}

self.onmessage = async (evento) => {
  const { fase, arquivos, ajustes } = evento.data;
  try {
    if (fase === "continuar") await faseContinuar(ajustes);
    else await fasePreparar(arquivos);
  } catch (erro) {
    avisa("erro", mensagemAmigavel(erro));
  }
};
