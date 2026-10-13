// Estrutura tarifária: valor (R$) de um consumo (m³) — a mesma regra da fórmula da planilha da Análise de Garantia.
//  - mínimo da ligação = mínimo da categoria × economias de cada tipo (Residencial/Social, Comercial/Peq. Comércio,
//    Industrial, Pública/Pub. Estadual); o que passa da soma dos mínimos é repartido igualmente entre as economias;
//  - cada tipo é cobrado pelas faixas da categoria (faixa × nº de economias), na tarifa progressiva quando passa do
//    mínimo; com esgoto, o valor dobra (água + esgoto).
// Usado no relatório (aba Garantia) e no site (etapa 2). tab = { faixas: [[categoria, ini, fim, normal, progressiva]], minimos: {categoria: m³} }
(function (raiz) {
  const norm = (s) => String(s == null ? '' : s).normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/\s+/g, ' ').trim();
  function minimoDe(tab, cat) {
    const c = norm(cat) === 'PUB. ESTADUAL' ? 'PUBLICA' : norm(cat);
    const k = Object.keys(tab.minimos || {}).find((x) => norm(x) === c);
    return k === undefined ? 0 : +tab.minimos[k] || 0;
  }
  function rotulos(categoria) {
    const c = norm(categoria);
    return {
      res: (c === 'RESIDENCIAL' || c === 'SOCIAL') ? c : 'RESIDENCIAL',
      com: (c === 'COMERCIAL' || c === 'PEQ. COMERCIO') ? c : 'COMERCIAL',
      ind: 'INDUSTRIAL',
      pub: (c === 'PUBLICA' || c === 'PUB. ESTADUAL') ? c : 'PUBLICA',
    };
  }
  function valorCategoria(tab, cat, qty, total) {
    if (!qty || !total) return 0;
    const progressivo = total > minimoDe(tab, cat) * qty;
    let soma = 0;
    (tab.faixas || []).forEach(([c, ini, fim, normal, prog]) => {
      if (norm(c) !== norm(cat)) return;
      const limInf = Math.max(+ini - 1, 0) * qty, limSup = +fim * qty;
      const vol = Math.max((total < limSup ? total : limSup) - limInf, 0);
      soma += vol * (progressivo ? +prog : +normal);
    });
    return soma;
  }
  const qtds = (eco) => ({ res: +(eco && eco.res) || 0, com: +(eco && eco.com) || 0, ind: +(eco && eco.ind) || 0, pub: +(eco && eco.pub) || 0 });
  // mínimo da ligação (m³): soma dos mínimos de cada tipo de economia
  function minimo(tab, categoria, eco) {
    const r = rotulos(categoria), q = qtds(eco);
    return ['res', 'com', 'ind', 'pub'].reduce((s, k) => s + (q[k] > 0 ? minimoDe(tab, r[k]) * q[k] : 0), 0);
  }
  function valor(tab, media, categoria, eco, esgoto) {
    if (media === null || media === undefined || media === '' || isNaN(+media) || !tab) return null;
    media = +media;
    const r = rotulos(categoria), q = qtds(eco), totalEco = q.res + q.com + q.ind + q.pub;
    const mins = {}; ['res', 'com', 'ind', 'pub'].forEach((k) => { mins[k] = minimoDe(tab, r[k]) * q[k]; });
    const soma = ['res', 'com', 'ind', 'pub'].reduce((s, k) => s + (q[k] > 0 ? mins[k] : 0), 0);
    const extra = totalEco ? (media > soma ? media - soma : 0) / totalEco : 0;
    const tot = (k) => (q[k] ? mins[k] + extra * q[k] : 0);
    const v = ['res', 'com', 'ind', 'pub'].reduce((s, k) => s + valorCategoria(tab, r[k], q[k], tot(k)), 0);
    return v * (esgoto ? 2 : 1);
  }
  raiz.Tarifa = { valor, minimo, norm };
})(typeof window !== 'undefined' ? window : globalThis);
