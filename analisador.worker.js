// Roda o pipeline Python dentro do navegador (Pyodide), fora da thread da página.
// Nada é enviado para servidor: os arquivos ficam numa pasta virtual na memória.

const PYODIDE_VERSAO = "0.29.5";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSAO}/full/`;
const PASTA = "/dados";
// Arquivos do pacote Python que o site copia para o Pyodide (caminho no site -> pasta virtual /app)
const ARQUIVOS_PY = [
  "faturamento/__init__.py", "faturamento/analises.py", "faturamento/analitico.py", "faturamento/base.py", "faturamento/cache_arquivos.py", "faturamento/comparativo.py",
  "faturamento/dre.py", "faturamento/dados.py",
  "faturamento/config.py", "faturamento/contexto.py", "faturamento/formatacao.py", "faturamento/leitura.py",
  "faturamento/origem.py", "faturamento/orcado_ciclo.py", "faturamento/previsao.py", "faturamento/projecao_grupos.py", "faturamento/validacao.py", "faturamento/painel_html.py", "faturamento/pipeline.py", "faturamento/progresso.py",
  "faturamento/relatorio.py", "faturamento/situacao_grupo.py", "faturamento/situacao_lancamento.py", "faturamento/tabelas_html.py", "faturamento/top20.py",
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
  // leitores/gravadores de Excel: primeiro do próprio Pyodide (mesmo servidor do Python); o que faltar, tenta no PyPI.
  // Falha em um deles não para a análise (redes que bloqueiam o PyPI davam "Can't fetch metadata for 'xlsxwriter'").
  const EXTRAS = ["openpyxl", "xlrd", "xlsxwriter"];
  try { await pyodide.loadPackage(EXTRAS); } catch (e) { avisa("log", { linha: "Aviso: " + e.message }); }
  const micropip = pyodide.pyimport("micropip");
  for (const pacote of EXTRAS) {
    const modulo = pacote;
    if (pyodide.runPython(`import importlib.util; importlib.util.find_spec("${modulo}") is not None`)) continue;
    try { await micropip.install(pacote); }
    catch (e) { avisa("log", { linha: `Aviso: não foi possível instalar ${pacote} (${String(e.message || e).split("\n").pop()}).` }); }
  }

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

function apagaTudo(FS, caminho) {                  // apaga arquivos e subpastas da análise anterior
  for (const nome of FS.readdir(caminho)) {
    if (nome === "." || nome === "..") continue;
    const c = `${caminho}/${nome}`;
    if (FS.isDir(FS.stat(c).mode)) { apagaTudo(FS, c); FS.rmdir(c); } else FS.unlink(c);
  }
}

function limpaPasta(pyodide) {
  const FS = pyodide.FS;
  try {
    apagaTudo(FS, PASTA);
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

// ===== Arquivos já lidos (guardados no navegador, IndexedDB) =====
// Para cada arquivo da pasta guarda o resultado já processado da leitura; na próxima análise, arquivo com o mesmo
// caminho, tamanho e data de alteração não é lido de novo (o Python recebe o resultado guardado — cache_arquivos.py).
const CACHE = "/cache";
const BANCO = "faturamento_cache";
const LIMITE_MB = 1500;                            // acima disso, apaga o que não é da pasta atual

function abreBanco() {
  return new Promise((ok, erro) => {
    const r = indexedDB.open(BANCO, 1);
    r.onupgradeneeded = () => r.result.createObjectStore("arquivos", { keyPath: "id" });
    r.onsuccess = () => ok(r.result);
    r.onerror = () => erro(r.error);
  });
}
function req(r) { return new Promise((ok, erro) => { r.onsuccess = () => ok(r.result); r.onerror = () => erro(r.error); }); }
async function bancoLe(db, id) { return req(db.transaction("arquivos").objectStore("arquivos").get(id)); }
async function bancoGrava(db, item) {
  return new Promise((ok, erro) => {
    const t = db.transaction("arquivos", "readwrite"); t.objectStore("arquivos").put(item);
    t.oncomplete = ok; t.onerror = () => erro(t.error); t.onabort = () => erro(t.error);
  });
}
async function bancoResumo(db) {                    // [{id, rel, versao, bytes}] sem carregar os dados guardados
  return new Promise((ok, erro) => {
    const itens = [], r = db.transaction("arquivos").objectStore("arquivos").openCursor();
    r.onsuccess = () => { const c = r.result; if (!c) return ok(itens); const v = c.value; itens.push({ id: v.id, rel: v.rel, versao: v.versao, bytes: v.bytes || 0 }); c.continue(); };
    r.onerror = () => erro(r.error);
  });
}
async function bancoApaga(db, ids) {
  if (!ids.length) return;
  return new Promise((ok, erro) => {
    const t = db.transaction("arquivos", "readwrite"), st = t.objectStore("arquivos");
    ids.forEach((id) => st.delete(id));
    t.oncomplete = ok; t.onerror = () => erro(t.error);
  });
}

async function idArquivo(chave) {                   // id curto e seguro para nome de pasta
  try {
    const h = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(chave));
    return Array.from(new Uint8Array(h)).map((b) => b.toString(16).padStart(2, "0")).join("");
  } catch (e) {                                     // sem crypto.subtle (página aberta como arquivo): hash simples
    let h1 = 0x811c9dc5, h2 = 0x01000193;
    for (let i = 0; i < chave.length; i++) { h1 = Math.imul(h1 ^ chave.charCodeAt(i), 16777619); h2 = Math.imul(h2 + chave.charCodeAt(i), 2246822519); }
    return (h1 >>> 0).toString(16) + (h2 >>> 0).toString(16) + chave.length.toString(16);
  }
}

function limpaDir(FS, caminho) {
  try { apagaTudo(FS, caminho); } catch (e) { /* não existia */ }
  FS.mkdirTree(caminho);
}

// Fase 1: lê a pasta e devolve o Top 20 para o usuário conferir
async function fasePreparar(arquivos) {
  const pyodide = await iniciaPyodide();
  const FS = pyodide.FS;
  avisa("etapa", { texto: "Copiando os arquivos para análise…" });
  limpaPasta(pyodide);
  limpaDir(FS, CACHE);
  limpaDir(FS, `${CACHE}/entrada`);
  const versao = pyodide.runPython("from faturamento.cache_arquivos import VERSAO\nVERSAO");
  let db = null;
  try { db = await abreBanco(); } catch (e) { avisa("log", { linha: "Aviso: sem acesso ao armazenamento do navegador; todos os arquivos serão lidos." }); }
  const meta = {}, atuais = new Set();
  let reaproveitados = 0;
  for (const arq of arquivos) {
    const partes = arq.nome.split("/").filter((p) => p && p !== "." && p !== "..");   // mantém as subpastas
    const rel = partes.join("/");
    if (partes.length > 1) FS.mkdirTree(`${PASTA}/${partes.slice(0, -1).join("/")}`);
    const tamanho = arq.tamanho != null ? arq.tamanho : (arq.conteudo ? arq.conteudo.byteLength : 0);
    const id = await idArquivo(`${versao}|${rel}|${tamanho}|${arq.modificado || 0}`);
    atuais.add(id);
    let guardado = null;
    if (db && arq.modificado) { try { guardado = await bancoLe(db, id); } catch (e) { guardado = null; } }
    if (guardado && guardado.versao === versao && guardado.etapas) {
      FS.writeFile(`${PASTA}/${rel}`, new Uint8Array(0));        // o arquivo nem é lido: o Python usa o resultado guardado
      FS.mkdirTree(`${CACHE}/entrada/${id}`);
      for (const [etapa, bytes] of Object.entries(guardado.etapas)) FS.writeFile(`${CACHE}/entrada/${id}/${etapa}`, bytes);
      meta[rel] = { id, tamanho, em_cache: true };
      reaproveitados++;
    } else {
      const conteudo = arq.conteudo || await arq.arquivo.arrayBuffer();
      FS.writeFile(`${PASTA}/${rel}`, new Uint8Array(conteudo));
      meta[rel] = { id, tamanho, em_cache: false, modificado: arq.modificado || 0 };
    }
  }
  FS.writeFile(`${CACHE}/meta.json`, JSON.stringify({ versao, arquivos: meta }));
  avisa("etapa", { texto: reaproveitados ? `Lendo os arquivos novos (${reaproveitados} já lidos antes)…` : "Lendo e cruzando os arquivos…" });
  const preparar = pyodide.globals.get("preparar");
  const progresso = (n, desc) => avisa("progresso", { pct: n, texto: desc });
  const json = preparar(PASTA, progresso);
  preparar.destroy();
  const dados = JSON.parse(json);
  if (db) {
    try { dados.leitura = Object.assign(dados.leitura || {}, await guardaLeituras(FS, db, meta, versao, atuais)); }
    catch (e) { avisa("log", { linha: "Aviso: não foi possível guardar os arquivos lidos para a próxima vez (" + e.message + ")." }); }
  }
  avisa("top20", { dados });
}

// Guarda no navegador o que o Python leu agora (CACHE/saida/<id>/) e tira o que ficou velho
async function guardaLeituras(FS, db, meta, versao, atuais) {
  const saida = `${CACHE}/saida`;
  const porId = {};
  Object.entries(meta).forEach(([rel, m]) => { porId[m.id] = rel; });
  if (FS.analyzePath(saida).exists) {
    for (const id of FS.readdir(saida)) {
      if (id === "." || id === "..") continue;
      const etapas = {}; let bytes = 0;
      for (const etapa of FS.readdir(`${saida}/${id}`)) {
        if (etapa === "." || etapa === "..") continue;
        etapas[etapa] = FS.readFile(`${saida}/${id}/${etapa}`);
        bytes += etapas[etapa].byteLength;
      }
      if (porId[id] && Object.keys(etapas).length) await bancoGrava(db, { id, rel: porId[id], versao, etapas, bytes, guardado: Date.now() });
    }
  }
  // tira: outra versão do programa; mesmo arquivo (caminho) com outro conteúdo; e, acima do limite, o que não é desta pasta
  const itens = await bancoResumo(db);
  const relsAtuais = new Set(Object.keys(meta));
  let apagar = itens.filter((i) => i.versao !== versao || (relsAtuais.has(i.rel) && !atuais.has(i.id))).map((i) => i.id);
  const restantes = itens.filter((i) => !apagar.includes(i.id));
  let total = restantes.reduce((a, i) => a + i.bytes, 0);
  if (total > LIMITE_MB * 1e6) {
    const fora = restantes.filter((i) => !atuais.has(i.id));
    apagar = apagar.concat(fora.map((i) => i.id));
    total -= fora.reduce((a, i) => a + i.bytes, 0);
  }
  await bancoApaga(db, apagar);
  return { guardadoMB: Math.round(total / 1e5) / 10 };
}

async function limpaCache() {
  await new Promise((ok) => { const r = indexedDB.deleteDatabase(BANCO); r.onsuccess = r.onerror = r.onblocked = () => ok(); });
  avisa("cacheLimpo", {});
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
    if (fase === "limparCache") { await limpaCache(); return; }
    if (fase === "continuar") await faseContinuar(ajustes);
    else await fasePreparar(arquivos);
  } catch (erro) {
    avisa("erro", mensagemAmigavel(erro));
  }
};
