// Roda o pipeline Python dentro do navegador (Pyodide), fora da thread da página.
// Nada é enviado para servidor: os arquivos ficam numa pasta virtual na memória.

const PYODIDE_VERSAO = "0.29.5";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSAO}/full/`;
const PASTA = "/dados";
const SAIDAS = [
  "Relatorio_Comparativo.html",
  "Base_Compilada_HISTORICO.xlsx",
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
  await micropip.install(["openpyxl", "xlrd"]);

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

self.onmessage = async (evento) => {
  const { arquivos } = evento.data;
  try {
    if (!pyodidePronto) {
      pyodidePronto = preparaPython().catch((e) => { pyodidePronto = null; throw e; });
    }
    const pyodide = await pyodidePronto;

    avisa("etapa", { texto: "Copiando os arquivos para análise…" });
    limpaPasta(pyodide);
    for (const arq of arquivos) {
      pyodide.FS.writeFile(`${PASTA}/${arq.nome}`, new Uint8Array(arq.conteudo));
    }

    const script = await (await fetch("acompanhamento_faturamento.py", { cache: "no-cache" })).text();

    avisa("etapa", { texto: "Processando…" });
    const executar = pyodide.globals.get("executar");
    const progresso = (n, desc) => avisa("progresso", { pct: n, texto: desc });
    const refs = executar(PASTA, script, progresso).toJs();
    executar.destroy();

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
  } catch (erro) {
    avisa("erro", mensagemAmigavel(erro));
  }
};
