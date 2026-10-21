const CHAVE_JUSTIFICATIVA = '__CHAVE_JUSTIFICATIVA__';

const VIEWS = ['resumo', 'tabelas', 'analise', 'indiretas', 'forecast', 'dre', 'garantia', 'plano', 'onepage', 'dados'];
function mostrarView(view) {
    VIEWS.forEach(v => {
        document.getElementById('view-' + v).classList.toggle('ativo', v === view);
        document.getElementById('view-' + v).style.display = (v === view) ? 'block' : 'none';
        document.getElementById('btn-' + v).classList.toggle('active', v === view);
    });
    const seletor = document.getElementById('seletorSup');
    if (seletor) seletor.hidden = !(view === 'dre' || view === 'indiretas' || view === 'forecast');
    if (view === 'onepage' && typeof opDesenhar === 'function') opDesenhar();
}

// Filtros da DRE/Indiretas: superintendência, mês e referência (RF / SUP / ambos)
const ESTADO = { sup: 'TODAS', mes: null, ref: null };
function definirFiltros(parcial) {
    Object.assign(ESTADO, parcial || {});
    document.querySelectorAll('.sup-bloco').forEach(b => {
        b.style.display = (b.dataset.sup === ESTADO.sup && b.dataset.mes === ESTADO.mes) ? 'block' : 'none';
    });
    document.querySelectorAll('.prev-bloco, .sup-top-bloco').forEach(b => { b.style.display = (b.dataset.sup === ESTADO.sup) ? 'block' : 'none'; });
    // Destaques do mês: um quadro por SUP; em "Todas" aparecem todos
    document.querySelectorAll('.sup-dest').forEach(b => { b.style.display = (ESTADO.sup === 'TODAS' || b.dataset.sup === ESTADO.sup) ? '' : 'none'; });
    // Downloads (Excel) por superintendência: só o botão da SUP escolhida aparece
    document.querySelectorAll('.sup-dl').forEach(b => { b.style.display = (b.dataset.sup === ESTADO.sup) ? '' : 'none'; });
    // Aba Dados, memória do Forecast: acompanha a SUP do cabeçalho (o seletor próprio continua funcionando)
    document.querySelectorAll('.fc-seletor select').forEach(sel => {
        if (!Array.from(sel.options).some(o => o.value === ESTADO.sup)) return;
        sel.value = ESTADO.sup;
        sel.closest('.val-bloco').querySelectorAll('.fc-sup').forEach(b => { b.hidden = b.dataset.fcSup !== ESTADO.sup; });
    });
    aplicarSupNosGrupos();
    aplicarFontes();
    cortRecalcular();
    [['selSup', ESTADO.sup], ['selMes', ESTADO.mes], ['selRef', ESTADO.ref]].forEach(([id, v]) => {
        const el = document.getElementById(id); if (el && v) el.value = v;
    });
    desenharGraficosIndiretas();
    if (typeof garRedesenhar === 'function') garRedesenhar();
    if (typeof planoDesenhar === 'function') planoDesenhar();
    if (typeof opDesenhar === 'function') opDesenhar();
}

// Superintendência nas abas por grupo (Resumo e Diretas): marca só os grupos da SUP escolhida (pela Localidade do cronograma)
let supGruposAplicada = null;
function aplicarSupNosGrupos() {
    if (ESTADO.sup === supGruposAplicada) return;           // só quando a SUP muda: não desfaz a escolha manual de grupos
    supGruposAplicada = ESTADO.sup;
    let mapa = {};
    try { mapa = JSON.parse(document.getElementById('info-filtros').textContent).grupoSup || {}; } catch (e) { /* sem mapa */ }
    const caixas = Array.from(document.querySelectorAll('.chk-grupo'));
    const daSup = (c) => ESTADO.sup === 'TODAS' || mapa[c.value] === ESTADO.sup;
    const algum = caixas.some(daSup);                       // SUP sem grupo conhecido: não esconde tudo
    let padrao = null;                                      // ainda no padrão: só os Liberados e Em Análise ficam marcados
    try { if (window.gruposAuto) padrao = gruposPadrao(); } catch (e) { padrao = null; }
    caixas.forEach(c => {
        const ok = !algum || daSup(c);
        c.checked = ok && (!padrao || padrao.has(normGrupo(c.value)));
        const rotulo = c.closest('label'); if (rotulo) rotulo.style.display = ok ? '' : 'none';
    });
    if (typeof filtrarPorGrupo === 'function' && document.getElementById('badgeFiltro')) filtrarPorGrupo();
}

// Referência = planilhas de orçado mostradas (ex.: "RF01T26|RF SUP" mostra as duas e a diferença entre elas)
function aplicarFontes() {
    const ref = ESTADO.ref || '';
    const soOrcados = ref.startsWith('cmp:');                 // compara RF com RF SUP, sem o realizado
    const chave = soOrcados ? ref.slice(4) : ref;
    const sel = chave.split('|').filter(Boolean);
    document.querySelectorAll('[data-src]').forEach(el => {
        const mostra = (!sel.length || sel.includes(el.dataset.src)) && !(soOrcados && el.dataset.tipo === 'dreal');
        el.style.display = mostra ? '' : 'none';
    });
    document.querySelectorAll('[data-real]').forEach(el => { el.style.display = soOrcados ? 'none' : ''; });
    document.querySelectorAll('[data-combo]').forEach(el => {
        el.style.display = (sel.length === 2 && el.dataset.combo.split('|').every(x => sel.includes(x))) ? '' : 'none';
    });
}

// Diretas: as tabelas de orçado por ciclo mostram só a planilha escolhida no seletor (Água e Esgoto)
function selecionarOrcadoCiclo(fonte) {
    document.querySelectorAll('.orc-ciclo-bloco').forEach(b => { b.hidden = b.dataset.orcCiclo !== fonte; });
    const sel = document.getElementById('selOrcCiclo'); if (sel && sel.value !== fonte) sel.value = fonte;
    configAlterada();
}

const CORES_CLASSES = ['#176b9c', '#16a5b8', '#1f8a70', '#d79b29', '#c94b4b', '#6b7a99'];
const fmtCompacto = v => v >= 1e6 ? (v / 1e6).toFixed(1).replace('.', ',') + ' mi' : v >= 1e3 ? (v / 1e3).toFixed(1).replace('.', ',').replace(',0', '') + ' mil' : Math.round(v).toLocaleString('pt-BR');

// Rótulos do gráfico de indiretas: valor dentro de cada faixa (se couber) e o total em cima da barra
const plugRotulosIndiretas = {
    id: 'rotulosIndiretas',
    afterDatasetsDraw(chart) {
        const { ctx } = chart; ctx.save(); ctx.textAlign = 'center';
        const n = chart.data.labels.length;
        for (let i = 0; i < n; i++) {
            let total = 0, topo = null, x = null;
            chart.data.datasets.forEach((ds, k) => {
                const barra = chart.getDatasetMeta(k).data[i], v = ds.data[i];
                total += v; x = barra.x;
                if (topo === null || barra.y < topo) topo = barra.y;
                if (v > 0 && Math.abs(barra.base - barra.y) >= 18) {
                    ctx.fillStyle = '#fff'; ctx.font = "600 11px 'Segoe UI', Arial, sans-serif"; ctx.textBaseline = 'middle';
                    ctx.fillText(fmtCompacto(v), barra.x, (barra.y + barra.base) / 2);
                }
            });
            ctx.fillStyle = '#102840'; ctx.font = "700 12px 'Segoe UI', Arial, sans-serif"; ctx.textBaseline = 'bottom';
            ctx.fillText('R$ ' + total.toLocaleString('pt-BR', { maximumFractionDigits: 0 }), x, topo - 6);
        }
        ctx.restore();
    }
};

function desenharGraficosIndiretas() {
    document.querySelectorAll('.sup-bloco').forEach(bloco => {
        if (bloco.style.display === 'none') return;
        bloco.querySelectorAll('canvas.canvas-indiretas').forEach(cv => {
            if (cv.dataset.pronto) return;
            if (typeof Chart === 'undefined') { cv.parentElement.style.display = 'none'; return; }
            const d = JSON.parse(cv.dataset.dados);
            cv.dataset.pronto = '1';
            new Chart(cv, {
                type: 'bar',
                plugins: [plugRotulosIndiretas],
                data: { labels: d.meses, datasets: d.series.map((s, i) => ({ label: s.classe, data: s.valores, backgroundColor: CORES_CLASSES[i % CORES_CLASSES.length], maxBarThickness: 110, borderWidth: 1, borderColor: '#fff' })) },
                options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 26 } },
                    scales: { x: { stacked: true, grid: { display: false } },
                              y: { stacked: true, beginAtZero: true, grid: { color: '#e8eef3' }, ticks: { callback: v => fmtCompacto(v) } } },
                    plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, pointStyle: 'rect', boxWidth: 10 } },
                               tooltip: { callbacks: { label: c => c.dataset.label + ': R$ ' + c.parsed.y.toLocaleString('pt-BR') } } } }
            });
        });
    });
}

// Tabelas longas (Top 100): mostra as primeiras linhas e um botão para ver todas
function recolherTabelasLongas() {
    document.querySelectorAll('table[class^="tabela-top100-"]').forEach(tabela => {
        const linhas = Array.from(tabela.querySelectorAll('tbody tr')), limite = 15;
        if (linhas.length <= limite || tabela.dataset.recolhido) return;
        tabela.dataset.recolhido = '1';
        const esconder = (sim) => linhas.forEach((tr, i) => { if (i >= limite) tr.style.display = sim ? 'none' : ''; });
        esconder(true);
        const botao = document.createElement('button');
        botao.type = 'button'; botao.className = 'btn-just btn-ver-todos'; botao.textContent = `Mostrar todos (${linhas.length})`;
        let aberto = false;
        botao.onclick = () => { aberto = !aberto; esconder(!aberto); botao.textContent = aberto ? `Mostrar só os ${limite} primeiros` : `Mostrar todos (${linhas.length})`; };
        (tabela.closest('.tabela-wrap') || tabela).insertAdjacentElement('afterend', botao);
    });
}

function toggleFiltro(event) {
    event.stopPropagation();
    document.getElementById('painelFiltro').classList.toggle('aberto');
}

document.addEventListener('click', function (e) {
    const painel = document.getElementById('painelFiltro');
    const botao = document.getElementById('btnFiltro');
    if (painel && !painel.contains(e.target) && (!botao || !botao.contains(e.target))) {
        painel.classList.remove('aberto');
    }
});

function marcarTodos(valor) {
    document.querySelectorAll('.chk-grupo').forEach(c => c.checked = valor);
    filtrarPorGrupo();
}

function envolverTabelasComScroll() {
    document.querySelectorAll('table').forEach(function (tabela) {
        if (tabela.id === 'tabela-dados-resumo') return;
        const pai = tabela.parentElement;
        if (pai && pai.classList.contains('tabela-wrap')) return;
        const wrap = document.createElement('div');
        wrap.className = 'tabela-wrap';
        pai.insertBefore(wrap, tabela);
        wrap.appendChild(tabela);
    });
}

function habilitarScrollTabelas() {
    document.querySelectorAll('.tabela-wrap').forEach(function (wrap) {
        if (wrap.dataset.scrollHabilitado) return;
        wrap.dataset.scrollHabilitado = "true";
        let isDown = false, startX, scrollLeft;
        wrap.addEventListener('mousedown', function (e) {
            isDown = true; wrap.classList.add('grabbing');
            startX = e.pageX - wrap.offsetLeft; scrollLeft = wrap.scrollLeft;
        });
        wrap.addEventListener('mouseleave', function () { isDown = false; wrap.classList.remove('grabbing'); });
        wrap.addEventListener('mouseup', function () { isDown = false; wrap.classList.remove('grabbing'); });
        wrap.addEventListener('mousemove', function (e) {
            if (!isDown) return;
            e.preventDefault();
            const x = e.pageX - wrap.offsetLeft;
            const walk = (x - startX) * 1.5;
            wrap.scrollLeft = scrollLeft - walk;
        });
        // sem tratamento de roda do mouse: a página continua rolando normalmente sobre a tabela (Shift+roda rola de lado)
    });
}

function filtrarPorGrupo() {
    const marcados = Array.from(document.querySelectorAll('.chk-grupo:checked')).map(c => c.value);
    document.getElementById('badgeFiltro').innerText = marcados.length;
    document.querySelectorAll('tr[data-grupo]').forEach(function (tr) {
        const grupo = tr.getAttribute('data-grupo');
        if (grupo === '') return;
        tr.style.display = marcados.includes(grupo) ? '' : 'none';
    });
    recalcularTotais();
    recalcularTotalAtivaCortada();
    recalcularMatrizGrupos();
    recalcularTabelaMinimo();
    recalcularKPIsResumo();
    refazTops();                                            // Top 100 refeito só com os grupos marcados
    sitlRecalcular();                                       // cards da Situação de lançamento
    cortRecalcular();                                       // cortadas com consumo
    if (typeof garRedesenhar === 'function') garRedesenhar();   // aba Garantia (Top 1000, análise e resumo)
    if (typeof planoDesenhar === 'function') planoDesenhar();   // aba Plano de ação
    if (typeof opDesenhar === 'function') opDesenhar();         // aba One page
}

function recalcularTotais() {
    document.querySelectorAll('table.tabela-comparativo').forEach(function (tabela) {
        const marcados = Array.from(document.querySelectorAll('.chk-grupo:checked')).map(c => c.value);
        let fatAt=0, fatAnt=0, ecoAt=0, ecoAnt=0, volAt=0, volAnt=0, diasAtSoma=0, diasAntSoma=0, diasAtN=0, diasAntN=0;
        tabela.querySelectorAll('tbody tr[data-grupo]').forEach(function (tr) {
            const grupo = tr.getAttribute('data-grupo');
            if (grupo === '' || !marcados.includes(grupo)) return;
            fatAt += parseFloat(tr.getAttribute('data-fat-atual')) || 0;
            fatAnt += parseFloat(tr.getAttribute('data-fat-anterior')) || 0;
            ecoAt += parseFloat(tr.getAttribute('data-eco-atual')) || 0;
            ecoAnt += parseFloat(tr.getAttribute('data-eco-anterior')) || 0;
            volAt += parseFloat(tr.getAttribute('data-vol-atual')) || 0;
            volAnt += parseFloat(tr.getAttribute('data-vol-anterior')) || 0;
            // dias 0 = grupo sem leitura naquele mês: fica fora da média
            const dAt = parseFloat(tr.getAttribute('data-dias-atual')) || 0, dAnt = parseFloat(tr.getAttribute('data-dias-anterior')) || 0;
            if (dAt > 0) { diasAtSoma += dAt; diasAtN++; }
            if (dAnt > 0) { diasAntSoma += dAnt; diasAntN++; }
        });
        const linhaTotal = tabela.querySelector('tbody tr.linha-media');
        if (!linhaTotal) return;
        const vmAt = ecoAt ? volAt / ecoAt : 0;
        const vmAnt = ecoAnt ? volAnt / ecoAnt : 0;
        const tarAt = volAt ? fatAt / volAt : 0;
        const tarAnt = volAnt ? fatAnt / volAnt : 0;
        const ticAt = ecoAt ? fatAt / ecoAt : 0;
        const ticAnt = ecoAnt ? fatAnt / ecoAnt : 0;
        const diasAt = diasAtN ? diasAtSoma / diasAtN : 0;
        const diasAnt = diasAntN ? diasAntSoma / diasAntN : 0;

        function fmt(v, dec) {
            dec = dec || 0;
            return v.toLocaleString('pt-BR', { minimumFractionDigits: dec, maximumFractionDigits: dec });
        }
        function setCell(campo, valor, dec) {
            const el = linhaTotal.querySelector('[data-field="' + campo + '"]');
            if (el) el.innerText = fmt(valor, dec);
        }
        function setDelta(campo, valor, pct, dec) {
            const el = linhaTotal.querySelector('[data-field="' + campo + '"]');
            if (!el) return;
            const cor = valor < 0 ? '#C2560C' : '#05050D';
            el.style.color = cor;
            el.innerText = pct ? (valor * 100).toFixed(1).replace('.', ',') + '%' : fmt(valor, dec || 0);
        }

        setCell('dias-atual', diasAt, 1);
        setCell('dias-anterior', diasAnt, 1);
        setCell('fat-atual', fatAt);
        setCell('fat-anterior', fatAnt);
        setDelta('delta-fat', fatAt - fatAnt);
        setDelta('delta-pct-fat', fatAnt ? (fatAt - fatAnt) / fatAnt : 0, true);
        setCell('eco-atual', ecoAt);
        setCell('eco-anterior', ecoAnt);
        setDelta('delta-pct-eco', ecoAnt ? (ecoAt - ecoAnt) / ecoAnt : 0, true);
        setDelta('delta-eco', ecoAt - ecoAnt);
        setCell('vol-atual', volAt);
        setCell('vol-anterior', volAnt);
        setDelta('delta-pct-vol', volAnt ? (volAt - volAnt) / volAnt : 0, true);
        setDelta('delta-vol', volAt - volAnt);
        setCell('vm-atual', vmAt, 2);
        setCell('vm-anterior', vmAnt, 2);
        setDelta('delta-vm', vmAt - vmAnt, false, 2);
        setDelta('delta-pct-vm', vmAnt ? (vmAt - vmAnt) / vmAnt : 0, true);
        setCell('tar-atual', tarAt, 2);
        setCell('tar-anterior', tarAnt, 2);
        setDelta('delta-tar', tarAt - tarAnt, false, 2);
        setDelta('delta-pct-tar', tarAnt ? (tarAt - tarAnt) / tarAnt : 0, true);
        setCell('tic-atual', ticAt, 2);
        setCell('tic-anterior', ticAnt, 2);
        setDelta('delta-tic', ticAt - ticAnt, false, 2);
        setDelta('delta-pct-tic', ticAnt ? (ticAt - ticAnt) / ticAnt : 0, true);
    });
}

function recalcularTotalAtivaCortada() { document.querySelectorAll('table.tabela-ativa-cortada').forEach(recalcAtivaCortadaTabela); }   // versões "todas" e "só esgoto"
function recalcAtivaCortadaTabela(tabela) {
    const marcados = Array.from(document.querySelectorAll('.chk-grupo:checked')).map(c => c.value);
    let ativaAt=0, ativaAnt=0, cortAt=0, cortAnt=0;
    tabela.querySelectorAll('tr[data-grupo]').forEach(function (tr) {
        const grupo = tr.getAttribute('data-grupo');
        if (grupo === '' || !marcados.includes(grupo)) return;
        ativaAt += parseFloat(tr.getAttribute('data-ativa-atual')) || 0;
        ativaAnt += parseFloat(tr.getAttribute('data-ativa-anterior')) || 0;
        cortAt += parseFloat(tr.getAttribute('data-cortada-atual')) || 0;
        cortAnt += parseFloat(tr.getAttribute('data-cortada-anterior')) || 0;
    });
    function fmt(v) { return v.toLocaleString('pt-BR'); }
    const linhaTotal = tabela.querySelector('tr.linha-total');
    if (!linhaTotal) return;
    linhaTotal.querySelector('[data-field="ativa-atual"]').innerText = fmt(ativaAt);
    linhaTotal.querySelector('[data-field="ativa-anterior"]').innerText = fmt(ativaAnt);
    linhaTotal.querySelector('[data-field="cortada-atual"]').innerText = fmt(cortAt);
    linhaTotal.querySelector('[data-field="cortada-anterior"]').innerText = fmt(cortAnt);
    const deltaAtiva = ativaAt - ativaAnt;
    const deltaCort = cortAt - cortAnt;
    const elAtiva = linhaTotal.querySelector('[data-field="delta-ativa"]');
    const elCort = linhaTotal.querySelector('[data-field="delta-cortada"]');
    elAtiva.innerText = fmt(deltaAtiva);
    elAtiva.style.color = deltaAtiva < 0 ? '#C2560C' : '#05050D';
    elCort.innerText = fmt(deltaCort);
    elCort.style.color = deltaCort < 0 ? '#C2560C' : '#05050D';
}

function recalcularTabelaMinimo() { document.querySelectorAll('table.tabela-min-consumo').forEach(recalcMinimoTabela); }   // versões "todas" e "só esgoto"
function recalcMinimoTabela(tabela) {
    const marcados = Array.from(document.querySelectorAll('.chk-grupo:checked')).map(c => c.value);
    let acimaAt=0, acimaAnt=0, abaixoAt=0, abaixoAnt=0;
    tabela.querySelectorAll('tr[data-grupo]').forEach(function (tr) {
        const grupo = tr.getAttribute('data-grupo');
        if (grupo === '' || !marcados.includes(grupo)) return;
        acimaAt += parseFloat(tr.getAttribute('data-acima-atual')) || 0;
        acimaAnt += parseFloat(tr.getAttribute('data-acima-anterior')) || 0;
        abaixoAt += parseFloat(tr.getAttribute('data-abaixo-atual')) || 0;
        abaixoAnt += parseFloat(tr.getAttribute('data-abaixo-anterior')) || 0;
    });
    function fmt(v) { return v.toLocaleString('pt-BR'); }
    const linhaTotal = tabela.querySelector('tr.linha-total');
    if (!linhaTotal) return;
    linhaTotal.querySelector('[data-field="acima-atual"]').innerText = fmt(acimaAt);
    linhaTotal.querySelector('[data-field="acima-anterior"]').innerText = fmt(acimaAnt);
    linhaTotal.querySelector('[data-field="abaixo-atual"]').innerText = fmt(abaixoAt);
    linhaTotal.querySelector('[data-field="abaixo-anterior"]').innerText = fmt(abaixoAnt);
    const deltaAcima = acimaAt - acimaAnt;
    const deltaAbaixo = abaixoAt - abaixoAnt;
    const elAcima = linhaTotal.querySelector('[data-field="delta-acima"]');
    const elAbaixo = linhaTotal.querySelector('[data-field="delta-abaixo"]');
    elAcima.innerText = fmt(deltaAcima);
    elAcima.style.color = deltaAcima < 0 ? '#C2560C' : '#1A2740';
    elAbaixo.innerText = fmt(deltaAbaixo);
    elAbaixo.style.color = deltaAbaixo > 0 ? '#C2560C' : '#1A2740';
}

function recalcularMatrizGrupos() { document.querySelectorAll('table.tabela-matriz-grupo').forEach(recalcMatrizTabela); }   // versões "todas" e "só esgoto"
function recalcMatrizTabela(tabela) {
    const marcados = Array.from(document.querySelectorAll('.chk-grupo:checked')).map(c => c.value);
    let totalGeral = 0;
    const totalPorColuna = {};
    tabela.querySelectorAll('tbody tr[data-grupo]').forEach(function (tr) {
        const grupoOrigem = tr.getAttribute('data-grupo');
        const visivel = marcados.includes(grupoOrigem) || grupoOrigem === '';
        tr.style.display = visivel ? '' : 'none';
        let totalLinha = 0;
        tr.querySelectorAll('td[data-destino]').forEach(function (td) {
            const destino = td.getAttribute('data-destino');
            const valor = parseFloat(td.getAttribute('data-valor')) || 0;
            if (!marcados.includes(destino) && destino !== 'Sem Faturamento Atual') return;
            if (!visivel) return;
            totalLinha += valor;
            totalPorColuna[destino] = (totalPorColuna[destino] || 0) + valor;
            totalGeral += valor;
        });
        const elTotalLinha = tr.querySelector('[data-field="total-linha"]');
        if (elTotalLinha) elTotalLinha.innerText = totalLinha.toLocaleString('pt-BR');
    });
    tabela.querySelectorAll('[data-field="total-coluna"]').forEach(function (td) {
        const destino = td.getAttribute('data-destino');
        const valor = totalPorColuna[destino] || 0;
        td.innerText = valor.toLocaleString('pt-BR');
    });
    const elTotalGeral = tabela.querySelector('[data-field="total-geral"]');
    if (elTotalGeral) elTotalGeral.innerText = totalGeral.toLocaleString('pt-BR');
}

function recalcularKPIsResumo() {
    const marcados = Array.from(document.querySelectorAll('.chk-grupo:checked')).map(c => c.value);
    const tabelaResumo = document.getElementById('tabela-dados-resumo');
    if (!tabelaResumo) return;
    let fatAt=0, fatAnt=0, ecoAt=0, ecoAnt=0, volFatAt=0, volFatAnt=0, acimaAt=0, acimaAnt=0;
    let fatAguaAt=0, fatAguaAnt=0, fatEsgotoAt=0, fatEsgotoAnt=0, diasAt=0, diasAnt=0, diasAtN=0, diasAntN=0;
    tabelaResumo.querySelectorAll('tr[data-grupo]').forEach(function (tr) {
        const grupo = tr.getAttribute('data-grupo');
        if (!marcados.includes(grupo)) return;
        const dAt = parseFloat(tr.getAttribute('data-dias-atual')) || 0, dAnt = parseFloat(tr.getAttribute('data-dias-anterior')) || 0;
        if (dAt > 0) { diasAt += dAt; diasAtN++; }               // grupo sem leitura no mês não entra na média
        if (dAnt > 0) { diasAnt += dAnt; diasAntN++; }
        fatAt += parseFloat(tr.getAttribute('data-fat-atual')) || 0;
        fatAnt += parseFloat(tr.getAttribute('data-fat-anterior')) || 0;
        ecoAt += parseFloat(tr.getAttribute('data-eco-atual')) || 0;
        ecoAnt += parseFloat(tr.getAttribute('data-eco-anterior')) || 0;
        volFatAt += parseFloat(tr.getAttribute('data-volfat-atual')) || 0;
        volFatAnt += parseFloat(tr.getAttribute('data-volfat-anterior')) || 0;
        acimaAt += parseFloat(tr.getAttribute('data-acima-atual')) || 0;
        acimaAnt += parseFloat(tr.getAttribute('data-acima-anterior')) || 0;
        fatAguaAt += parseFloat(tr.getAttribute('data-fatagua-atual')) || 0;
        fatAguaAnt += parseFloat(tr.getAttribute('data-fatagua-anterior')) || 0;
        fatEsgotoAt += parseFloat(tr.getAttribute('data-fatesgoto-atual')) || 0;
        fatEsgotoAnt += parseFloat(tr.getAttribute('data-fatesgoto-anterior')) || 0;
    });
    // Card "Dias de leitura (média)": só os grupos marcados (segue o filtro de grupos e de Superintendência)
    const mDiasAt = diasAtN ? diasAt / diasAtN : 0, mDiasAnt = diasAntN ? diasAnt / diasAntN : 0;
    const fmtDias = v => v.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const elDAt = document.querySelector('[data-field="dias-media-atual"]');
    if (elDAt) {
        elDAt.innerText = fmtDias(mDiasAt);
        document.querySelector('[data-field="dias-media-anterior"]').innerText = fmtDias(mDiasAnt);
        const elDelta = document.querySelector('[data-field="dias-media-delta"]');
        elDelta.innerText = 'Δ ' + fmtDias(mDiasAt - mDiasAnt) + ' dias';
        elDelta.style.color = (mDiasAt - mDiasAnt) < 0 ? '#C2560C' : '#1A2740';
    }
    const tarifaAt = volFatAt ? fatAt / volFatAt : 0;
    const tarifaAnt = volFatAnt ? fatAnt / volFatAnt : 0;
    const vmAt = ecoAt ? volFatAt / ecoAt : 0;
    const vmAnt = ecoAnt ? volFatAnt / ecoAnt : 0;
    const ticketAt = ecoAt ? fatAt / ecoAt : 0;
    const ticketAnt = ecoAnt ? fatAnt / ecoAnt : 0;

    function fmtNum(v, dec) {
        dec = dec || 0;
        return v.toLocaleString('pt-BR', { minimumFractionDigits: dec, maximumFractionDigits: dec });
    }
    function fmtMoeda(v) { return 'R$ ' + fmtNum(v, 2); }

    function setKpi(field, valorAtual, valorAnterior, opcoes) {
        opcoes = opcoes || {};
        const dec = opcoes.dec || 0;
        const sufixo = opcoes.sufixo || '';
        const moeda = opcoes.moeda || false;
        const elValor = document.querySelector('[data-field="' + field + '-valor"]');
        const elDelta = document.querySelector('[data-field="' + field + '-delta"]');
        if (!elValor) return;
        elValor.innerText = (moeda ? fmtMoeda(valorAtual) : fmtNum(valorAtual, dec) + sufixo);
        if (elDelta) {
            const delta = valorAtual - valorAnterior;
            const pct = valorAnterior ? (delta / valorAnterior * 100) : 0;
            const cor = delta < 0 ? '#C2560C' : '#1A2740';
            const seta = delta < 0 ? '▼' : '▲';
            elDelta.innerText = seta + ' ' + Math.abs(pct).toFixed(1).replace('.', ',') + '% vs mês anterior';
            elDelta.style.color = cor;
            const card = elDelta.closest('.kpi-card');
            if (card) card.classList.toggle('negativo', delta < 0);
        }
    }

    setKpi('fattotal', fatAguaAt + fatEsgotoAt, fatAguaAnt + fatEsgotoAnt, { moeda: true });
    setKpi('fatagua', fatAguaAt, fatAguaAnt, { moeda: true });
    setKpi('fatesgoto', fatEsgotoAt, fatEsgotoAnt, { moeda: true });
    setKpi('eco', ecoAt, ecoAnt);
    setKpi('vol', volFatAt, volFatAnt, { sufixo: ' m³' });
    setKpi('volfat', volFatAt, volFatAnt, { sufixo: ' m³' });
    setKpi('tarifa', tarifaAt, tarifaAnt, { moeda: true });
    setKpi('vm', vmAt, vmAnt, { sufixo: ' m³', dec: 2 });
    setKpi('ticket', ticketAt, ticketAnt, { moeda: true });
    setKpi('acima', acimaAt, acimaAnt);

    if (window.graficoFaturamentoChart && window.dadosGraficoOriginal) {
        const chart = window.graficoFaturamentoChart;
        const original = window.dadosGraficoOriginal;
        const novosLabels = [], novosAtuais = [], novosAnteriores = [], novasCores = [];
        original.labels.forEach(function (label, idx) {
            if (marcados.includes(label)) {
                novosLabels.push(label);
                novosAtuais.push(original.atual[idx]);
                novosAnteriores.push(original.anterior[idx]);
                if (original.cores) novasCores.push(original.cores[idx]);
            }
        });
        chart.data.labels = novosLabels;
        chart.data.datasets[1].data = novosAtuais;
        chart.data.datasets[0].data = novosAnteriores;
        if (original.cores) chart.data.datasets[1].backgroundColor = novasCores;   // cor de alerta acompanha o grupo
        // poucos grupos: estreita o espaço de cada grupo para as barras não ficarem largas demais (o par fica junto)
        const espaco = Math.min(0.65, 0.12 + 0.1 * novosLabels.length);
        chart.data.datasets.forEach(ds => { ds.categoryPercentage = espaco; });
        // escala refeita só com os grupos filtrados (antes ficava presa ao maior valor de todos os grupos)
        const maximo = Math.max(0, ...novosAtuais, ...novosAnteriores);
        if (chart.options.scales && chart.options.scales.y) {
            chart.options.scales.y.suggestedMax = maximo * 1.2;
            delete chart.options.scales.y.max;
        }
        chart.update();
    }
}

function configurarTooltipGrafico() {
    if (!window.graficoFaturamentoChart) return;
    const chart = window.graficoFaturamentoChart;
    if (!chart.options.plugins) chart.options.plugins = {};
    chart.options.plugins.tooltip = {
        enabled: true, backgroundColor: '#05050D', titleColor: '#FFFFFF', bodyColor: '#FFFFFF',
        borderColor: '#394D73', borderWidth: 1, padding: 12, cornerRadius: 8,
        titleFont: { size: 13, weight: 'bold' }, bodyFont: { size: 12 }, displayColors: true,
        callbacks: {
            title: function(context) { return 'Grupo ' + context[0].label; },
            label: function(context) {
                return context.dataset.label + ': R$ ' + context.parsed.y.toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
            },
            afterBody: function(context) {
                if (context.length < 2) return [];
                const valorAnterior = context[0].parsed.y;
                const valorAtual = context[1].parsed.y;
                const diferenca = valorAtual - valorAnterior;
                const percentual = valorAnterior !== 0 ? (diferenca / valorAnterior) * 100 : 0;
                const sinal = diferenca >= 0 ? '+' : '';
                const seta = diferenca >= 0 ? '▲' : '▼';
                return ['', '───────────────',
                    seta + ' Diferença: ' + sinal + 'R$ ' + diferenca.toLocaleString('pt-BR', {minimumFractionDigits: 2}),
                    seta + ' Variação: ' + sinal + percentual.toFixed(1).replace('.', ',') + '%'];
            }
        }
    };
    chart.update();
}

// Justificativas: guardadas neste navegador e, quando o relatório é aberto pelo site com a pasta conectada, também no
// arquivo justificativas_relatorio.json da pasta (sincronizada com o SharePoint) — a cópia da pasta vale para todos.
function justCompartilhada() {
    try { const p = window.parent; if (p && p !== window && p.justificativasCompartilhadas && p.justificativasCompartilhadas.disponivel()) return p.justificativasCompartilhadas; }
    catch (e) { /* relatório aberto fora do site */ }
    const c = ajustesCopia();                              // cópia salva para o celular: lê os ajustes embutidos
    return c ? { disponivel: () => true, pasta: COPIA_LEITURA.pasta, ler: async () => c.justificativas || {},
                 gravar: async () => ({ ok: false, motivo: COPIA_MOTIVO }) } : null;
}
// Relatorio_Faturamento.html (cópia que o site grava na pasta para abrir no celular) traz os ajustes do momento em
// <script id="ajustes-copia">: sem a pasta, o relatório usa esses ajustes, só para leitura.
const COPIA_MOTIVO = 'relatório salvo, somente leitura — altere no computador com a pasta conectada';
function ajustesCopia() {
    if (ajustesCopia.v) return ajustesCopia.v;
    const el = document.getElementById('ajustes-copia');
    if (!el) return null;
    try { ajustesCopia.v = JSON.parse(el.textContent); ajustesCopia.salvo = el.dataset.salvo || ''; } catch (e) { return null; }
    return ajustesCopia.v;
}
const COPIA_LEITURA = {
    disponivel: () => true,
    pasta: () => 'relatório salvo' + (ajustesCopia.salvo ? ' em ' + new Date(ajustesCopia.salvo).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : ''),
    ler: async () => ajustesCopia(),
    atualizar: async () => ({ ok: false, motivo: COPIA_MOTIVO }),
};
function justStatus(texto, erro) {
    const el = document.getElementById('statusJust');
    if (!el) return;
    el.textContent = texto; el.classList.toggle('status-just-erro', !!erro);
}
const quandoJust = (iso) => { try { return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }); } catch (e) { return ''; } };
let justAtualizado = null;
function limparHtmlJust(html) {           // sem os botões de remover (são recriados ao carregar)
    const d = document.createElement('div'); d.innerHTML = html;
    d.querySelectorAll('.btn-remover-item').forEach(b => b.remove());
    d.querySelectorAll('[contenteditable]').forEach(e => e.removeAttribute('contenteditable'));
    return d.innerHTML;
}
async function lerJustificativasDaPasta() {
    const comp = justCompartilhada();
    if (!comp) { justStatus('Salvas só neste navegador (abra o relatório pelo site com a pasta do SharePoint conectada para compartilhar).'); return; }
    const lista = document.getElementById('lista-justificativas');
    if (lista.classList.contains('modo-edicao')) return;                 // não atropela quem está editando
    const dados = await comp.ler();
    if (!dados) { justStatus('Não foi possível ler as justificativas da pasta; usando as deste navegador.', true); return; }
    const item = dados[CHAVE_JUSTIFICATIVA];
    if (item && item.atualizado !== justAtualizado) {
        if (justAtualizado !== null && typeof avisoNuvem === 'function') avisoNuvem('Justificativas: atualizadas com alterações salvas por outra pessoa');
        lista.innerHTML = item.html;
        localStorage.setItem(CHAVE_JUSTIFICATIVA, item.html);
        justAtualizado = item.atualizado;
        justPreparar();
    }
    justStatus(item ? `Compartilhadas na pasta "${comp.pasta()}" · atualizadas em ${quandoJust(item.atualizado)}`
                    : `Compartilhadas na pasta "${comp.pasta()}" · ainda não salvas por ninguém neste mês`);
}

function carregarJustificativas() {
    const salvo = localStorage.getItem(CHAVE_JUSTIFICATIVA);
    if (salvo) document.getElementById('lista-justificativas').innerHTML = salvo;
    justPreparar();
    lerJustificativasDaPasta();
    setInterval(lerJustificativasDaPasta, 60000);                         // vê o que os outros salvaram sem recarregar
}

async function salvarJustificativas() {
    justLimparVazios();
    const conteudo = limparHtmlJust(document.getElementById('lista-justificativas').innerHTML);
    localStorage.setItem(CHAVE_JUSTIFICATIVA, conteudo);
    const comp = justCompartilhada();
    if (!comp) return;
    justStatus('Salvando na pasta…');
    const r = await comp.gravar(CHAVE_JUSTIFICATIVA, conteudo);
    if (r.ok) { justAtualizado = r.atualizado; justStatus(`Salvas na pasta "${comp.pasta()}" em ${quandoJust(r.atualizado)} — todos que abrirem a pasta verão`); }
    else justStatus(`Salvas só neste navegador: ${r.motivo}`, true);
    marcaNuvem('Justificativas', r);
    return r.ok;
}

function toggleEdicaoJustificativa() {
    const lista = document.getElementById('lista-justificativas');
    const btn = document.getElementById('btnEditarJust');
    const emEdicao = lista.classList.contains('modo-edicao');
    if (emEdicao) {
        lista.classList.remove('modo-edicao');
        lista.querySelectorAll('.jg-txt, :scope > p').forEach(p => p.contentEditable = false);
        btn.innerText = 'Editar';
        salvarJustificativas();
    } else {
        lista.classList.add('modo-edicao');
        lista.querySelectorAll('.jg-txt, :scope > p').forEach(p => p.contentEditable = true);
        btn.innerText = 'Salvar';
    }
}

function adicionarJustificativa() {
    const lista = document.getElementById('lista-justificativas');
    const sug = justInfo().grupos.slice(0, 12).join(', ') + (justInfo().grupos.length > 12 ? '…' : '');
    let g = prompt(`Grupo da justificativa${sug ? ' (' + sug + ')' : ''}.\nDeixe em branco para uma observação geral.`, '');
    if (g === null) return;
    g = g.trim().replace(/^grupo\s*/i, '');
    const chave = g ? normGrupo(g) : '';
    g = justInfo().grupos.find((x) => normGrupo(x) === chave) || g;      // "5" → "05", como o grupo aparece no relatório
    let bloco = Array.from(lista.querySelectorAll('.jg')).find((b) => (b.dataset.grupo ? normGrupo(b.dataset.grupo) : '') === chave);
    if (!bloco) {
        bloco = justBloco(g, '', '');
        const depois = Array.from(lista.querySelectorAll('.jg')).find((b) => b.dataset.grupo && g && justOrdem(b.dataset.grupo) > justOrdem(g));
        lista.insertBefore(bloco, depois || null);
        justPreparar();
    }
    if (!lista.classList.contains('modo-edicao')) toggleEdicaoJustificativa();
    else bloco.querySelectorAll('.jg-txt').forEach((t) => { t.contentEditable = true; });
    const alvo = Array.from(bloco.querySelectorAll('.jg-txt')).find((t) => !t.textContent.trim()) || bloco.querySelector('.jg-txt');
    if (alvo) { alvo.focus(); bloco.scrollIntoView({ block: 'nearest' }); }
}

function limparJustificativas() {
    if (!confirm('Remover todas as justificativas? Esta ação não pode ser desfeita.')) return;
    document.getElementById('lista-justificativas').innerHTML = '';
    salvarJustificativas();
}

// Justificativas por grupo, com água e esgoto separados (esgoto só nos grupos que têm esgoto no mês).
// Cada grupo é um bloco .jg[data-grupo] com colunas .jg-col[data-serv="agua"|"esgoto"]; o HTML salvo na pasta é esse.
// Texto no formato antigo (parágrafos "<strong>Grupo 501:</strong> ...") vira a coluna de água do grupo.
let JUST_INFO = null;
function justInfo() {                                     // lida na primeira vez que precisa (o script roda antes do card)
    if (JUST_INFO) return JUST_INFO;
    try {
        const j = JSON.parse(document.getElementById('just-grupos').textContent);
        JUST_INFO = { grupos: j.grupos || [], esgoto: new Set((j.esgoto || []).map((g) => normGrupo(g))) };
    } catch (e) { return { grupos: [], esgoto: new Set() }; }
    return JUST_INFO;
}
const justOrdem = (g) => { const n = parseFloat(String(g).replace(',', '.')); return isNaN(n) ? Infinity : n; };
const JUST_SERV = { agua: ['r-agua', '💧 Água', 'água'], esgoto: ['r-esg', 'Esgoto', 'esgoto'] };
function justBloco(g, agua, esgoto) {
    const temEsg = !!g && (justInfo().esgoto.has(normGrupo(g)) || !!String(esgoto || '').trim());
    const col = (s, h) => `<div class="jg-col" data-serv="${s}">`
        + (g ? `<span class="jg-rot ${JUST_SERV[s][0]}">${JUST_SERV[s][1]}</span>` : '')
        + `<div class="jg-txt" data-vazio="${g ? `Sem justificativa de ${JUST_SERV[s][2]} para este grupo — clique em Editar para escrever.` : 'Clique em Editar para escrever.'}">${h || ''}</div></div>`;
    const b = document.createElement('div');
    b.className = 'jg'; b.dataset.grupo = g;
    b.innerHTML = `<div class="jg-tit"><span>${g ? 'Grupo ' + garEscJust(g) : 'Observações gerais'}</span><small>${g ? (temEsg ? 'água e esgoto' : 'somente água') : ''}</small></div>`
        + `<div class="jg-cols${temEsg ? '' : ' um'}">${col('agua', agua)}${temEsg ? col('esgoto', esgoto) : ''}</div>`;
    return b;
}
const garEscJust = (v) => String(v).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
function justConverterAntigo(lista) {
    const blocos = new Map(), ordem = [];
    const pega = (g) => { if (!blocos.has(g)) { blocos.set(g, { agua: [], esgoto: [] }); ordem.push(g); } return blocos.get(g); };
    Array.from(lista.childNodes).forEach((n) => {
        if (n.nodeType === 3) { if (n.textContent.trim()) pega('').agua.push(garEscJust(n.textContent.trim())); return; }
        if (n.nodeType !== 1) return;
        n.querySelectorAll('.btn-remover-item').forEach((x) => x.remove());
        if (!n.textContent.trim()) return;
        const forte = n.querySelector('strong, b'), rot = forte ? forte.textContent : '';
        const m = rot.match(/grupo\s*([\w.\-]+)/i);
        if (!m) { pega('').agua.push(n.innerHTML.trim()); return; }
        forte.remove();
        const corpo = n.innerHTML.replace(/^\s*(:|-|–)?\s*/, '').trim();
        const soEsgoto = /esgoto/i.test(rot) && !/[áa]gua/i.test(rot);
        pega(m[1])[soEsgoto ? 'esgoto' : 'agua'].push(corpo);
    });
    lista.innerHTML = '';
    ordem.sort((a, b) => (a === '' ? 1 : b === '' ? -1 : justOrdem(a) - justOrdem(b)))
        .forEach((g) => { const x = blocos.get(g); lista.appendChild(justBloco(g, x.agua.join('<br>'), x.esgoto.join('<br>'))); });
}
function justPreparar() {
    const lista = document.getElementById('lista-justificativas'); if (!lista) return;
    if (!lista.querySelector('.jg') && lista.textContent.trim()) justConverterAntigo(lista);
    lista.querySelectorAll('.jg').forEach((b) => {           // grupo com esgoto que ainda não tem a coluna (ex.: salvo antes)
        const g = b.dataset.grupo;
        if (g && justInfo().esgoto.has(normGrupo(g)) && !b.querySelector('[data-serv="esgoto"]')) {
            const novo = justBloco(g, b.querySelector('[data-serv="agua"] .jg-txt')?.innerHTML || '', '');
            b.replaceWith(novo); b = novo;
        }
        const tit = b.querySelector('.jg-tit');
        if (tit && !tit.querySelector('.btn-remover-item')) {
            const r = document.createElement('button');
            r.type = 'button'; r.className = 'btn-remover-item'; r.title = 'Remover este grupo das justificativas';
            r.onclick = () => { if (confirm(`Remover as justificativas do ${tit.querySelector('span').textContent}?`)) { r.closest('.jg').remove(); salvarJustificativas(); } };
            tit.appendChild(r);
        }
        if (lista.classList.contains('modo-edicao')) b.querySelectorAll('.jg-txt').forEach((t) => { t.contentEditable = true; });
    });
}
function justLimparVazios() {                             // texto apagado no editor deixa <br> — volta a ficar vazio
    document.querySelectorAll('#lista-justificativas .jg-txt').forEach((t) => { if (!t.textContent.trim() && !t.querySelector('img')) t.innerHTML = ''; });
}
const aplicarBotoesRemover = justPreparar;

document.addEventListener('DOMContentLoaded', function () {
    mostrarView('resumo');
    try { const inf = JSON.parse(document.getElementById('info-filtros').textContent); ESTADO.mes = inf.mesAtual; ESTADO.ref = inf.refPadrao; } catch (e) { /* sem filtros */ }
    definirFiltros();
    envolverTabelasComScroll();
    habilitarScrollTabelas();
    recolherTabelasLongas();
    filtrarPorGrupo();
    configurarTooltipGrafico();
    carregarJustificativas();
});

// CSV (";", aspas no padrão do pandas) só com as linhas cuja coluna Superintendência é `sup`; null se não houver a coluna
function filtraCsvPorSup(texto, sup) { return filtraCsv(texto, { 'Superintendência': sup }); }

// CSV só com as linhas em que cada coluna de `filtros` ({coluna: valor}) tem o valor pedido; null se faltar alguma coluna
function filtraCsv(texto, filtros) {
    const bom = texto.charCodeAt(0) === 0xFEFF ? '\uFEFF' : '';
    if (bom) texto = texto.slice(1);
    const registros = [];                                   // quebra de linha dentro de aspas não separa registros
    let ini = 0, aspas = false;
    for (let i = 0; i < texto.length; i++) {
        const c = texto.charCodeAt(i);
        if (c === 34) aspas = !aspas;
        else if (c === 10 && !aspas) { registros.push(texto.slice(ini, i)); ini = i + 1; }
    }
    if (ini < texto.length) registros.push(texto.slice(ini));
    const campos = (r) => {                                 // campos do registro (sem as aspas)
        const out = []; let atual = '', q = false;
        for (let i = 0; i < r.length; i++) {
            const c = r[i];
            if (c === '"') { if (q && r[i + 1] === '"') { atual += '"'; i++; } else q = !q; }
            else if (c === ';' && !q) { out.push(atual); atual = ''; }
            else if (c !== '\r' || q) atual += c;
        }
        out.push(atual);
        return out;
    };
    if (!registros.length) return null;
    const cab = campos(registros[0]);
    const conds = Object.keys(filtros).map(nome => [cab.indexOf(nome), filtros[nome] instanceof Set ? filtros[nome] : String(filtros[nome])]);
    if (conds.some(([col]) => col < 0)) return null;
    const linhas = registros.slice(1).filter(r => {
        if (!r) return false;
        const f = campos(r);
        return conds.every(([col, v]) => v instanceof Set ? v.has(normGrupo(f[col] || '')) : (f[col] || '').trim() === v);
    });
    return bom + [registros[0]].concat(linhas).join('\n') + '\n';
}

// ===== Filtro de grupos nas tabelas e downloads de Top 100, Situação de lançamento e Sem faturamento =====
function normGrupo(v) {                                     // '514', '514.0', ' 05 ' → '514', '5' (como chave_grupo no Python)
    const t = String(v == null ? '' : v).trim();
    return /^\d+(\.0+)?$/.test(t) ? String(parseInt(t, 10)) : t;
}

// Set dos grupos marcados, ou null quando nenhum grupo visível (da SUP escolhida) está desmarcado
function gruposFiltro() {
    const caixas = Array.from(document.querySelectorAll('.chk-grupo'));
    if (!caixas.length) return null;
    const visiveis = caixas.filter(c => { const l = c.closest('label'); return !l || l.style.display !== 'none'; });
    if (!visiveis.some(c => !c.checked)) return null;
    return new Set(caixas.filter(c => c.checked).map(c => normGrupo(c.value)));
}

function lerJson(id) {
    if (!lerJson.cache) lerJson.cache = {};
    if (!(id in lerJson.cache)) {
        const el = document.getElementById(id);
        try { lerJson.cache[id] = el ? JSON.parse(el.textContent) : null; } catch (e) { lerJson.cache[id] = null; }
    }
    return lerJson.cache[id];
}

const fmtBR = (v, dec) => Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: dec || 0, maximumFractionDigits: dec || 0 });

function csvDe(colunas, linhas) {                           // CSV ";" com vírgula decimal (abre direto no Excel)
    const cel = v => {
        if (v === null || v === undefined) return '';
        if (typeof v === 'number') return String(v).replace('.', ',');
        const t = String(v);
        return /[;"\n\r]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t;
    };
    return '\uFEFF' + [colunas.map(cel).join(';')].concat(linhas.map(l => l.map(cel).join(';'))).join('\n') + '\n';
}

function baixarTexto(texto, nome) {
    const url = URL.createObjectURL(new Blob([texto], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url; a.download = nome; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
}

// ===== Excel (.xlsx) gerado aqui no navegador, sem biblioteca: um ZIP com os XML da planilha (uma aba, cabeçalho em
// negrito e congelado, filtro). Números viram números de verdade (somam no Excel); códigos (matrícula, ligação, CPF…) e
// valores com zero à esquerda ficam como texto. O ZIP sai comprimido (CompressionStream) onde o navegador permite.
const XLSX_MAX_LINHAS = 1048575;                   // limite de linhas de uma aba do Excel (fora o cabeçalho)
const XLSX_COL_TEXTO = /liga[cç][aã]o|matr[ií]cula|^lig$|c[oó]d|cpf|cnpj|inscri|telefone|celular|^cep|documento|hidr[oô]metro|^rota$|o\.?\s?s\.?$|^n[º°.]?\s*(da\s+)?o\.?s/i;
const XLSX_CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
function xlsxCrc(crc, b) { let c = crc ^ 0xFFFFFFFF; for (let i = 0; i < b.length; i++) c = XLSX_CRC[(c ^ b[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
const xlsxEsc = (t) => String(t).replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
function xlsxColuna(i) { let s = ''; i++; while (i > 0) { const r = (i - 1) % 26; s = String.fromCharCode(65 + r) + s; i = Math.floor((i - 1) / 26); } return s; }
// texto "1234,56" / "1.234,56" / "-12" (como nas bases e no analítico) → número; o resto continua texto
function xlsxNumero(v) {
    const t = String(v).trim();
    if (!/^-?(\d{1,15}|\d{1,3}(\.\d{3})+)(,\d+)?$/.test(t)) return null;
    if (/^-?0\d/.test(t)) return null;                                      // zero à esquerda (código): texto
    const n = parseFloat(t.replace(/\./g, '').replace(',', '.'));
    return isFinite(n) ? n : null;
}
async function xlsxZipEntrada(nome, partes) {
    const enc = new TextEncoder();
    let crc = 0, tam = 0, cs = null;
    try { cs = typeof CompressionStream !== 'undefined' ? new CompressionStream('deflate-raw') : null; } catch (e) { cs = null; }
    const cru = [], w = cs ? cs.writable.getWriter() : null, saida = cs ? new Response(cs.readable).arrayBuffer() : null;
    for (const p of partes) {
        const b = enc.encode(p); crc = xlsxCrc(crc, b); tam += b.length;
        if (w) await w.write(b); else cru.push(b);
    }
    let dados;
    if (w) { await w.close(); dados = new Uint8Array(await saida); }
    else { dados = new Uint8Array(tam); let o = 0; cru.forEach((b) => { dados.set(b, o); o += b.length; }); }
    return { nome: enc.encode(nome), crc, tam, dados, metodo: w ? 8 : 0 };
}
function xlsxZip(entradas) {
    const partes = [], central = []; let pos = 0;
    entradas.forEach((e) => {
        const h = new DataView(new ArrayBuffer(30));
        h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint16(6, 0x0800, true); h.setUint16(8, e.metodo, true);
        h.setUint16(10, 0, true); h.setUint16(12, 0x21, true);           // hora/data fixas (01/01/1980)
        h.setUint32(14, e.crc, true); h.setUint32(18, e.dados.length, true); h.setUint32(22, e.tam, true);
        h.setUint16(26, e.nome.length, true); h.setUint16(28, 0, true);
        const c = new DataView(new ArrayBuffer(46));
        c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true); c.setUint16(8, 0x0800, true); c.setUint16(10, e.metodo, true);
        c.setUint16(12, 0, true); c.setUint16(14, 0x21, true); c.setUint32(16, e.crc, true); c.setUint32(20, e.dados.length, true); c.setUint32(24, e.tam, true);
        c.setUint16(28, e.nome.length, true); c.setUint32(42, pos, true);
        partes.push(new Uint8Array(h.buffer), e.nome, e.dados); central.push(new Uint8Array(c.buffer), e.nome);
        pos += 30 + e.nome.length + e.dados.length;
    });
    const tamCentral = central.reduce((t, b) => t + b.length, 0), fim = new DataView(new ArrayBuffer(22));
    fim.setUint32(0, 0x06054b50, true); fim.setUint16(8, entradas.length, true); fim.setUint16(10, entradas.length, true);
    fim.setUint32(12, tamCentral, true); fim.setUint32(16, pos, true);
    return new Blob([...partes, ...central, new Uint8Array(fim.buffer)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
}
async function xlsxDe(colunas, linhas, aba) {
    const nc = colunas.length, letras = colunas.map((c, i) => xlsxColuna(i));
    const texto = colunas.map((c) => XLSX_COL_TEXTO.test(String(c).trim()));
    // largura de cada coluna: o maior entre o cabeçalho e as 300 primeiras linhas (limitada)
    const larg = colunas.map((c) => String(c).length + 2);
    linhas.slice(0, 300).forEach((l) => l.forEach((v, i) => { if (i < nc && v != null) larg[i] = Math.max(larg[i], String(v).length + 1); }));
    const cel = (v, ref, i) => {
        if (v === null || v === undefined || v === '') return '';
        let n = typeof v === 'number' ? v : (typeof v === 'boolean' || texto[i] ? null : xlsxNumero(v));
        if (n !== null && isFinite(n)) return `<c r="${ref}"${Number.isInteger(n) ? '' : ' s="2"'}><v>${n}</v></c>`;
        return `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${xlsxEsc(v)}</t></is></c>`;
    };
    const ultima = `${letras[nc - 1] || 'A'}${linhas.length + 1}`;
    function* folha() {
        yield '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            + '<cols>' + larg.map((w, i) => `<col min="${i + 1}" max="${i + 1}" width="${Math.min(60, Math.max(6, w))}" customWidth="1"/>`).join('') + '</cols><sheetData>'
            + '<row r="1">' + colunas.map((c, i) => `<c r="${letras[i]}1" t="inlineStr" s="1"><is><t xml:space="preserve">${xlsxEsc(c)}</t></is></c>`).join('') + '</row>';
        for (let a = 0; a < linhas.length; a += 2000) {
            let bloco = '';
            for (let r = a; r < Math.min(a + 2000, linhas.length); r++) {
                const l = linhas[r], n = r + 2; let x = `<row r="${n}">`;
                for (let i = 0; i < nc; i++) x += cel(l[i], letras[i] + n, i);
                bloco += x + '</row>';
            }
            yield bloco;
        }
        yield `</sheetData><autoFilter ref="A1:${ultima}"/></worksheet>`;
    }
    const nomeAba = xlsxEsc(String(aba || 'Dados').replace(/[\\\/?*\[\]:]/g, ' ').slice(0, 31) || 'Dados');
    const xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n';
    const entradas = await Promise.all([
        xlsxZipEntrada('[Content_Types].xml', [xml + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            + '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>']),
        xlsxZipEntrada('_rels/.rels', [xml + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>']),
        xlsxZipEntrada('xl/workbook.xml', [xml + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            + `<sheets><sheet name="${nomeAba}" sheetId="1" r:id="rId1"/></sheets>`
            + `<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'${nomeAba.replace(/'/g, "''")}'!$A$1:$${letras[nc - 1] || 'A'}$${linhas.length + 1}</definedName></definedNames></workbook>`]),
        xlsxZipEntrada('xl/_rels/workbook.xml.rels', [xml + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            + '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>']),
        xlsxZipEntrada('xl/styles.xml', [xml + '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>'
            + '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
            + '<fill><patternFill patternType="solid"><fgColor rgb="FF1A2740"/><bgColor indexed="64"/></patternFill></fill></fills>'
            + '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            + '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            + '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            + '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
            + '<xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
            + '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>']),
        xlsxZipEntrada('xl/worksheets/sheet1.xml', folha()),
    ]);
    return xlsxZip(entradas);
}
// Baixa a tabela em Excel (.xlsx); se não der (navegador antigo, mais linhas que o Excel aceita), baixa em CSV
async function baixarPlanilha(colunas, linhas, nome) {
    const base = nome.replace(/\.(csv|xlsx)$/i, '');
    try {
        if (linhas.length > XLSX_MAX_LINHAS) throw new Error('mais linhas que o Excel aceita');
        const blob = await xlsxDe(colunas, linhas, base.slice(0, 31));
        const url = URL.createObjectURL(blob), a = document.createElement('a');
        a.href = url; a.download = base + '.xlsx'; document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (erro) {
        console.warn('Excel indisponível, baixando em CSV:', erro);
        baixarTexto(csvDe(colunas, linhas), base + '.csv');
    }
}
// CSV ";" (bases e analítico embutidos) → { cab, linhas }; quebra de linha dentro de aspas não separa registros
function lerCsvTexto(texto) {
    const registros = [];
    let ini = 0, aspas = false, t = texto.charCodeAt(0) === 0xFEFF ? texto.slice(1) : texto;
    for (let i = 0; i < t.length; i++) {
        const c = t.charCodeAt(i);
        if (c === 34) aspas = !aspas;
        else if (c === 10 && !aspas) { registros.push(t.slice(ini, i)); ini = i + 1; }
    }
    if (ini < t.length) registros.push(t.slice(ini));
    const campos = (r) => {
        const out = []; let atual = '', q = false;
        for (let i = 0; i < r.length; i++) {
            const c = r[i];
            if (c === '"') { if (q && r[i + 1] === '"') { atual += '"'; i++; } else q = !q; }
            else if (c === ';' && !q) { out.push(atual); atual = ''; }
            else if (c !== '\r' || q) atual += c;
        }
        out.push(atual);
        return out;
    };
    return { cab: registros.length ? campos(registros[0]) : [], linhas: registros.slice(1).filter(Boolean).map(campos) };
}

// Top 100: as linhas de uma lista para a SUP e os grupos marcados (a ordem já é a do ranking geral)
function topLinhas(chave, sup) {
    const d = lerJson('top100-dados');
    if (!d || !d[chave]) return null;
    const cols = d[chave].columns, iSup = cols.indexOf('Superintendência'), iG = cols.indexOf('Grupo'), grupos = gruposFiltro();
    const linhas = d[chave].data.filter(l => (sup === 'TODAS' || iSup < 0 || l[iSup] === sup) && (!grupos || grupos.has(normGrupo(l[iG]))))
        .slice(0, 100).map(l => l.slice());              // cópia: o Ranking é renumerado sem mexer nos dados embutidos
    const iR = cols.indexOf('Ranking');
    linhas.forEach((l, i) => { if (iR >= 0) l[iR] = i + 1; });
    return { colunas: cols.filter((c, i) => i !== iSup), linhas: linhas.map(l => l.filter((v, i) => i !== iSup)) };
}

function refazTops() {
    const d = lerJson('top100-dados');
    if (!d) return;
    const grupos = gruposFiltro();
    document.querySelectorAll('table[data-top]').forEach(tabela => {
        if (!grupos && !tabela.dataset.refeita) return;     // sem filtro de grupo: fica a tabela original
        const bloco = tabela.closest('[data-sup]'), sup = bloco ? bloco.dataset.sup : 'TODAS';
        const r = topLinhas(tabela.dataset.top, sup);
        if (!r) return;
        tabela.dataset.refeita = grupos ? '1' : '';
        const aumento = tabela.dataset.top.startsWith('aumento'), pre = aumento ? 'Aumento' : 'Queda', cor = aumento ? '#176b9c' : '#C2560C';
        const corpo = tabela.querySelector('tbody');
        corpo.innerHTML = '';
        r.linhas.forEach(l => {
            const tr = document.createElement('tr');
            r.colunas.forEach((c, i) => {
                const td = document.createElement('td'), v = l[i];
                let texto;
                if (c.startsWith('Valor R$') || c === pre + '_Valor_R$') texto = 'R$ ' + fmtBR(v, 2);
                else if (c === pre + '_%') texto = v === null ? '—' : fmtBR(v, 1) + '%';
                else if (c.startsWith('Consumo ') || c === pre + '_Consumo') texto = fmtBR(v, 2);
                else texto = v === null ? '' : String(v);
                td.textContent = texto;
                td.style.textAlign = (['Nome_Cliente', 'Grupo', 'Categoria'].includes(c) || c.startsWith('Situação Lançamento')) ? 'left' : 'center';
                if (c === pre + '_%' && typeof v === 'number' && v >= d.destaque) { td.style.color = cor; td.style.fontWeight = '700'; }
                tr.appendChild(td);
            });
            corpo.appendChild(tr);
        });
        // "Mostrar todos": refaz o botão com as linhas novas
        const ancora = tabela.closest('.tabela-wrap') || tabela, prox = ancora.nextElementSibling;
        if (prox && prox.classList.contains('btn-ver-todos')) prox.remove();
        delete tabela.dataset.recolhido;
    });
    recolherTabelasLongas();
}

// Situação de lançamento: refaz os números dos cards com os grupos marcados
function sitlSomas(sup) {
    const d = lerJson('sitl-agregados');
    if (!d) return null;
    const grupos = gruposFiltro(), soma = {};
    [['at', 0], ['ant', 1]].forEach(([k, m]) => d[k].forEach(([s, g, sit, n, eco, vol, val]) => {
        if ((sup !== 'TODAS' && s !== sup) || (grupos && !grupos.has(normGrupo(g)))) return;
        const x = soma[sit] || (soma[sit] = [[0, 0, 0, 0], [0, 0, 0, 0]]);
        x[m][0] += n; x[m][1] += eco; x[m][2] += vol; x[m][3] += val;
    }));
    const tot = [0, 1].map(m => Object.values(soma).reduce((a, x) => a + x[m][0], 0));
    // visão sintética: soma dos códigos de cada leitura da situação (grupo)
    const somaGrupo = {};
    Object.entries(soma).forEach(([sit, x]) => {
        const g = (d.grupo || {})[sit] || 'Outros', y = somaGrupo[g] || (somaGrupo[g] = [[0, 0, 0, 0], [0, 0, 0, 0]]);
        for (let m = 0; m < 2; m++) for (let k = 0; k < 4; k++) y[m][k] += x[m][k];
    });
    return { soma, somaGrupo, tot };
}

function sitlRecalcular() {
    if (!lerJson('sitl-agregados')) return;
    document.querySelectorAll('.sup-top-bloco').forEach(bloco => {
        const cards = bloco.querySelectorAll('.sitl-card');
        if (!cards.length) return;
        const r = sitlSomas(bloco.dataset.sup);
        cards.forEach(card => {
            const fonte = card.dataset.gsit !== undefined ? r.somaGrupo[card.dataset.gsit] : r.soma[card.dataset.sit];
            const [at, ant] = fonte || [[0, 0, 0, 0], [0, 0, 0, 0]];
            card.style.display = (at[0] || ant[0]) ? '' : 'none';
            const pct = r.tot[0] ? at[0] / r.tot[0] * 100 : 0, pctAnt = r.tot[1] ? ant[0] / r.tot[1] * 100 : 0;
            const pos = (f, txt) => { const el = card.querySelector('[data-f="' + f + '"]'); if (el) el.textContent = txt; };
            const varia = (f, v, dec, suf) => {
                const el = card.querySelector('[data-f="' + f + '"]'); if (!el) return;
                el.textContent = (v > 0 ? '+' : '') + fmtBR(v, dec) + (suf || '');
                el.style.color = v < 0 ? '#C2560C' : v > 0 ? '#176b9c' : '#49668C';
            };
            pos('lig', fmtBR(at[0])); pos('pct', fmtBR(pct, 1)); varia('pp', pct - pctAnt, 1, ' p.p.');
            varia('dlig', at[0] - ant[0], 0); pos('vol', fmtBR(at[2]));
            pos('vme', fmtBR(at[1] ? at[2] / at[1] : 0, 2)); pos('vmeant', fmtBR(ant[1] ? ant[2] / ant[1] : 0, 2));
            pos('val', 'R$ ' + fmtBR(at[3], 2)); varia('dval', at[3] - ant[3], 2);
            const seta = card.querySelector('.btn-detalhe'); if (seta) seta.style.display = at[0] ? '' : 'none';
        });
    });
}

// ===== Analítico por matrícula da aba Análise (seta ⬇≡ ao lado de cada tabela) =====
// O analítico vem embutido uma vez (script#analitico-dados, CSV em gzip): uma linha por ligação, mês anterior e atual
// lado a lado. Cada seta baixa as colunas e as linhas da sua tabela, com os filtros de Superintendência e Grupo.
let analiticoCache = null;
async function lerAnalitico() {
    if (analiticoCache) return analiticoCache;
    const el = document.getElementById('analitico-dados');
    if (!el) return null;
    const { cab, linhas } = lerCsvTexto(new TextDecoder('utf-8').decode(await bytesEmbutidos(el)));
    analiticoCache = { cab, linhas, ra: el.dataset.refAtual, rn: el.dataset.refAnterior, mes: el.dataset.mes };
    return analiticoCache;
}

const numBR = (v) => (v === '' || v == null ? null : parseFloat(String(v).replace(',', '.')));

// colunas e linhas de cada tabela; "top-…": ranking completo calculado aqui (todas as ligações com queda/aumento)
function definicaoAnalitico(tipo, ra, rn) {
    const base = ['N. Ligação', 'Nome Cliente', 'Categoria', 'Superintendência', 'Grupo'];
    const par = (nome) => [`${nome} ${rn}`, `${nome} ${ra}`];
    const algum = (...cols) => (v) => cols.some((c) => v(c) !== '');
    switch (tipo) {
        case 'ativas': return { nome: 'Ativas_x_Cortadas', esgMes: (ref) => [`Ativa/Cortada ${ref}`], cols: base.concat(par('Grupo'), par('Situação Ligação'), par('Ativa/Cortada'),
            par('Economias'), par('Consumo água')), filtro: algum(...par('Ativa/Cortada')) };
        case 'matriz': return { nome: 'Migracao_de_Grupos', esgLinha: true, cols: base.concat(par('Grupo'), ['Migração de grupo'], par('Economias'), par('Consumo água')),
            filtro: (v) => v('Migração de grupo') !== 'Sem consumo nos dois meses' };
        case 'minimo': return { nome: 'Consumo_Minimo', esgMes: (ref) => [`Acima/Abaixo do mínimo ${ref}`], cols: base.concat(par('Economias'), par('Consumo água'), par('Mínimo da matrícula'),
            [`Conta do mínimo ${ra}`], par('Acima/Abaixo do mínimo'), ['Mudança de classe']), filtro: algum(...par('Acima/Abaixo do mínimo')),
            extra: { 'Mudança de classe': (v) => { const a = v(`Acima/Abaixo do mínimo ${rn}`), b = v(`Acima/Abaixo do mínimo ${ra}`);
                return a && b ? (a === b ? 'Manteve' : `${a} → ${b}`) : ''; } } };
        // cortadas com consumo: Situação Ligação cortada no mês atual e Consumo Medido > 0 (o faturado é só informação)
        case 'cortadas': {
            const [mAnt, mAt] = par('Consumo medido água'), cortada = (t) => /CORT/i.test(t);
            return { nome: 'Cortadas_com_consumo', exige: mAt,
                semColuna: 'A base de consumo deste relatório não tem a coluna Consumo Medido (ou o relatório é de uma versão anterior): atualize a análise.',
                vazio: 'Nenhuma ligação cortada com consumo medido no mês (com os filtros da tela).',
                cols: base.concat(['Localidade', 'Zona'], par('Grupo'), par('Situação Ligação'), par('Situação Lançamento'), par('Economias'), [mAnt, mAt],
                    par('Consumo água'), par('Valor água'), par('Valor esgoto'), par('Acima/Abaixo do mínimo'), ['Cortada e medindo há 2 meses']),
                filtro: (v) => cortada(v(`Situação Ligação ${ra}`)) && numBR(v(mAt)) > 0,
                extra: { [mAt]: (v) => numBR(v(mAt)),
                    'Cortada e medindo há 2 meses': (v) => (cortada(v(`Situação Ligação ${rn}`)) && numBR(v(mAnt)) > 0 ? 'Sim' : 'Não') },
                ordem: mAt };
        }
        case 'situacao': return { nome: 'Situacao_Lancamento', cols: base.concat(par('Situação Lançamento'), par('Leitura da situação'),
            par('Situação Ligação'), par('Economias'), par('Consumo água'), par('Valor total'), ['Δ valor total']),
            filtro: algum(...par('Situação Lançamento')) };
    }
    const d = /^diretas-(agua|esgoto)$/.exec(tipo);
    if (d) {
        // Diretas: de quais matrículas vieram as variações de economias, volume e faturamento (maiores quedas primeiro)
        const serv = d[1] === 'agua' ? 'água' : 'esgoto';
        const [eAnt, eAt] = par(`Economias faturadas ${serv}`), [cAnt, cAt] = par(`Consumo ${serv}`), [vAnt, vAt] = par(`Valor ${serv}`);
        const n = (v, c) => numBR(v(c)) || 0, dif = (a, b) => (v) => Math.round((n(v, b) - n(v, a)) * 100) / 100;
        // com grupos filtrados, cada mês só conta se a matrícula estava num grupo marcado NAQUELE mês (como o painel):
        // quem mudou de grupo aparece na lista, mas os números do outro mês ficam em branco
        // análise de ciclo (coluna Situação): só com UM grupo filtrado — ele é a referência
        const marcados = gruposFiltro(), grupoRef = marcados && marcados.size === 1 ? Array.from(marcados)[0] : null;
        // "A-ATIVA" / "C - Cortada" → "Ativa" / "Cortada"
        const sitTexto = (t) => { t = String(t || '').trim().replace(/^[A-Za-z0-9]{1,3}\s*-\s*/, '').toLowerCase(); return t ? t[0].toUpperCase() + t.slice(1) : ''; };
        return { nome: `Diretas_${d[1] === 'agua' ? 'Agua' : 'Esgoto'}`, grupos: par('Grupo'),
            porMes: [[`Grupo ${rn}`, [eAnt, cAnt, vAnt]], [`Grupo ${ra}`, [eAt, cAt, vAt]]],
            cols: base.concat(par('Grupo'), ['Migração de grupo'], par('Situação Ligação'), par('Situação Lançamento'),
                [eAnt, eAt, 'Δ economias', cAnt, cAt, 'Δ consumo', vAnt, vAt, 'Δ valor', 'Δ % valor', 'O que aconteceu'], grupoRef ? ['Situação'] : []),
            filtro: (v) => n(v, vAnt) !== 0 || n(v, vAt) !== 0 || n(v, eAnt) !== 0 || n(v, eAt) !== 0,
            extra: {
                'Δ economias': dif(eAnt, eAt), 'Δ consumo': dif(cAnt, cAt), 'Δ valor': dif(vAnt, vAt),
                'Δ % valor': (v) => { const a = n(v, vAnt); return a ? Math.round((n(v, vAt) - a) / a * 1000) / 10 : null; },
                'O que aconteceu': (v) => {
                    const a = n(v, vAnt), b = n(v, vAt), ga = v(`Grupo ${rn}`), gb = v(`Grupo ${ra}`);
                    if (ga && gb && normGrupo(ga) !== normGrupo(gb)) return `Mudou do grupo ${ga} para o ${gb}`;
                    if (a && !b) return 'Deixou de faturar no mês atual';
                    if (!a && b) return 'Passou a faturar no mês atual';
                    if (n(v, eAt) < n(v, eAnt)) return b < a ? 'Caiu: perdeu economias' : 'Perdeu economias';
                    if (n(v, eAt) > n(v, eAnt)) return b > a ? 'Subiu: ganhou economias' : 'Ganhou economias';
                    return b < a ? 'Caiu: menor consumo/valor' : b > a ? 'Subiu: maior consumo/valor' : 'Igual';
                },
                // Situação (análise de ciclo, só com um grupo filtrado): 1º mudança de grupo, vista do grupo filtrado; 2º sem mudança:
                // o mês sem economias faturadas traz a situação da ligação naquele mês; 3º economias nos dois meses.
                // O resto fica em branco (análise manual).
                'Situação': (v) => {
                    const ga = v(`Grupo ${rn}`), gb = v(`Grupo ${ra}`);
                    if (ga && gb && normGrupo(ga) !== normGrupo(gb)) {
                        if (normGrupo(ga) === grupoRef) return `Passou para o Grupo ${gb}`;
                        if (normGrupo(gb) === grupoRef) return `Estava no Grupo ${ga}`;
                        return '';
                    }
                    const ea = n(v, eAnt), eb = n(v, eAt);
                    if (ea > 0 && eb > 0) return 'Faturou os dois meses';
                    if (eb > 0) return sitTexto(v(`Situação Ligação ${rn}`));
                    if (ea > 0) return sitTexto(v(`Situação Ligação ${ra}`));
                    return '';
                },
            },
            ordem: 'Δ valor', crescente: true };
    }
    const m = /^top-(queda|aumento)-(agua|esgoto)$/.exec(tipo);
    if (!m) return null;
    const serv = m[2] === 'agua' ? 'água' : 'esgoto', queda = m[1] === 'queda', P = queda ? 'Queda' : 'Aumento';
    const cAnt = `Consumo ${serv} ${rn}`, cAt = `Consumo ${serv} ${ra}`;
    return { nome: `Ranking_${P}_${m[2] === 'agua' ? 'Agua' : 'Esgoto'}`, ranking: true,
        cols: ['Ranking'].concat(base, [`Grupo ${ra}`], par('Situação Lançamento'), [`Situação Ligação ${ra}`], par('Economias'),
            [cAnt, cAt, `${P} de consumo`, `${P} %`], par(`Valor ${serv}`), [`${P} de valor`], par('Acima/Abaixo do mínimo')),
        filtro: (v) => v(cAnt) !== '' && v(cAt) !== '' && (queda ? numBR(v(cAnt)) - numBR(v(cAt)) : numBR(v(cAt)) - numBR(v(cAnt))) > 0,
        extra: {
            [`${P} de consumo`]: (v) => Math.round((queda ? numBR(v(cAnt)) - numBR(v(cAt)) : numBR(v(cAt)) - numBR(v(cAnt))) * 100) / 100,
            [`${P} %`]: (v) => { const a = numBR(v(cAnt)); if (!a) return null; return Math.round(Math.abs(numBR(v(cAt)) - a) / a * 1000) / 10; },
            [`${P} de valor`]: (v) => { const a = numBR(v(`Valor ${serv} ${rn}`)) || 0, b = numBR(v(`Valor ${serv} ${ra}`)) || 0;
                return Math.round((queda ? a - b : b - a) * 100) / 100; },
        },
        ordem: `${P} de consumo` };
}

document.addEventListener('click', function (e) {
    const b = e.target.closest && e.target.closest('.btn-detalhe');
    if (b) baixaDetalhe(b);
});
// botão "Cortadas com consumo" do site (barra de cima): mesmo analítico, sem seta na tela
window.baixarCortadasConsumo = () => baixaDetalhe({ dataset: { detalhe: 'cortadas' }, closest: () => null });
async function baixaDetalhe(b) {
    try {
        const a = await lerAnalitico();
        if (!a) { alert('Este relatório não tem o analítico por matrícula: atualize a análise.'); return; }
        const def = definicaoAnalitico(b.dataset.detalhe, a.ra, a.rn);
        if (!def) return;
        if (def.exige && !a.cab.includes(def.exige)) { alert(def.semColuna); return; }
        const idx = Object.fromEntries(a.cab.map((c, i) => [c, i]));
        const bloco = b.closest('.sup-top-bloco');
        const sup = bloco ? bloco.dataset.sup : (ESTADO.sup || 'TODAS'), grupos = gruposFiltro();
        const soEsg = analiseVista === 'esgoto' && (def.esgMes || def.esgLinha);
        const leitor = (l) => {
            const bruto0 = (c) => (idx[c] === undefined ? '' : (l[idx[c]] || ''));
            let bruto = bruto0;
            if (soEsg) {                             // vista "só esgoto": o mês só conta se a ligação faturou esgoto nele
                const semEsg = (ref) => !(numBR(bruto0(`Consumo esgoto ${ref}`)) > 0);
                if (def.esgLinha) { if (semEsg(a.rn) && semEsg(a.ra)) bruto = () => ''; }
                else {
                    const fora = new Set();
                    [a.rn, a.ra].forEach((ref) => { if (semEsg(ref)) def.esgMes(ref).forEach((c) => fora.add(c)); });
                    if (fora.size) bruto = (c) => (fora.has(c) ? '' : bruto0(c));
                }
            }
            if (!def.porMes || !grupos) return bruto;
            const fora = new Set();
            def.porMes.forEach(([gc, cols]) => { const g = bruto(gc); if (!g || !grupos.has(normGrupo(g))) cols.forEach((c) => fora.add(c)); });
            return fora.size ? (c) => (fora.has(c) ? '' : bruto(c)) : bruto;
        };
        let linhas = a.linhas.filter((l) => {
            const v = leitor(l);
            const sit = b.dataset.sit !== undefined ? v(`Situação Lançamento ${a.ra}`) === b.dataset.sit
                : b.dataset.gsit !== undefined ? v(`Leitura da situação ${a.ra}`) === b.dataset.gsit : true;
            return (sup === 'TODAS' || v('Superintendência') === sup) && sit && def.filtro(v)
                && (!grupos || (def.grupos || ['Grupo']).some((c) => v(c) !== '' && grupos.has(normGrupo(v(c)))));
        }).map((l) => {
            const v = leitor(l);
            return def.cols.map((c) => (def.extra && def.extra[c] ? def.extra[c](v) : c === 'Ranking' ? 0 : v(c)));
        });
        if (def.ordem) {
            const io = def.cols.indexOf(def.ordem);
            linhas.sort((x, y) => (def.crescente ? (x[io] || 0) - (y[io] || 0) : (y[io] || 0) - (x[io] || 0)));
            if (def.ranking) linhas.forEach((l, i) => { l[0] = i + 1; });
        }
        const sitNome = (b.dataset.sit || b.dataset.gsit || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
            .replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '');
        const nome = `${def.nome}${soEsg ? '_so_esgoto' : ''}${sitNome ? '_' + sitNome : ''}_${a.mes}${sup !== 'TODAS' ? '_' + sup.replace(/[^A-Za-z0-9]/g, '') : ''}${grupos ? '_grupos_filtrados' : ''}.csv`;
        if (!linhas.length && def.vazio) { alert(def.vazio); return; }
        await baixarPlanilha(def.cols, linhas, nome);
    } catch (erro) {
        alert('Não foi possível baixar o analítico neste navegador (' + erro.message + ').');
    }
}

// Situação de lançamento: botão Analítica / Sintética (vale para os quadros de todas as SUPs; lembra a última escolha)
function sitlVisao(visao) {
    document.querySelectorAll('.sitl-grid[data-visao]').forEach(g => { g.hidden = g.dataset.visao !== visao; });
    document.querySelectorAll('.sitl-visao button').forEach(b => {
        const ativo = b.dataset.visao === visao; b.classList.toggle('ativo', ativo); b.setAttribute('aria-pressed', ativo ? 'true' : 'false');
    });
    try { localStorage.setItem('faturamento_sitl_visao', visao); } catch (e) { /* sem armazenamento */ }
}
document.addEventListener('click', function (e) {
    const b = e.target.closest && e.target.closest('.sitl-visao button');
    if (b) { sitlVisao(b.dataset.visao); configAlterada(); }
});
document.addEventListener('DOMContentLoaded', function () {
    let v = null; try { v = localStorage.getItem('faturamento_sitl_visao'); } catch (e) { /* sem armazenamento */ }
    if (v === 'sintetica') sitlVisao(v);
});

// base64 (e gzip, com data-gz="1") embutido num <script> → bytes do arquivo
async function bytesEmbutidos(el) {
    const bin = atob(el.textContent.trim()), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    if (el.dataset.gz !== '1') return bytes;
    const fluxo = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    return new Uint8Array(await new Response(fluxo).arrayBuffer());
}

// Botões "Base: ... (Excel)": a base vem embutida uma vez (script#base-dl-<chave>, comprimida) e vários botões a usam
document.addEventListener('click', async function (e) {
    const b = e.target.closest && e.target.closest('.btn-baixar-base');
    if (!b) return;
    const el = document.getElementById('base-dl-' + b.dataset.ref);
    if (!el) return;
    let bytes;
    try { bytes = await bytesEmbutidos(el); }
    catch (erro) { alert('Não foi possível abrir a base neste navegador (' + erro.message + ').'); return; }
    let conteudo = bytes, nome = el.dataset.arquivo;
    const sup = (typeof ESTADO !== 'undefined' && ESTADO.sup) || 'TODAS';
    const grupos = gruposFiltro();
    if (sup !== 'TODAS' || grupos) {                        // filtros Superintendência e Grupo: só as linhas escolhidas
        let texto = new TextDecoder('utf-8').decode(bytes);
        if (sup !== 'TODAS') {
            const f = filtraCsvPorSup(texto, sup);
            if (f !== null) { texto = f; nome = nome.replace(/\.csv$/i, '_' + sup.replace(/[^A-Za-z0-9]/g, '') + '.csv'); }
        }
        if (grupos) {                                       // base sem coluna Grupo (orçado) vem sem esse filtro
            const f = filtraCsv(texto, { 'Grupo': grupos });
            if (f !== null) { texto = f; nome = nome.replace(/\.csv$/i, '_grupos_filtrados.csv'); }
        }
        conteudo = texto;
    }
    // em Excel (.xlsx): números como números; base maior que o limite do Excel continua em CSV
    const texto = typeof conteudo === 'string' ? conteudo : new TextDecoder('utf-8').decode(conteudo);
    const { cab, linhas } = lerCsvTexto(texto);
    if (cab.length && linhas.length <= XLSX_MAX_LINHAS) { await baixarPlanilha(cab, linhas, nome); return; }
    const url = URL.createObjectURL(new Blob([conteudo], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url; a.download = nome; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
});

// Botões "Baixar (Excel)": o arquivo vem embutido no relatório em base64
document.addEventListener('click', function (e) {
    const b = e.target.closest && e.target.closest('.btn-baixar');
    if (!b) return;
    const bin = atob(b.dataset.b64), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
    const a = document.createElement('a');
    a.href = url; a.download = b.dataset.arquivo; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
});

// ===== Previsão de fechamento (aba DRE): células editáveis, totais refeitos aqui no navegador =====
const PREV_BASICAS = ['dA', 'dE', 'iE', 'ri_CORTE', 'ri_RELIGAÇÃO', 'ri_LNA', 'ri_SANÇÃO', 'ri_OUTROS', 'ecoA', 'ecoE', 'volA', 'volE', 'canc'];
const PREV_CLASSES_RI = ['ri_CORTE', 'ri_RELIGAÇÃO', 'ri_LNA', 'ri_SANÇÃO', 'ri_OUTROS'];
const PREV_EV_RI = PREV_CLASSES_RI.map(k => 'ev_' + k);          // aba Indiretas: eventos faturados
PREV_BASICAS.push(...PREV_EV_RI, 'ev_iE');
const PREV_CHAVE_LS = 'faturamento_previsao_v2';
let prevEdicoes = {}, prevOculta = false, prevOcultaInd = false;     // "Ocultar forecast": um para a aba Forecast, outro para a Indiretas
try { const salvo = JSON.parse(localStorage.getItem(PREV_CHAVE_LS) || '{}'); prevEdicoes = salvo.edicoes || {};
    // a SUP LAGOS passou a se chamar INTERIOR: as edições guardadas com o nome antigo continuam valendo
    Object.keys(prevEdicoes).filter(c => c.includes('|LAGOS|')).forEach(c => { const n = c.replace('|LAGOS|', '|INTERIOR|'); if (!(n in prevEdicoes)) prevEdicoes[n] = prevEdicoes[c]; delete prevEdicoes[c]; }); prevOculta = !!salvo.oculta; prevOcultaInd = !!salvo.ocultaInd; } catch (e) { /* sem armazenamento: vale só nesta abertura */ }
function prevSalvar() {
    try { localStorage.setItem(PREV_CHAVE_LS, JSON.stringify({ edicoes: prevEdicoes, oculta: prevOculta, ocultaInd: prevOcultaInd })); } catch (e) { /* ignora */ }
    if (typeof syncForecast !== 'undefined') syncForecast.agendar();
}

const prevN = (v, d) => v.toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
function prevFmt(v, formato) {
    if (v === null || v === undefined || !isFinite(v)) return '-';
    if (formato === 'dec') return prevN(v, 2);
    if (formato === 'num') return prevN(v, 0);
    const t = prevN(Math.abs(v), 0);
    return v < 0 ? `R$ (${t})` : `R$ ${t}`;
}
function prevLer(txt) {                       // "1.234,56", "R$ (1.234)", "1234.5" -> número
    let t = String(txt).replace(/R\$|\s/g, ''), neg = false;
    if (/^\(.*\)$/.test(t)) { neg = true; t = t.slice(1, -1); }
    if (t.startsWith('-')) { neg = !neg; t = t.slice(1); }
    if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.');
    else if (/^\d{1,3}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, '');
    const v = parseFloat(t);
    return isNaN(v) ? null : (neg ? -v : v);
}
const prevAttr = (el, a) => { const v = el.getAttribute(a); return v === null || v === '' ? null : parseFloat(v); };
const prevChave = (tab, k) => `${tab.dataset.mes}|${tab.dataset.prev}|${k}`;

function prevRecalcular(tab) {
    const linha = k => tab.querySelector(`tr[data-k="${k}"]`);
    const FC = {}, C = {};                       // FC: forecast (editável) · C: realizado + forecast
    PREV_BASICAS.forEach(k => {
        const tr = linha(k); if (!tr) return;
        const ed = prevEdicoes[prevChave(tab, k)], real = prevAttr(tr, 'data-real');
        FC[k] = ed !== undefined ? ed : prevAttr(tr, 'data-auto');
        C[k] = (real == null && FC[k] == null) ? null : (real || 0) + (FC[k] || 0);
    });
    const soma = (o, ks) => ks.some(k => o[k] != null) ? ks.reduce((a, k) => a + (o[k] || 0), 0) : null;
    const div = (a, b) => (a != null && b) ? a / b : null;
    C.dTot = soma(C, ['dA', 'dE']); C.iA = soma(C, PREV_CLASSES_RI); C.bruto = soma(C, ['dTot', 'iA', 'iE']);
    FC.dTot = soma(FC, ['dA', 'dE']); FC.iA = soma(FC, PREV_CLASSES_RI); FC.bruto = soma(FC, ['dTot', 'iA', 'iE']);
    C.tot = soma(C, ['iA', 'iE']); FC.tot = soma(FC, ['iA', 'iE']);            // Total indiretas (aba Indiretas)
    C.ev_iA = soma(C, PREV_EV_RI); FC.ev_iA = soma(FC, PREV_EV_RI);
    C.ev_tot = soma(C, ['ev_iA', 'ev_iE']); FC.ev_tot = soma(FC, ['ev_iA', 'ev_iE']);
    C.vmA = div(C.volA, C.ecoA); C.vmE = div(C.volE, C.ecoE);
    C.tarA = div(C.dA, C.volA); C.tarE = div(C.dE, C.volE);
    C.tickA = div(C.dA, C.ecoA); C.tickE = div(C.dE, C.ecoE);
    tab.querySelectorAll('tbody tr[data-k]').forEach(tr => {
        const k = tr.dataset.k, formato = tr.dataset.fmt, v = C[k] === undefined ? null : C[k];
        const cel = tr.querySelector('.p-prev');
        if (cel && document.activeElement !== cel) cel.textContent = prevFmt(FC[k] === undefined ? null : FC[k], formato);
        if (cel) cel.classList.toggle('editado', prevEdicoes[prevChave(tab, k)] !== undefined);
        const fech = tr.querySelector('.p-fech'); if (fech) fech.textContent = prevFmt(v, formato);
        const neg = (x) => x !== null && x < -0.0005 && tr.dataset.canc !== '1';
        tr.querySelectorAll('.p-dorc').forEach(el => {
            const base = prevAttr(el, 'data-orc'), pct = (v != null && base) ? v / base - 1 : null;
            el.textContent = pct === null ? '-' : prevN(pct * 100, 1) + '%';
            el.classList.toggle('neg', neg(pct));
        });
        tr.querySelectorAll('.p-dorcv').forEach(el => {
            const base = prevAttr(el, 'data-orc'), d = (v != null && base != null) ? v - base : null;
            el.textContent = d === null ? '-' : prevFmt(d, formato);
            el.classList.toggle('neg', neg(d === null || !base ? null : d / base));
        });
    });
}

function prevRecalcularTodas() {
    document.querySelectorAll('table.tabela-previsao').forEach(prevRecalcular);
    document.dispatchEvent(new Event('forecast-recalculado'));       // o One page refaz a tendência com o forecast novo
}

document.addEventListener('focusin', e => {
    const cel = e.target.closest && e.target.closest('.prev-edit'); if (!cel) return;
    const tab = cel.closest('table'), k = cel.dataset.k, tr = cel.closest('tr');
    const ed = prevEdicoes[prevChave(tab, k)], atual = ed !== undefined ? ed : prevAttr(tr, 'data-auto');
    cel.textContent = atual == null ? '' : String(Math.round(atual * 100) / 100).replace('.', ',');
    const r = document.createRange(); r.selectNodeContents(cel); const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
});
document.addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.target.closest && e.target.closest('.prev-edit')) { e.preventDefault(); e.target.blur(); }
    if (e.key === 'Escape' && e.target.closest && e.target.closest('.prev-edit')) { e.target.dataset.cancelar = '1'; e.target.blur(); }
});
document.addEventListener('focusout', e => {
    const cel = e.target.closest && e.target.closest('.prev-edit'); if (!cel) return;
    const tab = cel.closest('table'), k = cel.dataset.k, tr = cel.closest('tr'), chave = prevChave(tab, k);
    if (cel.dataset.cancelar) { delete cel.dataset.cancelar; }
    else {
        const txt = cel.textContent.trim(), v = txt === '' ? null : prevLer(txt), auto = prevAttr(tr, 'data-auto');
        if (v === null) delete prevEdicoes[chave];
        else if (auto !== null && Math.abs(v - auto) < 0.005) delete prevEdicoes[chave];
        else prevEdicoes[chave] = v;
        prevSalvar();
    }
    prevRecalcularTodas();                       // a mesma linha aparece no Forecast e nas Indiretas
});

function previsaoRestaurar(botao) {
    const tab = botao.closest('.prev-card').querySelector('table.tabela-previsao');
    Object.keys(prevEdicoes).filter(c => c.startsWith(`${tab.dataset.mes}|${tab.dataset.prev}|`)).forEach(c => delete prevEdicoes[c]);
    prevSalvar(); prevRecalcularTodas();
}
function previsaoAplicarVisibilidade() {
    // cada aba tem o seu botão: o da aba Forecast não esconde a coluna nas Indiretas, e vice-versa
    [['#view-forecast', prevOculta], ['#view-indiretas', prevOcultaInd]].forEach(([vista, oculta]) => {
        document.querySelectorAll(`${vista} table.tabela-previsao`).forEach(t => t.classList.toggle('prev-sem-forecast', oculta));
        document.querySelectorAll(`${vista} .btn-prev-toggle`).forEach(b => { b.textContent = oculta ? 'Mostrar forecast' : 'Ocultar forecast'; });
        document.querySelectorAll(`${vista} .btn-prev-restaurar`).forEach(b => { b.style.display = oculta ? 'none' : ''; });
    });
}
function previsaoAlternar(botao) {
    if (botao && botao.closest && botao.closest('#view-indiretas')) prevOcultaInd = !prevOcultaInd;
    else prevOculta = !prevOculta;
    prevSalvar(); previsaoAplicarVisibilidade();
    configAlterada();
}
prevRecalcularTodas(); previsaoAplicarVisibilidade();


// Diretas: por padrão só as colunas principais; o botão mostra as demais (dias de leitura, Δ absolutos, volume médio)
function alternarColunas() {
    configAlterada();
    const v = document.getElementById('view-tabelas'), compacto = v.classList.toggle('compacto');
    document.getElementById('btn-colunas').textContent = compacto ? 'Mostrar todas as colunas' : 'Mostrar só as principais';
    v.querySelectorAll('th[data-full]').forEach(th => { th.colSpan = parseInt(compacto ? th.dataset.comp : th.dataset.full, 10); });
    v.querySelectorAll('th[data-full]').forEach(th => { if (compacto) th.colSpan = parseInt(th.dataset.comp, 10); });
}
document.querySelectorAll('#view-tabelas th[data-full]').forEach(th => { th.colSpan = parseInt(th.dataset.comp, 10); });


// ===== Relatório executivo (PDF): copia o que está na tela agora — filtros, orçado escolhido e botões de ocultar valem =====
// modo 'celular' (padrão): folha em pé na largura do celular, letra grande e tabelas só com as colunas principais;
// modo 'a4': folhas A4 deitadas, com todas as colunas (para imprimir)
function gerarExecutivo(libs, modo) {
    const celular = modo !== 'a4';
    const antigo = document.getElementById('view-executivo'); if (antigo) antigo.remove();
    const cont = document.createElement('div'); cont.id = 'view-executivo';
    if (document.getElementById('view-tabelas').classList.contains('compacto')) cont.classList.add('compacto');
    if (celular) cont.classList.add('exec-celular');
    // gráfico: vira imagem do que está desenhado; no celular é redesenhado estreito (letras do mesmo tamanho da tela)
    const fotoGrafico = (cv) => {
        const ch = celular && window.Chart && Chart.getChart ? Chart.getChart(cv) : null;
        if (!ch) return cv.toDataURL('image/png');
        const dpr = ch.options.devicePixelRatio;
        try { ch.options.devicePixelRatio = 3; ch.resize(EXEC_CEL_W - 40, 340); return ch.toBase64Image('image/png'); }
        finally { ch.options.devicePixelRatio = dpr; ch.resize(); }
    };
    const clona = (el) => {
        if (!el) return null;
        const c = el.cloneNode(true), origs = el.querySelectorAll('canvas'), copias = c.querySelectorAll('canvas');
        origs.forEach((cv, i) => {
            try { const img = new Image(); img.src = fotoGrafico(cv); img.className = 'exec-grafico'; copias[i].replaceWith(img); }
            catch (e) { copias[i].remove(); }
        });
        c.querySelectorAll('script').forEach(x => x.remove());          // só o conteúdo: nada roda no documento do PDF
        c.querySelectorAll('.dias-uteis').forEach(x => x.remove());     // no PDF vai só a tabela do forecast (sem o painel de dias úteis)
        c.querySelectorAll('[contenteditable]').forEach(x => x.removeAttribute('contenteditable'));
        c.querySelectorAll('.jg-col').forEach((col) => { const t = col.querySelector('.jg-txt'); if (t && !t.textContent.trim()) col.remove(); });
        c.querySelectorAll('.jg').forEach((b) => { const n = b.querySelectorAll('.jg-col').length; if (!n) b.remove(); else if (n === 1) b.querySelector('.jg-cols').classList.add('um'); });
        c.querySelectorAll('.btn-remover-item').forEach(x => x.remove());
        c.querySelectorAll('[id]').forEach(x => x.removeAttribute('id'));
        c.removeAttribute('id');
        if (celular) c.querySelectorAll('table').forEach(enxugaTabelaCelular);
        return c;
    };
    const q = (sel) => document.querySelector(sel), qa = (sel) => Array.from(document.querySelectorAll(sel));
    const sup = ESTADO.sup, mes = ESTADO.mes;
    const nomeSup = (q('#selSup option[value="' + sup + '"]') || {}).textContent || sup;
    const nomeMes = (q('#selMes option[value="' + mes + '"]') || {}).textContent || mes;
    const marcados = qa('.chk-grupo:checked').length, grupos = qa('.chk-grupo').length;
    const refs = (ESTADO.ref || '').replace(/^cmp:/, '').split('|').filter(Boolean).join(' e ') || 'todas';
    const titulo = (q('.header-exec h1') || {}).textContent || '';
    const cab = document.createElement('div'); cab.className = 'exec-cabecalho';
    cab.innerHTML = `<div class="exec-marca">Águas do Rio · Relatório Executivo</div><h1></h1><p></p>`;
    cab.querySelector('h1').textContent = titulo;
    cab.querySelector('p').textContent = `Superintendência: ${nomeSup} · Mês: ${nomeMes} · Orçado comparado: ${refs} · Grupos: ` +
        (marcados === grupos ? `todos (${grupos})` : `${marcados} de ${grupos}`) + ` · Gerado em ${new Date().toLocaleString('pt-BR')}`;
    cont.appendChild(cab);
    const card = (sel) => (q(sel) || { closest: () => null }).closest('.card');
    // seções do PDF: título (começa página nova) + os quadros daquela seção; seção sem quadro não entra
    const secoes = [
        [null, [q('#view-resumo .kpis-grid'), card('#graficoFaturamento')]],
        ['DRE - Forecast', [q(`#view-forecast .prev-bloco[data-sup="${sup}"] .prev-card`)]],
        ['Orçado x Realizado', qa('#view-tabelas .orc-ciclo-bloco:not([hidden]) > .card')],
        ['Faturamento Mês a Mês', [card('#tabela-agua'), card('#tabela-esgoto')]],
        ['Indiretas', qa(`#view-indiretas .sup-bloco[data-sup="${sup}"][data-mes="${mes}"] .prev-card`)],
        ['Plano de Ação', [q('#plano-card.tem-dados')]],
        ['Análise de Ciclo', [q('#card-justificativa')]],         // título só no PDF, em cima das justificativas
    ];
    // justificativas: cada grupo vira um bloco próprio no PDF — a quebra de página cai entre grupos, sem cortar o texto
    const separaGrupos = (c) => {
        const blocos = c.querySelectorAll ? Array.from(c.querySelectorAll('.jg')) : [];
        if (!blocos.length) return [c];
        blocos.forEach((b) => b.remove());
        return [c].concat(blocos.map((b) => { const w = document.createElement('div'); w.className = 'exec-just-bloco'; w.appendChild(b); return w; }));
    };
    secoes.forEach(([nome, els]) => {
        const copias = els.map(clona).filter(Boolean).flatMap(separaGrupos);
        if (!copias.length) return;
        if (nome) {
            const t = document.createElement('div'); t.className = 'exec-secao';
            const h = document.createElement('h2'); h.textContent = nome; t.appendChild(h);
            cont.appendChild(t);
        }
        copias.forEach(c => { c.classList.add('exec-item'); cont.appendChild(c); });
    });
    // PDF gerado direto (arquivo .pdf baixado, sem a janela de impressão); sem as bibliotecas, cai na impressão
    obterLibsPdf(libs).then(l => (l ? gerarPdfDireto(cont, l, `Executivo_${sup}_${nomeMes}` + (celular ? '_celular' : '')) : Promise.reject(new Error('sem bibliotecas'))))
        .catch(erro => { console.warn('PDF direto indisponível, usando a impressão:', erro); imprimirDocumentoLeve(cont); });
}

const EXEC_CEL_W = 430;      // largura (px) da folha do Executivo para celular: as letras ficam do tamanho da tela do telefone

// Executivo no celular: as tabelas largas ficam só com as colunas principais.
// Comparativos (mês a mês e orçado por ciclo): Grupo, Faturamento (atual/realizado e anterior/orçado) e Δ Fat. (Abs e %).
// Forecast e indiretas: sai a coluna de diferença em valor (Δ R$ / Δ eventos); fica o Δ %.
function enxugaTabelaCelular(t) {
    // grade da tabela: cada célula com a coluna em que começa e quantas ocupa (considera colspan e rowspan)
    const celulas = [], ocupadas = [];
    Array.from(t.rows).forEach((tr, r) => {
        let col = 0;
        Array.from(tr.cells).forEach((td) => {
            while (ocupadas[r] && ocupadas[r][col]) col++;
            const span = td.colSpan || 1, rs = td.rowSpan || 1;
            for (let i = 0; i < rs; i++) for (let j = 0; j < span; j++) (ocupadas[r + i] = ocupadas[r + i] || [])[col + j] = true;
            celulas.push({ td, col, span, cab: td.tagName === 'TH' && !!td.closest('thead') });
            col += span;
        });
    });
    const nCols = Math.max(0, ...ocupadas.map(l => (l || []).length));
    // rótulo de cada coluna: os títulos do cabeçalho que a cobrem (ex.: "Δ Fat. %")
    const rotulos = Array.from({ length: nCols }, () => []);
    celulas.filter(c => c.cab).forEach(c => { for (let j = 0; j < c.span; j++) rotulos[c.col + j].push(c.td.textContent.replace(/\s+/g, ' ').trim()); });
    const rot = rotulos.map(l => l.join(' '));
    let manter;
    if (t.classList.contains('tabela-comparativo')) manter = (r) => /^(Grupo|Faturamento |Δ Fat\.)/.test(r);
    else if (t.querySelector('th[data-tipo="dreal"]')) manter = (r) => !/^Δ (R\$|eventos)/.test(r);
    else return;
    const fica = rot.map(manter);
    if (!fica.some(Boolean) || fica.every(Boolean)) return;
    celulas.forEach(({ td, col, span }) => {
        let n = 0; for (let j = 0; j < span; j++) if (fica[col + j]) n++;
        if (!n) td.remove(); else if (n < span) td.colSpan = n;
    });
    t.classList.add('exec-enxuta');
}

// jsPDF + html2canvas: o código das bibliotecas vem do site (pasta lib/, passado pelo botão do site como texto);
// no relatório salvo como arquivo, vêm do CDN. Elas rodam DENTRO do documento do PDF (o html2canvas só desenha bem
// elementos do próprio documento). Devolve [{codigo} ou {src}] ou null.
function obterLibsPdf(libs) {
    if (libs && libs.codigo && libs.codigo.length === 2) return Promise.resolve(libs.codigo.map(c => ({ codigo: c })));
    const base = 'https://cdnjs.cloudflare.com/ajax/libs/';
    return Promise.resolve([{ src: base + 'jspdf/2.5.2/jspdf.umd.min.js' }, { src: base + 'html2canvas/1.4.1/html2canvas.min.js' }]);
}

function injetaLibs(doc, libs) {
    return Promise.all(libs.map(l => new Promise((ok, erro) => {
        const sc = doc.createElement('script');
        if (l.codigo) { sc.textContent = l.codigo; doc.head.appendChild(sc); ok(); return; }
        sc.src = l.src; sc.onload = ok; sc.onerror = () => erro(new Error('não carregou ' + l.src));
        doc.head.appendChild(sc);
    })));
}

// Gera o PDF do Executivo e baixa o arquivo: cada quadro vira imagem (html2canvas) e é paginado em A4 paisagem (jsPDF).
// Cada título de seção começa uma página; quadro maior que a página é dividido em partes.
async function gerarPdfDireto(cont, libs, nome) {
    const aviso = document.createElement('div');
    aviso.textContent = 'Gerando o PDF executivo…';
    aviso.style.cssText = 'position:fixed; right:16px; bottom:16px; z-index:99999; background:#1A2740; color:#fff; padding:10px 16px; border-radius:8px; font:600 13px sans-serif; box-shadow:0 6px 20px rgba(0,0,0,.25);';
    document.body.appendChild(aviso);
    const fr = document.createElement('iframe');
    fr.setAttribute('aria-hidden', 'true'); fr.title = 'Executivo';
    // largura de uma folha A4 paisagem (281 mm úteis a 96 dpi): as letras saem do mesmo tamanho da impressão
    // dentro da tela (transparente e atrás de tudo): fora dela o html2canvas desenha a página em branco
    // no celular, a largura da tela de um telefone (EXEC_CEL_W)
    const celular = cont.classList.contains('exec-celular'), larguraBase = celular ? EXEC_CEL_W : 1062;
    fr.style.cssText = `position:fixed; left:0; top:0; width:${larguraBase}px; height:800px; border:0; opacity:0; pointer-events:none; z-index:-1;`;
    document.body.appendChild(fr);
    try {
        const doc = fr.contentDocument;
        doc.open(); doc.write(montaDocumentoExecutivo(cont, true)); doc.close();
        const imgs = Array.from(doc.images);
        await Promise.race([Promise.all([...imgs.map(i => i.complete ? null : new Promise(r => { i.onload = i.onerror = r; })),
            doc.fonts && doc.fonts.ready ? doc.fonts.ready.catch(() => null) : null]), new Promise(r => setTimeout(r, 4000))]);
        // tabela mais larga que a folha (ex.: orçado por ciclo com Abs e %): alarga o documento para caber inteira;
        // a imagem depois é reduzida para a largura da página
        // no celular, a tabela que ainda não cabe diminui a letra (até 9px) antes de alargar a folha
        if (celular) doc.querySelectorAll('#view-executivo table').forEach(t => {
            const cabe = () => t.scrollWidth <= t.parentElement.clientWidth + 1;
            for (let px = 11; px >= 9 && !cabe(); px--) t.style.fontSize = px + 'px';
        });
        let largura = larguraBase;
        doc.querySelectorAll('#view-executivo table').forEach(t => { largura = Math.max(largura, Math.ceil(t.scrollWidth) + (celular ? 24 : 48)); });
        if (largura > larguraBase) { fr.style.width = largura + 'px'; await new Promise(r => setTimeout(r, 50)); }
        await Promise.race([injetaLibs(doc, libs), new Promise((_, r) => setTimeout(() => r(new Error('bibliotecas do PDF demoraram')), 15000))]);
        const w = fr.contentWindow;
        if (!w.jspdf || !w.html2canvas) throw new Error('bibliotecas do PDF indisponíveis');
        const raiz = doc.getElementById('view-executivo') || doc.body.firstElementChild;
        // uma única "foto" do Executivo inteiro (rápido); depois cada quadro é recortado dela pela posição.
        // As posições são medidas na CÓPIA que o html2canvas desenha (onclone), não no documento original: em alguns
        // computadores (barra de rolagem, escala do Windows, fontes) a cópia quebra o texto diferente, os quadros ficam
        // com outra altura e o recorte "escorregava" — o título da seção seguinte ia parar no fim da página anterior.
        // celular: imagem mais fina (a tela do telefone tem mais pontos), sem passar do limite de altura de um canvas (~32 mil px)
        const ESC = celular ? Math.max(1, Math.min(3, Math.floor(300000 / Math.max(1, raiz.scrollHeight + 100)) / 10)) : 2;
        let medidas = null;
        const foto = await w.html2canvas(raiz, { scale: ESC, backgroundColor: '#FFFFFF', logging: false, imageTimeout: 3000,
            windowWidth: largura, windowHeight: Math.max(800, Math.ceil(raiz.scrollHeight) + 100),
            onclone: (d) => {
                d.documentElement.style.overflow = 'hidden'; d.body.style.overflow = 'hidden';     // sem barra de rolagem na cópia
                const rc = d.getElementById('view-executivo') || d.body.firstElementChild, b0 = rc.getBoundingClientRect();
                medidas = { altura: b0.height, itens: Array.from(rc.children).map(el => {
                    const r = el.getBoundingClientRect(); return { topo: r.top - b0.top, alt: r.height }; }) };
            } });
        const r0 = raiz.getBoundingClientRect();
        const filhos = Array.from(raiz.children);
        // px da cópia → px da foto (a foto tem a altura da cópia × escala)
        const kFoto = medidas && medidas.altura ? foto.height / medidas.altura : ESC;
        const posicao = (el, i) => {
            const m = medidas && medidas.itens.length === filhos.length ? medidas.itens[i] : null;
            if (m) return { topo: m.topo * kFoto, altPx: m.alt * kFoto };
            const r = el.getBoundingClientRect();
            return { topo: (r.top - r0.top) * ESC, altPx: r.height * ESC };
        };
        const recorte = (topoPx, altPx) => {
            const c = document.createElement('canvas'); c.width = foto.width; c.height = Math.max(1, Math.round(altPx));
            c.getContext('2d').drawImage(foto, 0, Math.round(topoPx), foto.width, c.height, 0, 0, foto.width, c.height);
            return c.toDataURL('image/jpeg', 0.92);
        };
        const pdf = celular ? paginaCelular(w, foto, filhos, posicao, recorte) : null;
        if (pdf) { baixaPdf(pdf, nome); return; }
        const pdf4 = new w.jspdf.jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4', compress: true });
        const W = 297, H = 210, M = 8, LW = W - 2 * M, LH = H - 2 * M - 6;       // 6 mm do rodapé
        let y = M, primeira = true;
        const novaPagina = () => { pdf4.addPage(); y = M; };
        const mmPorPx = LW / foto.width;
        for (const [i, el] of filhos.entries()) {
            const { topo, altPx } = posicao(el, i);
            if (!altPx) continue;
            const alt = altPx * mmPorPx;
            if (el.classList.contains('exec-secao') && !primeira && y > M) novaPagina();
            if (alt <= LH) {
                if (y + alt > M + LH) novaPagina();
                pdf4.addImage(recorte(topo, altPx), 'JPEG', M, y, LW, alt);
                y += alt + 3;
            } else {                                                  // quadro mais alto que a página: fatias de uma página
                // começa logo abaixo do que já está na página (ex.: o título da seção) — antes pulava para a página
                // seguinte e deixava o título sozinho numa página em branco
                if (M + LH - y < LH * 0.3) novaPagina();
                let d = 0;
                while (d < altPx) {
                    const h = Math.min(Math.floor((M + LH - y) / mmPorPx), altPx - d);
                    if (h < 20) { novaPagina(); continue; }               // sem espaço nesta página: segue na próxima
                    pdf4.addImage(recorte(topo + d, h), 'JPEG', M, y, LW, h * mmPorPx);
                    y += h * mmPorPx + 3; d += h;
                    if (d < altPx) novaPagina();
                }
            }
            primeira = false;
        }
        const total = pdf4.getNumberOfPages();
        for (let i = 1; i <= total; i++) {                            // rodapé: página X de N
            pdf4.setPage(i); pdf4.setFontSize(8); pdf4.setTextColor(73, 102, 140);
            pdf4.text(`Águas do Rio · Relatório Executivo · página ${i} de ${total}`, W - M, H - 5, { align: 'right' });
        }
        baixaPdf(pdf4, nome);
    } finally {
        fr.remove(); aviso.remove();
    }
}

// baixa pelo documento do relatório (o iframe do PDF é removido logo depois; um clique dentro dele cancelaria o download)
function baixaPdf(pdf, nome) {
    const url = URL.createObjectURL(new Blob([pdf.output('blob')], { type: 'application/pdf' }));
    const a = document.createElement('a');
    a.href = url; a.download = String(nome).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Za-z0-9_-]+/g, '_') + '.pdf';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
}

// Executivo no celular: folhas em pé, na largura do telefone, sem espaço em branco. Cada seção é uma folha com a altura
// do seu conteúdo (o leitor de PDF do celular mostra a folha na largura da tela e a pessoa só rola para baixo).
// Seção muito comprida é dividida entre quadros; quadro sozinho mais alto que o limite é fatiado.
function paginaCelular(w, foto, filhos, posicao, recorte) {
    const PW = 120, M = 4, RODAPE = 7, LW = PW - 2 * M, mmPorPx = LW / foto.width;
    const MAX = 1400;                                              // altura máxima de uma folha (mm); o PDF aceita até ~5000
    // grupos: o cabeçalho com os indicadores, depois um por título de seção
    const grupos = [];
    filhos.forEach((el, i) => {
        const p = posicao(el, i); if (!p.altPx) return;
        if (!grupos.length || el.classList.contains('exec-secao')) grupos.push([]);
        grupos[grupos.length - 1].push(p);
    });
    // folhas: [{ partes: [{topo, altPx}] }]; cada parte é um recorte contínuo da foto
    const folhas = [];
    const maxPx = (MAX - 2 * M - RODAPE) / mmPorPx;
    grupos.forEach((g) => {
        let atual = null;
        g.forEach((p) => {
            const fim = p.topo + p.altPx;
            if (atual && fim - atual.topo <= maxPx) { atual.fim = fim; return; }
            if (atual) folhas.push(atual);
            if (p.altPx <= maxPx) { atual = { topo: p.topo, fim }; return; }
            for (let d = 0; d < p.altPx; d += maxPx) folhas.push({ topo: p.topo + d, fim: Math.min(fim, p.topo + d + maxPx) });
            atual = null;
        });
        if (atual) folhas.push(atual);
    });
    if (!folhas.length) return null;
    const alturaMm = (f) => (f.fim - f.topo) * mmPorPx + 2 * M + RODAPE;
    // orientação pela forma da folha: folha mais baixa que larga (seção curta) com "portrait" fazia o jsPDF trocar
    // largura e altura — a folha ficava estreita e cortava a tabela e o rodapé à direita
    const orient = (ph) => (ph >= PW ? 'portrait' : 'landscape');
    const pdf = new w.jspdf.jsPDF({ orientation: orient(alturaMm(folhas[0])), unit: 'mm', format: [PW, alturaMm(folhas[0])], compress: true });
    folhas.forEach((f, i) => {
        const PH = alturaMm(f);
        if (i) pdf.addPage([PW, PH], orient(PH));
        pdf.addImage(recorte(f.topo, f.fim - f.topo), 'JPEG', M, M, LW, (f.fim - f.topo) * mmPorPx);
        pdf.setFontSize(7); pdf.setTextColor(73, 102, 140);
        pdf.text(`Águas do Rio · Relatório Executivo · ${i + 1} de ${folhas.length}`, PW - M, PH - 3.5, { align: 'right' });
    });
    return pdf;
}

// Imprime só o conteúdo do Executivo num documento à parte (iframe escondido), com os estilos do relatório.
// Imprimir o relatório inteiro (vários MB com as bases embutidas) fazia a visualização de impressão falhar e o PDF
// salvo sair corrompido ("Não é possível abrir este arquivo").
function montaDocumentoExecutivo(cont, telaComoImpressao) {
    let estilos = Array.from(document.querySelectorAll('style')).map(s => s.textContent).join('\n');
    // PDF direto: o documento é desenhado na tela, então as regras de impressão do Executivo passam a valer na tela também
    if (telaComoImpressao) estilos = estilos.replace(/@media\s+print/g, '@media all') +
        '\n#view-executivo .card, #view-executivo .tabela-wrap { overflow: visible !important; }' +   // nada cortado na foto
        '\nhtml, body { overflow: hidden !important; }';            // sem barra de rolagem: a largura não muda entre documento e foto
    const fontes = telaComoImpressao ? '' : Array.from(document.querySelectorAll('link[rel="stylesheet"], link[rel="preconnect"]')).map(l => l.outerHTML).join('');
    return '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><title>' +
        (document.title || 'Relatório Executivo').replace(/</g, '&lt;') + ' — Executivo</title>' + fontes +
        '<style>' + estilos + '\n#view-executivo{display:block !important}</style></head>' +
        // PDF direto: sem a classe modo-executivo — a regra dela esconde todo filho do <body>, inclusive o quadro de
        // trabalho que o html2canvas coloca ali (a página saía em branco)
        (telaComoImpressao ? '<body>' : '<body class="modo-executivo">') +
        cont.outerHTML + '</body></html>';
}

function imprimirDocumentoLeve(cont) {
    const antigo = document.getElementById('frame-executivo'); if (antigo) antigo.remove();
    const fr = document.createElement('iframe');
    fr.id = 'frame-executivo'; fr.setAttribute('aria-hidden', 'true'); fr.title = 'Executivo';
    fr.style.cssText = 'position:fixed; right:0; bottom:0; width:1px; height:1px; border:0; opacity:0; pointer-events:none;';
    document.body.appendChild(fr);
    const doc = fr.contentDocument;
    doc.open(); doc.write(montaDocumentoExecutivo(cont)); doc.close();
    const imgs = Array.from(doc.images);
    const prontas = Promise.all(imgs.map(i => i.complete ? null : new Promise(r => { i.onload = i.onerror = r; })));
    const fontes = doc.fonts && doc.fonts.ready ? doc.fonts.ready.catch(() => null) : null;
    Promise.race([Promise.all([prontas, fontes]), new Promise(r => setTimeout(r, 3000))]).then(() => {
        const w = fr.contentWindow;
        const tira = () => setTimeout(() => fr.remove(), 1000);
        w.addEventListener('afterprint', tira);
        w.focus();
        w.print();
        setTimeout(() => { if (document.body.contains(fr)) fr.remove(); }, 120000);   // garantia, se afterprint não vier
    });
}

// ===== Situação do grupo (aba Diretas): o selo é editável — a escolha manual vale para o grupo em todas as tabelas =====
// Guardada no navegador por mês (como as edições do forecast); "Automático" volta à regra (LIS / Aguardando / Em Análise / Liberado).
const SIT_LS = 'faturamento_situacao_grupo';
const SIT_OPCOES = ['Liberado', 'Em Análise', 'LIS', 'Aguardando'];
const SIT_CLASSE = { 'Liberado': 'sit-liberado', 'Em Análise': 'sit-analise', 'LIS': 'sit-lis', 'Aguardando': 'sit-aguardando' };
let sitManuais = {};
try { sitManuais = JSON.parse(localStorage.getItem(SIT_LS) || '{}') || {}; } catch (e) { /* sem armazenamento: vale só nesta abertura */ }
function sitSalvar() {
    try { localStorage.setItem(SIT_LS, JSON.stringify(sitManuais)); } catch (e) { /* ignora */ }
    if (typeof garDesenharResumo === 'function') setTimeout(garDesenharResumo, 0);     // "Somente grupos liberados" acompanha
    if (typeof syncSituacao !== 'undefined') syncSituacao.agendar();
}
function sitAplicar(el) {
    const auto = el.dataset.sitAuto, man = (sitManuais[el.dataset.sitRef] || {})[el.dataset.sitGrupo];
    const v = man || auto;
    el.className = 'sit-grupo ' + (SIT_CLASSE[v] || '') + (man ? ' sit-manual' : '');
    el.textContent = v;
    if (man) { const l = document.createElement('span'); l.className = 'sit-lapis'; l.textContent = ' ✎'; el.appendChild(l); }
    el.title = man ? `Alterada manualmente (automática: ${auto}) — clique para mudar` : 'Situação automática — clique para alterar';
}
function sitAplicarGrupo(ref, grupo) {
    document.querySelectorAll('.sit-grupo[data-sit-grupo]').forEach(el => {
        if (el.dataset.sitRef === ref && el.dataset.sitGrupo === grupo) sitAplicar(el);
    });
}
document.querySelectorAll('.sit-grupo[data-sit-grupo]').forEach(sitAplicar);
// Grupos que abrem marcados: os Liberados e os Em Análise (situação manual, se houver, senão a automática). Vale até a
// pessoa mexer no filtro de grupos nesta abertura (gruposAuto = false).
window.gruposAuto = true;
function gruposPadrao() {
    const ok = new Set(), vistos = new Set();
    document.querySelectorAll('.sit-grupo[data-sit-grupo]').forEach((el) => {
        const g = el.dataset.sitGrupo, man = (sitManuais[el.dataset.sitRef] || {})[g], v = man || el.dataset.sitAuto;
        vistos.add(g); if (v === 'Liberado' || v === 'Em Análise') ok.add(g);
    });
    return vistos.size && ok.size ? ok : null;                     // sem situação nos dados: todos marcados
}
// grupos com situação Liberado (manual, se houver, senão a automática) — chave "Somente grupos liberados" do Resumo de Ganhos
function gruposLiberados() {
    const ok = new Set();
    document.querySelectorAll('.sit-grupo[data-sit-grupo]').forEach((el) => {
        const g = el.dataset.sitGrupo, man = (sitManuais[el.dataset.sitRef] || {})[g];
        if ((man || el.dataset.sitAuto) === 'Liberado') ok.add(g);
    });
    return ok;
}
window.aplicarGruposPadrao = function () {
    const ok = gruposPadrao();
    document.querySelectorAll('.chk-grupo').forEach((c) => { c.checked = !ok || ok.has(normGrupo(c.value)); });
    if (typeof filtrarPorGrupo === 'function') filtrarPorGrupo();
    try { const p = window.parent; if (p && p !== window && p.sincronizaGruposTopo) p.sincronizaGruposTopo(); } catch (e) {}
};
function sitEditar(el) {
    if (el.nextElementSibling && el.nextElementSibling.classList.contains('sit-escolha')) return;
    const ref = el.dataset.sitRef, grupo = el.dataset.sitGrupo, man = (sitManuais[ref] || {})[grupo] || '';
    const sel = document.createElement('select');
    sel.className = 'sit-escolha';
    sel.setAttribute('aria-label', 'Situação do grupo ' + grupo);
    [['', `Automático (${el.dataset.sitAuto})`]].concat(SIT_OPCOES.map(o => [o, o])).forEach(([v, t]) => {
        const op = document.createElement('option'); op.value = v; op.textContent = t; if (v === man) op.selected = true; sel.appendChild(op);
    });
    let fechada = false;
    const fecha = () => { if (fechada) return; fechada = true; sel.remove(); el.style.display = ''; };
    sel.addEventListener('change', () => {
        const m = sitManuais[ref] = sitManuais[ref] || {};
        if (sel.value) m[grupo] = sel.value; else delete m[grupo];
        if (!Object.keys(m).length) delete sitManuais[ref];
        sitSalvar(); sitAplicarGrupo(ref, grupo); fecha();
    });
    sel.addEventListener('blur', fecha);
    sel.addEventListener('keydown', ev => { if (ev.key === 'Escape') fecha(); });
    el.style.display = 'none';
    el.after(sel);
    sel.focus();
}
document.addEventListener('click', e => {
    const el = e.target.closest && e.target.closest('.sit-grupo[data-sit-grupo]');
    if (el) sitEditar(el);
});
document.addEventListener('keydown', e => {
    const el = e.target.closest && e.target.closest('.sit-grupo[data-sit-grupo]');
    if (el && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); sitEditar(el); }
});


// ===== Ajustes compartilhados na pasta do SharePoint (forecast editado e Situação dos grupos) =====
// Com o relatório aberto pelo site e a pasta conectada, cada alteração vai para ajustes_relatorio.json na pasta (o OneDrive
// sincroniza): quem abrir a mesma pasta vê os mesmos valores. Ao gravar, só as chaves alteradas aqui entram no arquivo
// (o que outra pessoa mudou em outras linhas é mantido). A cada minuto o relatório relê o arquivo.
function compartilhado() {
    try { const p = window.parent; if (p && p !== window && p.arquivoCompartilhado && p.arquivoCompartilhado.disponivel()) return p.arquivoCompartilhado; }
    catch (e) { /* relatório aberto fora do site */ }
    return ajustesCopia() ? COPIA_LEITURA : null;
}
// Nuvem ao lado da versão (no site): ✓ quando tudo foi salvo na pasta, ✕ quando alguma alteração ficou só aqui.
const pendentesNuvem = new Set();
function marcaNuvem(nome, r) {
    const comp = compartilhado();
    if (r.ok) pendentesNuvem.delete(nome); else pendentesNuvem.add(nome);
    avisoNuvem(r.ok ? `${nome}: alteração salva na pasta "${comp ? comp.pasta() : ''}" — vale para todos` : `${nome}: salvo só neste navegador (${r.motivo})`, !r.ok);
    try {
        const p = window.parent;
        if (p && p !== window && p.estadoNuvem) p.estadoNuvem(!pendentesNuvem.size,
            pendentesNuvem.size ? `Não salvo na pasta: ${Array.from(pendentesNuvem).join(', ')}` : `Tudo salvo na pasta "${comp ? comp.pasta() : ''}"`);
    } catch (e) { /* relatório aberto fora do site */ }
}
// clique na nuvem: grava tudo o que está na tela e relê a pasta; devolve true se tudo foi salvo
window.sincronizarTudo = async function () {
    if (!compartilhado()) return false;
    const r = [await syncForecast.empurrar(), await syncSituacao.empurrar(), await syncGarantia.empurrar(), await syncPlano.empurrar(), await syncOnePage.empurrar(), await salvarJustificativas()];
    puxarAjustesCompartilhados(); lerJustificativasDaPasta();
    return r.every(Boolean);
};
function avisoNuvem(texto, erro) {
    let el = document.getElementById('avisoNuvem');
    if (!el) { el = document.createElement('div'); el.id = 'avisoNuvem'; document.body.appendChild(el); }
    el.textContent = texto; el.className = erro ? 'erro' : ''; el.style.display = 'block';
    clearTimeout(avisoNuvem.t); avisoNuvem.t = setTimeout(() => { el.style.display = 'none'; }, erro ? 9000 : 5000);
}
const igualJson = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const copiaJson = (o) => JSON.parse(JSON.stringify(o || {}));
function criaSync(secao, nome, obter, definir, redesenhar, ocupado) {
    let base = null, timer = null;
    async function puxar() {
        const comp = compartilhado();
        if (!comp || (ocupado && ocupado()) || timer || pendentesNuvem.has(nome)) return;   // não atropela o que ainda vai ser salvo
        const d = await comp.ler();
        if (!d) return;
        if (!d[secao]) { if (base === null) base = {}; return; }   // nunca salvo na pasta: fica o que há neste navegador
        const remoto = d[secao].mapa || {};
        if (!igualJson(remoto, obter())) {
            definir(copiaJson(remoto)); redesenhar();
            if (base !== null) avisoNuvem(`${nome}: atualizado com alterações salvas por outra pessoa`);
        }
        base = copiaJson(remoto);
    }
    async function empurrar() {
        const comp = compartilhado();
        if (!comp) return false;
        const atual = copiaJson(obter()), antes = base || {};
        const r = await comp.atualizar((d) => {
            const sec = d[secao] = d[secao] || { mapa: {} }, m = sec.mapa = sec.mapa || {};
            new Set([...Object.keys(atual), ...Object.keys(antes)]).forEach(k => {
                if (!(k in atual)) delete m[k];
                else if (!igualJson(atual[k], antes[k])) m[k] = atual[k];
            });
            sec.atualizado = new Date().toISOString();
        });
        if (r.ok) {
            base = copiaJson(r.dados[secao].mapa);
            if (!igualJson(base, obter())) { definir(copiaJson(base)); redesenhar(); }
        }
        marcaNuvem(nome, r);
        return r.ok;
    }
    return {
        puxar, empurrar,
        agendar() { clearTimeout(timer); timer = setTimeout(() => { timer = null; empurrar(); }, 700); },
    };
}
var syncForecast = criaSync('forecast', 'Forecast', () => prevEdicoes,
    (m) => { prevEdicoes = m; try { localStorage.setItem(PREV_CHAVE_LS, JSON.stringify({ edicoes: prevEdicoes, oculta: prevOculta, ocultaInd: prevOcultaInd })); } catch (e) {} },
    () => prevRecalcularTodas(),
    () => document.activeElement && document.activeElement.classList && document.activeElement.classList.contains('p-prev'));
var syncSituacao = criaSync('situacao', 'Situação do grupo',
    () => { const plano = {}; Object.entries(sitManuais).forEach(([ref, gs]) => Object.entries(gs).forEach(([g, v]) => { plano[ref + '|' + g] = v; })); return plano; },
    (plano) => { sitManuais = {}; Object.entries(plano).forEach(([k, v]) => { const i = k.lastIndexOf('|'); (sitManuais[k.slice(0, i)] = sitManuais[k.slice(0, i)] || {})[k.slice(i + 1)] = v; });
                 try { localStorage.setItem(SIT_LS, JSON.stringify(sitManuais)); } catch (e) {} },
    () => { document.querySelectorAll('.sit-grupo[data-sit-grupo]').forEach(sitAplicar);
            if (window.gruposAuto) window.aplicarGruposPadrao(); },        // situação manual chegou da pasta: refaz os grupos padrão
    () => !!document.querySelector('select.sit-escolha'));
function puxarAjustesCompartilhados() {
    syncForecast.puxar(); syncSituacao.puxar();
    if (typeof syncGarantia !== 'undefined') syncGarantia.puxar();
    if (typeof syncPlano !== 'undefined') syncPlano.puxar();
    if (typeof syncOnePage !== 'undefined') syncOnePage.puxar();
}
// chamado pelo site quando o arquivo da pasta mudou (outra pessoa salvou) ou ao voltar para a aba
window.puxarTudoDaPasta = function () { puxarAjustesCompartilhados(); lerJustificativasDaPasta(); };
puxarAjustesCompartilhados();
setInterval(puxarAjustesCompartilhados, 60000);


// ===== Preferências de visualização (de cada pessoa, neste navegador) =====
// Ocultar forecast (Forecast e Indiretas), Orçado por ciclo, visão Analítica/Sintética e Mostrar todas as colunas ficam
// salvos só aqui, na última escolha de cada um — mudar não altera a tela de mais ninguém. Superintendência, Comparar, Mês e
// Grupos são guardados pelo site (index.html), também por pessoa. O que é DADO (forecast editado, situação dos grupos,
// justificativas, garantia, plano de ação) continua no ajustes_relatorio.json da pasta, para todos.
const CONFIG_LS = 'faturamento_config_local';
let aplicandoConfig = false;
function lerConfig() {
    const sel = document.getElementById('selOrcCiclo'), vt = document.getElementById('view-tabelas');
    const sint = document.querySelector('.sitl-visao button[data-visao="sintetica"].ativo');
    return {
        ocultaForecast: !!prevOculta, ocultaIndiretas: !!prevOcultaInd,
        orcadoCiclo: sel ? sel.value : '',
        visaoSituacao: sint ? 'sintetica' : 'analitica',
        todasColunas: vt ? !vt.classList.contains('compacto') : false,
    };
}
function configAlterada() {
    if (aplicandoConfig) return;
    try { localStorage.setItem(CONFIG_LS, JSON.stringify(lerConfig())); } catch (e) { /* sem armazenamento */ }
}
function aplicarConfig(c) {
    aplicandoConfig = true;
    try {
        if ('ocultaForecast' in c || 'ocultaIndiretas' in c) {
            prevOculta = !!c.ocultaForecast; prevOcultaInd = !!c.ocultaIndiretas;
            try { localStorage.setItem(PREV_CHAVE_LS, JSON.stringify({ edicoes: prevEdicoes, oculta: prevOculta, ocultaInd: prevOcultaInd })); } catch (e) {}
            previsaoAplicarVisibilidade();
        }
        const sel = document.getElementById('selOrcCiclo');
        if (c.orcadoCiclo && sel && Array.from(sel.options).some(o => o.value === c.orcadoCiclo) && sel.value !== c.orcadoCiclo) selecionarOrcadoCiclo(c.orcadoCiclo);
        if (c.visaoSituacao) sitlVisao(c.visaoSituacao);
        const vt = document.getElementById('view-tabelas');
        if ('todasColunas' in c && vt && vt.classList.contains('compacto') === !!c.todasColunas) alternarColunas();
    } finally { aplicandoConfig = false; }
}
document.addEventListener('DOMContentLoaded', () => {
    let c = null; try { c = JSON.parse(localStorage.getItem(CONFIG_LS) || 'null'); } catch (e) { c = null; }
    if (c) aplicarConfig(c);
});

// ===== Aba Garantia: Top 1000 · Análise de Garantia · Resumo de Ganhos =====
// Dados (script#garantia-dados, JSON em gzip): uma linha por matrícula, já no ranking da média do faturado (R$) dos
// meses fechados. A análise manual (média do sistema, motivo, retorno, foto do faturado) fica em garItens e vai para a
// seção "garantia" do ajustes_relatorio.json — a mesma análise para todos.
const GAR = { dados: null, porLig: new Map(), ref: '', top: 1000, refs: [], tarifa: null, soAnalise: false, busca: [],
              ordem: { campo: 'rank', desc: false }, carregando: null };
const GAR_LS = 'faturamento_garantia';
let garItens = {};
try { garItens = JSON.parse(localStorage.getItem(GAR_LS) || '{}') || {}; } catch (e) { /* sem armazenamento */ }
const garEsc = (v) => String(v == null ? '' : v).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const garR = (v) => (v == null || isNaN(v) ? '–' : 'R$ ' + fmtBR(v, 2));
const garN = (v, d) => (v == null || isNaN(v) ? '–' : fmtBR(v, d || 0));
const garEmAnalise = (d) => !!d && (d.sit || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().trim() === 'EM ANALISE';
const garVar = (atual, media) => (atual == null || !media ? null : (atual - media) / media);

function garCarregar() {
    if (GAR.carregando) return GAR.carregando;
    GAR.carregando = (async () => {
        const el = document.getElementById('garantia-dados');
        if (!el) return null;
        const j = JSON.parse(new TextDecoder('utf-8').decode(await bytesEmbutidos(el)));
        GAR.ref = j.refAtual; GAR.top = j.top || 1000; GAR.refs = j.refs || [];
        GAR.dados = j.linhas.map((l) => Object.fromEntries(j.colunas.map((c, i) => [c, l[i]])));
        GAR.porLig = new Map(GAR.dados.map((d) => [String(d.lig), d]));
        GAR.lista = GAR.dados.filter((d) => d.rank && d.rank <= GAR.top);      // o Top 1000 (separado uma vez só)
        try { GAR.tarifa = JSON.parse(document.getElementById('tarifa-dados').textContent); } catch (e) { GAR.tarifa = null; }
        return GAR.dados;
    })();
    return GAR.carregando;
}
// filtro de grupos lido da tela uma vez por redesenho (ler para cada matrícula deixava a aba lenta)
let garGrupos = null;
function garVisivel(d) {
    if (!d) return true;                                         // matrícula digitada que não está na base do mês
    if (ESTADO.sup !== 'TODAS' && d.sup !== ESTADO.sup) return false;
    return !garGrupos || garGrupos.has(normGrupo(d.grupo));
}
const garEco = (d) => ({ res: d.res || 0, com: d.com || 0, ind: d.ind || 0, pub: d.pub || 0 });
function garCalculado(d, media) {
    if (!d || media == null || media === '' || !GAR.tarifa || !window.Tarifa) return null;
    return Tarifa.valor(GAR.tarifa, +media, d.cat, garEco(d), d.esg);
}

// --- Top 1000 ---
const GAR_COLS_TOP = [
    ['rank', '#', 'n'], ['lig', 'Matrícula', 't'], ['nome', 'Cliente', 't'], ['cat', 'Categoria', 't'], ['loc', 'Localidade', 't'],
    ['grupo', 'Grupo', 't'], ['sup', 'SUP', 't'], ['eco', 'Econ.', 'n'], ['mMed', 'Média cons. medido (m³)', 'n'],
    ['mCons', 'Média cons. faturado (m³)', 'n'], ['cons', 'Cons. faturado atual (m³)', 'n'], ['dCons', 'Δ% cons.', 'n'],
    ['mVal', 'Média faturado (R$)', 'n'], ['val', 'Faturado atual (R$)', 'n'], ['dVal', 'Δ% R$', 'n'], ['sit', 'Situação conta', 't'],
];
function garValorCol(d, c) {
    if (c === 'eco') return (d.res || 0) + (d.com || 0) + (d.ind || 0) + (d.pub || 0);
    if (c === 'dCons') return garVar(d.cons, d.mCons);
    if (c === 'dVal') return garVar(d.val, d.mVal);
    return d[c];
}
function garLinhasTop() {
    const busca = GAR.busca;                             // filtro por matrícula (parte do número; várias separadas por espaço)
    let ls = GAR.lista.filter((d) => garVisivel(d) && (!GAR.soAnalise || garEmAnalise(d)) && (!GAR_CAT_TOP.cats || GAR_CAT_TOP.cats.has(garCat(d)))
        && (!busca.length || busca.some((t) => String(d.lig).includes(t))));
    const { campo, desc } = GAR.ordem;
    const num = GAR_COLS_TOP.find((c) => c[0] === campo)?.[2] !== 't';
    ls.sort((a, b) => {
        let x = garValorCol(a, campo), y = garValorCol(b, campo);
        if (num) { x = x == null ? -Infinity : x; y = y == null ? -Infinity : y; return desc ? y - x : x - y; }
        return desc ? String(y || '').localeCompare(String(x || '')) : String(x || '').localeCompare(String(y || ''));
    });
    return ls;
}
// filtro de categoria (lista com caixas, como o filtro de grupos do cabeçalho): uma instância por sub-aba; cats null = todas
const garCat = (d) => String((d && d.cat) || '').trim() || '(sem categoria)';
function garFiltroCategoria(p, fonte, aoMudar) {
    // p: prefixo dos ids (p+'DD', p+'Btn', p+'Lista', p+'Todas'); fonte(): matrículas para contar; aoMudar(): redesenha
    const f = { cats: null }, el = (s) => document.getElementById(p + s), chk = p + '-chk';
    f.montar = () => {
        const lista = el('Lista'); if (!lista || lista.dataset.pronta) return;
        const n = {}; (fonte() || []).forEach((d) => { const c = garCat(d); n[c] = (n[c] || 0) + 1; });
        const cats = Object.keys(n).sort((a, b) => a.localeCompare(b, 'pt-BR'));
        lista.innerHTML = `<label><input type="checkbox" id="${p}Todas" checked> <b>Selecionar todas</b></label><hr>`
            + cats.map((c) => `<label><input type="checkbox" class="${chk}" value="${garEsc(c)}" checked> ${garEsc(c)} <small>(${n[c]})</small></label>`).join('');
        lista.dataset.pronta = '1';
    };
    const ler = () => {
        const caixas = Array.from(document.querySelectorAll(`#${p}Lista .${chk}`)), marc = caixas.filter((c) => c.checked);
        f.cats = marc.length === caixas.length ? null : new Set(marc.map((c) => c.value));
        const todas = el('Todas');
        if (todas) { todas.checked = marc.length === caixas.length; todas.indeterminate = marc.length > 0 && marc.length < caixas.length; }
        const b = el('Btn');
        if (b) { b.textContent = (!f.cats ? 'Todas' : marc.length === 1 ? marc[0].value : `${marc.length} de ${caixas.length}`) + ' ▾'; b.classList.toggle('ativo', !!f.cats); }
        aoMudar();
    };
    document.addEventListener('change', (e) => {
        if (e.target.id === p + 'Todas') { document.querySelectorAll(`#${p}Lista .${chk}`).forEach((c) => { c.checked = e.target.checked; }); ler(); }
        else if (e.target.classList && e.target.classList.contains(chk)) ler();
    });
    document.addEventListener('click', (e) => {
        const dd = el('DD'); if (!dd) return;
        if (e.target.id === p + 'Btn') { const ab = dd.classList.toggle('aberto'); e.target.setAttribute('aria-expanded', ab ? 'true' : 'false'); return; }
        if (!dd.contains(e.target)) { dd.classList.remove('aberto'); el('Btn').setAttribute('aria-expanded', 'false'); }
    });
    document.addEventListener('keydown', (e) => {
        const dd = el('DD');
        if (e.key === 'Escape' && dd && dd.classList.contains('aberto')) { dd.classList.remove('aberto'); el('Btn').focus(); }
    });
    return f;
}
const GAR_CAT_TOP = garFiltroCategoria('garCat', () => GAR.lista, () => garDesenharTop());
function garDesenharTop() {
    const tab = document.getElementById('garTabelaTop'); if (!tab || !GAR.dados) return;
    GAR_CAT_TOP.montar();
    garGrupos = gruposFiltro();
    const { campo, desc } = GAR.ordem;
    tab.tHead.innerHTML = '<tr>' + GAR_COLS_TOP.map(([c, t, tipo]) => `<th class="gar-ord ${tipo === 'n' ? 'num' : ''}" data-ord="${c}" tabindex="0" title="Ordenar">${t}${c === campo ? (desc ? ' ▼' : ' ▲') : ''}</th>`).join('') + '<th></th></tr>';
    const ls = garLinhasTop();
    const naAnalise = new Set(Object.keys(garItens).filter((k) => k.startsWith(GAR.ref + '|')).map((k) => k.slice(GAR.ref.length + 1)));
    const pctCel = (p) => {
        if (p == null) return '<td class="num">–</td>';
        const forte = Math.abs(p) > 0.3, cls = p < 0 ? 'gar-queda' : 'gar-aumento';
        return `<td class="num ${forte ? 'gar-forte ' + cls : ''}">${(p > 0 ? '+' : '') + fmtBR(p * 100, 1)}%</td>`;
    };
    tab.tBodies[0].innerHTML = ls.map((d) => {
        const dc = garVar(d.cons, d.mCons), dv = garVar(d.val, d.mVal);
        const forte = (dc != null && Math.abs(dc) > 0.3) || (dv != null && Math.abs(dv) > 0.3);
        const sit = d.sit ? `<span class="gar-sit ${garEmAnalise(d) ? 'gar-sit-analise' : 'gar-sit-lib'}">${garEsc(garEmAnalise(d) ? 'Em análise' : d.sit)}</span>` : '<span class="gar-sit">sem fatura no mês</span>';
        const lig = String(d.lig);
        return `<tr class="${forte ? 'gar-linha-forte' : ''}"><td class="num">${d.rank}</td><td class="${forte ? 'gar-forte' : ''}">${garEsc(lig)}</td>`
            + `<td class="gar-cli" title="${garEsc(d.nome)}">${garEsc(d.nome)}</td><td>${garEsc(d.cat)}</td><td>${garEsc(d.loc)}</td><td>${garEsc(d.grupo)}</td><td>${garEsc(d.sup)}</td>`
            + `<td class="num">${garN(garValorCol(d, 'eco'))}</td><td class="num">${garN(d.mMed, 1)}</td><td class="num">${garN(d.mCons, 1)}</td><td class="num">${garN(d.cons, 1)}</td>${pctCel(dc)}`
            + `<td class="num">${garR(d.mVal)}</td><td class="num">${garR(d.val)}</td>${pctCel(dv)}<td>${sit}</td>`
            + `<td><button type="button" class="btn-just gar-add" data-lig="${garEsc(lig)}" ${naAnalise.has(lig) ? 'disabled title="Já está na Análise de Garantia"' : 'title="Levar para a Análise de Garantia"'}>${naAnalise.has(lig) ? '✓' : '+ Análise'}</button></td></tr>`;
    }).join('') || `<tr><td colspan="${GAR_COLS_TOP.length + 1}" class="gar-vazio">${GAR.busca.length && !GAR.busca.some((t) => GAR.lista.some((d) => String(d.lig).includes(t)))
        ? 'Matrícula fora do Top ' + GAR.top + ': para analisá-la, use a sub-aba Análise de Garantia.' : 'Nenhuma matrícula com os filtros escolhidos.'}</td></tr>`;
    const emAnalise = GAR.lista.filter((d) => garVisivel(d) && garEmAnalise(d)).length;
    document.getElementById('garTopContagem').textContent = `${ls.length} matrícula(s) na tela · ${emAnalise} em análise`;
    const b = document.getElementById('garSoAnalise');
    b.classList.toggle('ativo', GAR.soAnalise); b.setAttribute('aria-pressed', GAR.soAnalise ? 'true' : 'false');
    b.textContent = GAR.soAnalise ? `Mostrando só em análise (${emAnalise}) — ver todas` : `Somente em análise (${emAnalise})`;
}

// --- Aumentos e quedas: Top 100 pela variação do faturado (água + esgoto) contra o mês anterior ---
// Só matrículas que faturaram nos dois meses (grupo ainda não lido no mês não vira "queda"). O ranking é refeito com os
// filtros (SUP, Grupo, Categoria, Somente em análise); a busca por matrícula só procura dentro do Top 100.
const GAR_VAR = { soAnalise: false, busca: [], base: null };
const GAR_CAT_VAR = garFiltroCategoria('garVcat', () => garVarBase(), () => garDesenharVar());
function garVarBase() {
    if (!GAR.var_base) GAR.var_base = (GAR.dados || []).filter((d) => d.val != null && d.vAnt != null);
    return GAR.var_base;
}
const garDifVal = (d) => d.val - d.vAnt;
function garVarLista(tipo) {
    const s = tipo === 'aumento' ? 1 : -1;
    return garVarBase().filter((d) => garVisivel(d) && (!GAR_VAR.soAnalise || garEmAnalise(d))
            && (!GAR_CAT_VAR.cats || GAR_CAT_VAR.cats.has(garCat(d))) && s * garDifVal(d) > 0)
        .sort((a, b) => s * (garDifVal(b) - garDifVal(a)));
}
// [campo, título, tipo]: clique no título ordena a tabela (as 100 do ranking): número começa do maior, texto de A a Z;
// o terceiro clique volta à ordem do ranking (#). Cada tabela (aumentos / quedas) tem a sua ordem.
const GAR_COLS_VAR = [['rank', '#', 'n'], ['lig', 'Matrícula', 't'], ['nome', 'Cliente', 't'], ['cat', 'Categoria', 't'], ['loc', 'Localidade', 't'],
    ['grupo', 'Grupo', 't'], ['sup', 'SUP', 't'], ['eco', 'Econ.', 'n'], ['cAnt', 'Cons. fat. anterior (m³)', 'n'], ['cons', 'Cons. fat. atual (m³)', 'n'],
    ['dc', 'Δ cons. (m³)', 'n'], ['vAnt', 'Faturado anterior (R$)', 'n'], ['val', 'Faturado atual (R$)', 'n'], ['dv', 'Δ R$', 'n'], ['pv', 'Δ %', 'n'],
    ['sit', 'Situação conta', 't']];
GAR_VAR.ordem = { aumento: { campo: null, desc: false }, queda: { campo: null, desc: false } };
function garVarValor(d, r, c) {
    if (c === 'rank') return r;
    if (c === 'eco') return garValorCol(d, 'eco');
    if (c === 'dc') return d.cons != null && d.cAnt != null ? d.cons - d.cAnt : null;
    if (c === 'dv') return garDifVal(d);
    if (c === 'pv') return d.vAnt ? garDifVal(d) / d.vAnt : null;
    if (c === 'sit') return garEmAnalise(d) ? 'Em análise' : d.sit;
    if (c === 'grupo') return parseInt(normGrupo(d.grupo), 10) || 0;
    return d[c];
}
function garDesenharVar() {
    if (!GAR.dados || !document.getElementById('garTabelaAumento')) return;
    garGrupos = gruposFiltro();
    GAR_CAT_VAR.montar();
    const naAnalise = new Set(Object.keys(garItens).filter((k) => k.startsWith(GAR.ref + '|')).map((k) => k.slice(GAR.ref.length + 1)));
    const busca = GAR_VAR.busca, conta = {};
    ['aumento', 'queda'].forEach((tipo) => {
        const tab = document.getElementById(tipo === 'aumento' ? 'garTabelaAumento' : 'garTabelaQueda');
        const lista = garVarLista(tipo), top = lista.slice(0, 100);
        const vis = top.map((d, i) => [d, i + 1]).filter(([d]) => !busca.length || busca.some((t) => String(d.lig).includes(t)));
        conta[tipo] = [vis.length, lista.length];
        const { campo, desc } = GAR_VAR.ordem[tipo];
        if (campo) {
            const num = GAR_COLS_VAR.find((c) => c[0] === campo)[2] === 'n' || campo === 'grupo';
            vis.sort(([a, ra], [b, rb]) => {
                let x = garVarValor(a, ra, campo), y = garVarValor(b, rb, campo);
                if (num) { x = x == null ? -Infinity : x; y = y == null ? -Infinity : y; return desc ? y - x : x - y; }
                return desc ? String(y || '').localeCompare(String(x || '')) : String(x || '').localeCompare(String(y || ''));
            });
        }
        tab.tHead.innerHTML = '<tr>' + GAR_COLS_VAR.map(([c, t, tipoC]) => `<th class="gar-ord ${tipoC === 'n' ? 'num' : ''}" data-ord-var="${c}" tabindex="0" `
            + `title="Clique para ordenar">${t}${c === campo ? (desc ? ' ▼' : ' ▲') : ''}</th>`).join('') + '<th></th></tr>';
        tab.tBodies[0].innerHTML = vis.map(([d, r]) => {
            const dc = (d.cons != null && d.cAnt != null) ? d.cons - d.cAnt : null, dv = garDifVal(d), pv = d.vAnt ? dv / d.vAnt : null;
            const sit = d.sit ? `<span class="gar-sit ${garEmAnalise(d) ? 'gar-sit-analise' : 'gar-sit-lib'}">${garEsc(garEmAnalise(d) ? 'Em análise' : d.sit)}</span>` : '';
            const lig = String(d.lig), cls = dv < 0 ? 'gar-queda' : 'gar-aumento';
            return `<tr><td class="num">${r}</td><td>${garEsc(lig)}</td><td class="gar-cli" title="${garEsc(d.nome)}">${garEsc(d.nome)}</td><td>${garEsc(d.cat)}</td>`
                + `<td>${garEsc(d.loc)}</td><td>${garEsc(d.grupo)}</td><td>${garEsc(d.sup)}</td><td class="num">${garN(garValorCol(d, 'eco'))}</td>`
                + `<td class="num">${garN(d.cAnt, 1)}</td><td class="num">${garN(d.cons, 1)}</td><td class="num ${dc < 0 ? 'gar-neg' : ''}">${garN(dc, 1)}</td>`
                + `<td class="num">${garR(d.vAnt)}</td><td class="num">${garR(d.val)}</td><td class="num gar-forte ${cls}">${garR(dv)}</td>`
                + `<td class="num ${cls}">${pv == null ? '–' : (pv > 0 ? '+' : '') + fmtBR(pv * 100, 1) + '%'}</td><td>${sit}</td>`
                + `<td><button type="button" class="btn-just gar-add" data-lig="${garEsc(lig)}" ${naAnalise.has(lig) ? 'disabled title="Já está na Análise de Garantia"' : 'title="Levar para a Análise de Garantia"'}>${naAnalise.has(lig) ? '✓' : '+ Análise'}</button></td></tr>`;
        }).join('') || `<tr><td colspan="${GAR_COLS_VAR.length + 1}" class="gar-vazio">${busca.length ? 'Matrícula fora deste Top 100 (com os filtros escolhidos).' : 'Nenhuma matrícula com os filtros escolhidos.'}</td></tr>`;
    });
    const emAnalise = garVarBase().filter((d) => garVisivel(d) && garEmAnalise(d)).length;
    document.getElementById('garVarContagem').textContent = `Aumentos: ${conta.aumento[0]} de ${conta.aumento[1]} · Quedas: ${conta.queda[0]} de ${conta.queda[1]}`;
    const b = document.getElementById('garVarSoAnalise');
    b.classList.toggle('ativo', GAR_VAR.soAnalise); b.setAttribute('aria-pressed', GAR_VAR.soAnalise ? 'true' : 'false');
    b.textContent = GAR_VAR.soAnalise ? `Mostrando só em análise (${emAnalise}) — ver todas` : `Somente em análise (${emAnalise})`;
}
function garBaixarVar(tipo) {
    const lista = garVarLista(tipo), P = tipo === 'aumento' ? 'Aumento' : 'Queda';
    const cols = ['Ranking', 'Matrícula', 'Cliente', 'Categoria', 'Localidade', 'Grupo', 'Rota', 'SUP', 'Econ. residencial', 'Econ. comercial',
        'Econ. industrial', 'Econ. pública', 'Econ. total', 'Tem esgoto', 'Situação conta', 'Situação lançamento',
        'Cons. faturado mês anterior (m³)', 'Cons. faturado atual (m³)', 'Δ consumo (m³)', 'Δ % consumo',
        'Faturado mês anterior (R$)', 'Faturado atual (R$)', `${P} (R$)`, 'Δ % faturado', 'Média faturado meses fechados (R$)', 'Posição no Top 1000'];
    const pct = (a, b) => (b ? Math.round((a - b) / b * 1000) / 10 : null), r2 = (v) => (v == null ? null : Math.round(v * 100) / 100);
    const linhas = lista.map((d, i) => [i + 1, d.lig, d.nome, d.cat, d.loc, d.grupo, d.rota, d.sup, d.res, d.com, d.ind, d.pub, garValorCol(d, 'eco'),
        d.esg ? 'Sim' : 'Não', d.sit || '', d.lanc || '', d.cAnt, d.cons, r2(d.cons != null && d.cAnt != null ? d.cons - d.cAnt : null), pct(d.cons, d.cAnt),
        d.vAnt, d.val, r2(garDifVal(d)), pct(d.val, d.vAnt), d.mVal, d.rank && d.rank <= GAR.top ? d.rank : '']);
    baixarPlanilha(cols, linhas, `Garantia_${P}s_${GAR.ref.replace('/', '-')}${GAR_VAR.soAnalise ? '_em_analise' : ''}${GAR_CAT_VAR.cats ? '_categorias_filtradas' : ''}.csv`);
}
function garVarOrdenar(th) {
    const tipo = th.closest('#garTabelaAumento') ? 'aumento' : 'queda', c = th.dataset.ordVar, o = GAR_VAR.ordem[tipo];
    const texto = GAR_COLS_VAR.find((x) => x[0] === c)[2] === 't' && c !== 'grupo', primeiro = !texto;      // número: maior primeiro
    GAR_VAR.ordem[tipo] = o.campo !== c ? { campo: c, desc: primeiro } : o.desc === primeiro ? { campo: c, desc: !primeiro } : { campo: null, desc: false };
    garDesenharVar();
}
document.addEventListener('keydown', (e) => {
    const th = (e.key === 'Enter' || e.key === ' ') && e.target.closest && e.target.closest('th[data-ord-var]');
    if (th) { e.preventDefault(); garVarOrdenar(th); }
});
document.addEventListener('click', (e) => {
    const th = e.target.closest && e.target.closest('th[data-ord-var]');
    if (th) { garVarOrdenar(th); return; }
    if (e.target.id === 'garVarSoAnalise') { GAR_VAR.soAnalise = !GAR_VAR.soAnalise; garDesenharVar(); return; }
    if (e.target.id === 'garVarLimpar') { const i = document.getElementById('garVarBusca'); i.value = ''; GAR_VAR.busca = []; garDesenharVar(); i.focus(); return; }
    const b = e.target.closest && e.target.closest('[data-var-baixar]');
    if (b) garBaixarVar(b.dataset.varBaixar);
});
document.addEventListener('input', (e) => {
    if (e.target.id !== 'garVarBusca') return;
    GAR_VAR.busca = e.target.value.match(/\d+/g) || [];
    clearTimeout(GAR_VAR.t); GAR_VAR.t = setTimeout(garDesenharVar, 150);
});

// --- Análise de Garantia ---
const garChave = (lig) => `${GAR.ref}|${lig}`;
function garItensDoMes() {
    return Object.entries(garItens).filter(([k]) => k.startsWith(GAR.ref + '|'))
        .map(([k, v]) => ({ lig: k.slice(GAR.ref.length + 1), ...v })).sort((a, b) => (a.ordem || 0) - (b.ordem || 0));
}
function garSalvar() {
    try { localStorage.setItem(GAR_LS, JSON.stringify(garItens)); } catch (e) { /* ignora */ }
    if (typeof syncGarantia !== 'undefined') syncGarantia.agendar();
}
function garAdicionar(ligs) {
    let novos = 0, fora = [];
    const base = Date.now();
    ligs.forEach((lig, i) => {
        lig = String(lig).trim(); if (!lig) return;
        const k = garChave(lig);
        if (garItens[k]) return;
        const d = GAR.porLig.get(lig);
        if (!d) fora.push(lig);
        garItens[k] = { media: null, motivo: '', retorno: '', obs: '', anterior: d && d.val != null ? d.val : null,
                        foto: d && d.val != null ? new Date().toISOString() : null, ordem: base + i };
        novos++;
    });
    if (novos) garSalvar();
    const msg = document.getElementById('garMsg');
    if (msg) msg.textContent = (novos ? `${novos} matrícula(s) adicionada(s).` : 'Nenhuma matrícula nova.')
        + (fora.length ? ` Sem dados no mês atual: ${fora.slice(0, 5).join(', ')}${fora.length > 5 ? '…' : ''}` : '');
    garRedesenhar();
}
function garCalcItem(it) {
    const d = GAR.porLig.get(it.lig);
    const calc = garCalculado(d, it.media);
    const atual = d ? d.val : null;
    const dif = atual != null && it.anterior != null ? atual - it.anterior : null;
    return { d, calc, atual, dif };
}
// colunas da Análise de Garantia (todas ordenáveis pelo cabeçalho): [campo, título, n = número / t = texto, dica]
const GAR_COLS_ANALISE = [
    ['lig', 'Matrícula', 't'], ['nome', 'Cliente', 't'], ['cat', 'Categoria', 't'], ['loc', 'Localidade', 't'],
    ['res', 'Res.', 'n'], ['com', 'Com.', 'n'], ['ind', 'Ind.', 'n'], ['pub', 'Púb.', 'n'], ['tot', 'Total', 'n'],
    ['grupo', 'Grupo', 't'], ['rota', 'Rota', 't'], ['sit', 'Situação conta', 't'],
    ['media', 'Média volume fat. (m³)', 'n', 'Média faturada do sistema (m³) — preenchida manualmente'],
    ['calc', 'Fat. calculado (R$)', 'n', 'Valor da média pela estrutura tarifária'],
    ['anterior', 'Fat. anterior (R$)', 'n', 'Foto do faturado quando a matrícula entrou na análise'],
    ['atual', 'Fat. ajustado (R$)', 'n', 'Faturado atual (muda quando a fatura é liberada)'], ['dif', 'Dif. (R$)', 'n'],
    ['motivo', 'Motivo', 't'], ['retorno', 'Retorno superintendência', 't'],
    ['obs', 'O.S.', 't', 'Abrir O.S.: a matrícula entra no controle de prazo (D+10) do Resumo de Ganhos'],
];
GAR.ordemAnalise = { campo: null, desc: false };              // null = ordem em que as matrículas entraram
function garValorAnalise(it, c) {
    const { d, calc, atual, dif } = garCalcItem(it);
    switch (c) {
        case 'lig': return it.lig;
        case 'tot': return d ? (d.res || 0) + (d.com || 0) + (d.ind || 0) + (d.pub || 0) : null;
        case 'sit': return d ? (garEmAnalise(d) ? 'Em análise' : (d.sit || '')) : '';
        case 'media': return it.media; case 'calc': return calc; case 'anterior': return it.anterior;
        case 'atual': return atual; case 'dif': return dif;
        case 'motivo': return it.motivo === 'QUEDA' ? 'Queda de consumo' : it.motivo === 'AUMENTO' ? 'Aumento de consumo' : '';
        case 'retorno': return it.retorno || '';
        case 'obs': return (it.obs || '') + (it.os_num ? ' ' + it.os_num : '');
        default: return d ? d[c] : null;
    }
}
function garOrdenarAnalise(itens) {
    const { campo, desc } = GAR.ordemAnalise;
    if (!campo) return itens;
    const num = (GAR_COLS_ANALISE.find((c) => c[0] === campo) || [])[2] === 'n';
    const vazio = (v) => v == null || v === '' || (typeof v === 'number' && isNaN(v));
    return itens.slice().sort((a, b) => {
        const x = garValorAnalise(a, campo), y = garValorAnalise(b, campo);
        if (vazio(x) || vazio(y)) return vazio(x) && vazio(y) ? 0 : vazio(x) ? 1 : -1;       // vazios sempre no fim
        const r = num ? x - y : String(x).localeCompare(String(y), 'pt-BR', { numeric: true });
        return desc ? -r : r;
    });
}
document.addEventListener('click', (e) => {
    const th = e.target.closest && e.target.closest('#garTabelaAnalise th[data-ord-an]'); if (!th) return;
    const c = th.dataset.ordAn, o = GAR.ordemAnalise;
    GAR.ordemAnalise = o.campo === c ? (o.desc ? { campo: null, desc: false } : { campo: c, desc: true }) : { campo: c, desc: false };
    garDesenharAnalise();
});
document.addEventListener('keydown', (e) => {
    const th = e.target.closest && e.target.closest('#garTabelaAnalise th[data-ord-an]');
    if (th && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); th.click(); }
});
function garDesenharAnalise() {
    const tab = document.getElementById('garTabelaAnalise'); if (!tab || !GAR.dados) return;
    const { campo, desc } = GAR.ordemAnalise;
    tab.tHead.innerHTML = '<tr>' + GAR_COLS_ANALISE.map(([c, t, tipo, dica]) => `<th class="gar-ord ${tipo === 'n' ? 'num' : ''}" data-ord-an="${c}" tabindex="0" title="${garEsc((dica ? dica + ' — ' : '') + 'clique para ordenar')}">${t}${c === campo ? (desc ? ' ▼' : ' ▲') : ''}</th>`).join('') + '<th></th></tr>';
    let mudouFoto = false;
    const itens = garOrdenarAnalise(garItensDoMes().filter((it) => garVisivel(GAR.porLig.get(it.lig))));
    tab.tBodies[0].innerHTML = itens.map((it) => {
        const { d, calc, atual, dif } = garCalcItem(it);
        if (it.anterior == null && atual != null) { garItens[garChave(it.lig)].anterior = atual; garItens[garChave(it.lig)].foto = new Date().toISOString(); it.anterior = atual; mudouFoto = true; }
        const tot = d ? (d.res || 0) + (d.com || 0) + (d.ind || 0) + (d.pub || 0) : null;
        const sit = !d ? '<span class="gar-sit">não encontrada</span>' : d.sit ? `<span class="gar-sit ${garEmAnalise(d) ? 'gar-sit-analise' : 'gar-sit-lib'}">${garEsc(garEmAnalise(d) ? 'Em análise' : d.sit)}</span>` : '<span class="gar-sit">sem fatura no mês</span>';
        const opt = (v, t) => `<option value="${v}" ${it.motivo === v ? 'selected' : ''}>${t}</option>`;
        const optOS = (v, t) => `<option value="${garEsc(v)}" ${(it.obs || '') === v ? 'selected' : ''}>${garEsc(t)}</option>`;
        const hist = it.historico ? ` <span class="gar-hist" title="Trazida da planilha (análise feita antes do painel): Fat. anterior informado na planilha">Histórico</span>` : '';
        return `<tr data-lig="${garEsc(it.lig)}" ${it.obs_texto ? `title="Observação da planilha: ${garEsc(it.obs_texto)}"` : ''}><td>${garEsc(it.lig)}${hist}</td><td class="gar-cli" title="${garEsc(d && d.nome)}">${garEsc(d && d.nome)}</td>`
            + `<td>${garEsc(d && d.cat)}</td><td>${garEsc(d && d.loc)}</td><td class="num">${garN(d && d.res)}</td><td class="num">${garN(d && d.com)}</td>`
            + `<td class="num">${garN(d && d.ind)}</td><td class="num">${garN(d && d.pub)}</td><td class="num">${garN(tot)}</td><td>${garEsc(d && d.grupo)}</td>`
            + `<td>${garEsc(d && d.rota)}</td><td>${sit}</td>`
            + `<td class="num"><input class="gar-in gar-media" data-campo="media" inputmode="decimal" value="${it.media == null ? '' : fmtBR(it.media, it.media % 1 ? 2 : 0)}"></td>`
            + `<td class="num" data-f="calc">${garR(calc)}</td><td class="num">${garR(it.anterior)}</td><td class="num" data-f="atual">${garR(atual)}</td>`
            + `<td class="num ${dif < 0 ? 'gar-neg' : ''}" data-f="dif">${garR(dif)}</td>`
            + `<td><select class="gar-in" data-campo="motivo">${opt('', '—')}${opt('QUEDA', 'Queda de consumo')}${opt('AUMENTO', 'Aumento de consumo')}</select></td>`
            + `<td><input class="gar-in gar-texto" data-campo="retorno" value="${garEsc(it.retorno)}" placeholder="ex.: FATURAR MÉDIA 311 m³"></td>`
            + `<td><select class="gar-in" data-campo="obs">${optOS('', '—')}${optOS(OS_ABRIR, OS_ABRIR)}${optOS(OS_NAO, OS_NAO)}${it.obs && it.obs !== OS_ABRIR && it.obs !== OS_NAO ? optOS(it.obs, it.obs) : ''}</select>`
            + (it.obs === OS_ABRIR ? `<input class="gar-in gar-os-num" data-campo="os_num" inputmode="numeric" value="${garEsc(it.os_num || '')}" placeholder="Nº da O.S." title="Número da O.S. aberta" aria-label="Número da O.S. da matrícula ${garEsc(it.lig)}">` : '') + '</td>'
            + `<td><button type="button" class="btn-just gar-remover" title="Tirar da análise" aria-label="Tirar a matrícula ${garEsc(it.lig)} da análise">✕</button></td></tr>`;
    }).join('') || '<tr><td colspan="21" class="gar-vazio">Nenhuma matrícula na análise deste mês. Digite ou cole matrículas acima, ou use “+ Análise” no Top 1000.</td></tr>';
    if (mudouFoto) garSalvar();
}
function garLerNumero(t) {
    t = String(t || '').trim().replace(/\s/g, '').replace(/m³|m3|R\$/gi, '');
    if (!t) return null;
    if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.');
    const n = parseFloat(t);
    return isNaN(n) ? null : n;
}
document.addEventListener('input', (e) => {
    const inp = e.target.closest && e.target.closest('#garTabelaAnalise .gar-in'); if (!inp) return;
    const tr = inp.closest('tr'), it = garItens[garChave(tr.dataset.lig)]; if (!it) return;
    const campo = inp.dataset.campo;
    it[campo] = campo === 'media' ? garLerNumero(inp.value) : inp.value;
    if (campo === 'obs') {
        if (inp.value === OS_ABRIR) { if (!it.os_data) it.os_data = garHoje(); delete it.os_status; }
        else { delete it.os_data; delete it.os_status; delete it.os_realizada; delete it.os_num; }
    }
    if (campo === 'os_num') it.os_num = inp.value.trim();
    if (campo === 'media') {
        const c = garCalcItem({ lig: tr.dataset.lig, ...it });
        tr.querySelector('[data-f="calc"]').textContent = garR(c.calc);
    }
    garSalvar(); garDesenharResumo();
    if (campo === 'obs') {                   // mostra/esconde o campo do nº da O.S. na linha
        garDesenharAnalise(); garDesenharOS();
        const n = inp.value === OS_ABRIR && document.querySelector(`#garTabelaAnalise tr[data-lig="${CSS.escape(tr.dataset.lig)}"] .gar-os-num`);
        if (n) n.focus();
    }
    if (campo === 'os_num') garDesenharOS();
});
document.addEventListener('click', (e) => {
    const add = e.target.closest && e.target.closest('.gar-add');
    if (add) { garAdicionar([add.dataset.lig]); return; }
    const rem = e.target.closest && e.target.closest('#garTabelaAnalise .gar-remover');
    if (rem) {
        const lig = rem.closest('tr').dataset.lig;
        if (!confirm(`Tirar a matrícula ${lig} da análise de garantia?`)) return;
        delete garItens[garChave(lig)]; garSalvar(); garRedesenhar(); return;
    }
    const aba = e.target.closest && e.target.closest('[data-gar-aba]');
    if (aba) {
        document.querySelectorAll('[data-gar-aba]').forEach((b) => { const ok = b === aba; b.classList.toggle('ativo', ok); b.setAttribute('aria-pressed', ok ? 'true' : 'false'); });
        document.querySelectorAll('.gar-painel').forEach((p) => { p.hidden = p.dataset.gar !== aba.dataset.garAba; });
        return;
    }
    const ord = e.target.closest && e.target.closest('#garTabelaTop th.gar-ord');
    if (ord) {
        const c = ord.dataset.ord;
        GAR.ordem = { campo: c, desc: GAR.ordem.campo === c ? !GAR.ordem.desc : c !== 'rank' };
        garDesenharTop(); return;
    }
    if (e.target.id === 'garLimparBusca') { const i = document.getElementById('garBuscaLig'); i.value = ''; GAR.busca = []; garDesenharTop(); i.focus(); return; }
    if (e.target.id === 'garSoAnalise') { GAR.soAnalise = !GAR.soAnalise; garDesenharTop(); return; }
    if (e.target.id === 'garAdicionar') {
        const t = document.getElementById('garEntrada');
        if (!(t.value.includes('\t') && garImportarExcel(t.value))) garAdicionar((t.value.match(/\d{4,}/g) || []));
        t.value = ''; return;
    }
    if (e.target.id === 'garBaixarTop') { garBaixarTop(); return; }
    if (e.target.id === 'garEmail') { garExportarEmail(); return; }
});
document.addEventListener('input', (e) => {
    if (e.target.id !== 'garBuscaLig') return;
    GAR.busca = e.target.value.match(/\d+/g) || [];
    clearTimeout(GAR.tBusca); GAR.tBusca = setTimeout(garDesenharTop, 150);
});
document.addEventListener('keydown', (e) => {
    if (e.target.id === 'garEntrada' && e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); document.getElementById('garAdicionar').click(); }
    const ord = e.target.closest && e.target.closest('#garTabelaTop th.gar-ord');
    if (ord && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); ord.click(); }
});
document.addEventListener('paste', (e) => {               // colar várias matrículas direto no campo já adiciona
    if (e.target.id !== 'garEntrada') return;
    const t = (e.clipboardData || window.clipboardData).getData('text');
    if (t.includes('\t') && garImportarExcel(t)) { e.preventDefault(); return; }
    const ligs = t.match(/\d{4,}/g) || [];
    if (ligs.length > 1) { e.preventDefault(); garAdicionar(ligs); }
});
// --- Importar do Excel o que já foi analisado antes do painel ---
// Cola as linhas da planilha de garantia (com o cabeçalho): Nº da Ligação, Média Volume Fat., Fat. Anterior, Motivo,
// Retorno Superintendência e a observação de O.S. (coluna sem título depois do Retorno, ou "O.S."/"Observação").
// O Fat. anterior vem da planilha (a foto de antes do ajuste); o Fat. ajustado continua sendo o valor de hoje na base.
function garLerTSV(texto) {
    const linhas = []; let lin = [], cel = '', aspas = false;
    texto = texto.replace(/\r\n?/g, '\n');
    for (let i = 0; i < texto.length; i++) {
        const c = texto[i];
        if (aspas) {
            if (c === '"' && texto[i + 1] === '"') { cel += '"'; i++; }
            else if (c === '"') aspas = false;
            else cel += c;
        } else if (c === '"' && cel === '') aspas = true;
        else if (c === '\t') { lin.push(cel); cel = ''; }
        else if (c === '\n') { lin.push(cel); linhas.push(lin); lin = []; cel = ''; }
        else cel += c;
    }
    if (cel !== '' || lin.length) { lin.push(cel); linhas.push(lin); }
    return linhas;
}
function garImportarExcel(texto) {
    const tab = garLerTSV(texto);
    const norm = (v) => String(v || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().replace(/[^A-Z0-9]/g, '');
    const iCab = tab.findIndex((l) => l.some((c) => norm(c).includes('LIGACAO')) && l.some((c) => norm(c).includes('ANTERIOR')));
    if (iCab < 0) return false;
    const cab = tab[iCab].map(norm), col = (f) => cab.findIndex(f);
    const cLig = col((c) => c.includes('LIGACAO')), cMed = col((c) => c.includes('MEDIA')), cAnt = col((c) => c.includes('ANTERIOR'));
    const cNum = col((c) => /^(NUMERO|N|NO)(DA)?OS$|^OSN(UMERO)?$/.test(c));
    const cMot = col((c) => c.includes('MOTIVO')), cRet = col((c) => c.includes('RETORNO')), cData = col((c) => c.startsWith('DATA'));
    const cOS = cab.map((c, i) => i).filter((i) => ['OS', 'OBS'].includes(cab[i]) || cab[i].startsWith('OBSERVAC') || (cRet >= 0 && i > cRet && !cab[i]));
    const dataISO = (v) => { const m = String(v || '').match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/); if (!m) return null;
        const a = m[3].length === 2 ? '20' + m[3] : m[3]; return `${a}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`; };
    const vistos = new Set(), regs = [];
    tab.slice(iCab + 1).forEach((l) => {
        const lig = (String(l[cLig] || '').match(/\d{4,}/) || [])[0];
        if (!lig || vistos.has(lig)) return;
        vistos.add(lig);
        const mot = norm(l[cMot]), osTxt = cOS.map((i) => String(l[i] || '').trim()).filter(Boolean).join(' · ');
        const nOS = norm(osTxt);
        regs.push({ lig, media: cMed >= 0 ? garLerNumero(l[cMed]) : null, anterior: garLerNumero(l[cAnt]),
                    motivo: mot.includes('QUEDA') ? 'QUEDA' : mot.includes('AUMENTO') ? 'AUMENTO' : '',
                    retorno: cRet >= 0 ? String(l[cRet] || '').replace(/\s+/g, ' ').trim() : '',
                    obs: /NAOABRIR/.test(nOS) ? OS_NAO : /ABRIROS/.test(nOS) ? OS_ABRIR : '', obs_texto: osTxt,
                    data: cData >= 0 ? dataISO(l[cData]) : null,
                    os_num: cNum >= 0 ? (String(l[cNum] || '').match(/\d{4,}/) || [])[0]
                        : ((osTxt + ' ' + (l[cRet] || '')).match(/O\.?\s*S\.?\s*(?:N[º°o.]*\s*)?(\d{5,})/i) || [])[1] });
    });
    if (!regs.length) { avisoNuvem('Nenhuma matrícula reconhecida nas linhas coladas.', true); return true; }
    const ja = regs.filter((r) => garItens[garChave(r.lig)]).length;
    if (!confirm(`Importar ${regs.length} matrícula(s) da planilha para a Análise de Garantia de ${GAR.ref}?\n\n`
        + `${regs.length - ja} nova(s)` + (ja ? ` · ${ja} já na análise (recebem o Fat. anterior e os campos preenchidos na planilha)` : '')
        + `\n\nO Fat. anterior vem da planilha; o Fat. ajustado é o valor de hoje na base.`)) return true;
    const base = Date.now(), fora = [];
    regs.forEach((r, i) => {
        const k = garChave(r.lig), it = garItens[k] || (garItens[k] = { media: null, motivo: '', retorno: '', obs: '', anterior: null, foto: null, ordem: base + i });
        if (!GAR.porLig.get(r.lig)) fora.push(r.lig);
        it.historico = true;
        if (r.anterior != null) { it.anterior = r.anterior; it.foto = null; }
        if (r.media != null) it.media = r.media;
        if (r.motivo) it.motivo = r.motivo;
        if (r.retorno) it.retorno = r.retorno;
        if (r.obs_texto) it.obs_texto = r.obs_texto;
        if (r.obs && !it.obs) { it.obs = r.obs; if (r.obs === OS_ABRIR) it.os_data = r.data || it.os_data || garHoje(); }
        if (it.obs === OS_ABRIR && r.os_num && !it.os_num) it.os_num = r.os_num;
    });
    garSalvar(); garRedesenhar();
    const msg = document.getElementById('garMsg');
    if (msg) msg.textContent = `${regs.length} matrícula(s) importada(s) da planilha.` + (fora.length ? ` Sem dados no mês atual: ${fora.slice(0, 5).join(', ')}${fora.length > 5 ? '…' : ''}` : '');
    avisoNuvem(`${regs.length} matrícula(s) da planilha importadas para a Análise de Garantia.`);
    return true;
}
function garBaixarTop() {
    const cols = ['Ranking', 'Matrícula', 'Cliente', 'Categoria', 'Localidade', 'Grupo', 'SUP', 'Economias', 'Média cons. medido (m³)',
        'Média cons. faturado (m³)', 'Cons. faturado atual (m³)', 'Δ% cons.', 'Média faturado (R$)', 'Faturado atual (R$)', 'Δ% R$', 'Situação conta'];
    const pct = (p) => (p == null ? null : Math.round(p * 1000) / 10);
    const linhas = garLinhasTop().map((d) => [d.rank, d.lig, d.nome, d.cat, d.loc, d.grupo, d.sup, garValorCol(d, 'eco'), d.mMed, d.mCons, d.cons,
        pct(garVar(d.cons, d.mCons)), d.mVal, d.val, pct(garVar(d.val, d.mVal)), d.sit || '']);
    baixarPlanilha(cols, linhas, `Garantia_Top${GAR.top}_${GAR.ref.replace('/', '-')}${GAR.soAnalise ? '_em_analise' : ''}${GAR_CAT_TOP.cats ? '_categorias_filtradas' : ''}.csv`);
}
function garExportarEmail() {
    const itens = garItensDoMes().filter((it) => garVisivel(GAR.porLig.get(it.lig)) && (it.motivo || it.retorno));
    if (!itens.length) { avisoNuvem('Nenhuma matrícula com motivo ou retorno preenchido para exportar.', true); return; }
    // layout do e-mail: Grupo · Nº da Ligação · Superintendência · Motivo · Retorno Superintendência (como na planilha)
    const cols = ['Grupo', 'Nº da Ligação', 'Superintendência', 'Motivo', 'Retorno Superintendência'];
    const nomeSup = (s) => String(s || '').toLowerCase().replace(/(^|\s)\S/g, (c) => c.toUpperCase());
    const linhas = itens.map((it) => { const d = GAR.porLig.get(it.lig) || {};
        return [d.grupo || '', it.lig, nomeSup(d.sup), it.motivo === 'QUEDA' ? 'QUEDA DE CONSUMO' : it.motivo === 'AUMENTO' ? 'AUMENTO DE CONSUMO' : '', it.retorno || '']; });
    // formatação pedida: sem linhas de grade, Calibri 14, títulos em negrito com fundo cinza-azulado (Texto 2, mais
    // escuro 25% = #333F4F) e fonte branca; demais linhas fonte preta sem preenchimento. Estilo em cada célula (o Outlook
    // ignora CSS de <th>/<style>), com bgcolor para o Outlook desktop.
    const AZUL = '#333F4F', FONTE = "font-family:Calibri,'Calibri',sans-serif;font-size:14pt;";
    const tit = (conteudo, extra) => `<td bgcolor="${AZUL}" ${extra || ''} style="${FONTE}background:${AZUL};color:#FFFFFF;font-weight:bold;border:none;padding:2px 14px;text-align:center;white-space:nowrap">${conteudo}</td>`;
    const cel = (v) => `<td style="${FONTE}color:#000000;border:none;padding:2px 14px;text-align:center;white-space:nowrap">${garEsc(v)}</td>`;
    const html = `<table border="0" cellspacing="0" cellpadding="0" style="border-collapse:collapse;border:none;${FONTE}">`
        + '<tr>' + cols.map((c) => tit(garEsc(c))).join('') + '</tr>'
        + linhas.map((l) => '<tr>' + l.map(cel).join('') + '</tr>').join('') + '</table>';
    const texto = cols.join('\t') + '\n' + linhas.map((l) => l.map((v) => (v == null ? '' : v)).join('\t')).join('\n');
    const copiar = async () => {
        try {
            await navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([html], { type: 'text/html' }), 'text/plain': new Blob([texto], { type: 'text/plain' }) })]);
            return true;
        } catch (e) {                        // reserva: copia a tabela renderizada (mantém a formatação)
            const div = document.createElement('div'); div.innerHTML = html; div.style.cssText = 'position:fixed;left:-9999px;top:0';
            document.body.appendChild(div);
            const r = document.createRange(); r.selectNodeContents(div); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
            let ok = false; try { ok = document.execCommand('copy'); } catch (e2) { ok = false; }
            s.removeAllRanges(); div.remove(); return ok;
        }
    };
    copiar().then((ok) => avisoNuvem((ok ? `${itens.length} matrícula(s) copiadas com a formatação: cole no e-mail (Ctrl+V). ` : 'Não foi possível copiar. ')
        + 'Também foi baixado um rascunho de e-mail (.eml): abra-o para enviar pelo Outlook.', !ok));
    garBaixarEml(html, `Análise de garantia — ${GAR.ref}`, `Garantia_email_${GAR.ref.replace('/', '-')}.eml`);
}
// rascunho de e-mail (.eml) com a tabela formatada: o Outlook abre como mensagem nova, pronta para enviar
function garBaixarEml(html, assunto, nome) {
    const b64 = (t) => btoa(unescape(encodeURIComponent(t)));
    const corpo = `<html><head><meta charset="utf-8"></head><body style="font-family:Calibri,sans-serif;font-size:14pt">${html}</body></html>`;
    const eml = ['X-Unsent: 1', `Subject: =?UTF-8?B?${b64(assunto)}?=`, 'MIME-Version: 1.0', 'Content-Type: text/html; charset=UTF-8',
        'Content-Transfer-Encoding: base64', '', b64(corpo).replace(/.{76}/g, '$&\r\n')].join('\r\n');
    const url = URL.createObjectURL(new Blob([eml], { type: 'message/rfc822' }));
    const a = document.createElement('a'); a.href = url; a.download = nome; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
}

// --- Controle de O.S. (Abrir O.S. → verificar em D+10 a partir do dia da análise) ---
const OS_ABRIR = 'Abrir O.S.', OS_NAO = 'Não abrir O.S.', OS_PRAZO_DIAS = 10;
const garHoje = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const garDataBR = (iso) => (iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4) : '–');
function garPrazo(iso) { const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() + OS_PRAZO_DIAS); return d; }
// todas as O.S. abertas (de qualquer mês) que ainda não foram marcadas como realizadas
function garOS() {
    const hoje = new Date(garHoje() + 'T12:00:00');
    return Object.entries(garItens).filter(([, v]) => v.obs === OS_ABRIR && v.os_status !== 'Realizada').map(([k, v]) => {
        const i = k.lastIndexOf('|'), ref = k.slice(0, i), lig = k.slice(i + 1);
        const data = v.os_data || (v.foto ? v.foto.slice(0, 10) : garHoje());
        const prazo = garPrazo(data), dias = Math.round((hoje - prazo) / 86400000);
        return { k, ref, lig, v, data, prazo, dias, vencida: dias >= 0, d: GAR.porLig.get(lig) };
    }).filter((o) => garVisivel(o.d)).sort((a, b) => b.dias - a.dias);
}
function garDesenharOS() {
    const el = document.getElementById('garAvisoOS'); if (!el || !GAR.dados) return;
    const os = garOS(), vencidas = os.filter((o) => o.vencida), noPrazo = os.length - vencidas.length;
    const aba = document.querySelector('[data-gar-aba="resumo"]');
    if (aba) aba.innerHTML = 'Resumo de Ganhos' + (vencidas.length ? ` <span class="gar-badge" title="O.S. com prazo de ${OS_PRAZO_DIAS} dias vencido">${vencidas.length}</span>` : '');
    if (!os.length) { el.hidden = true; el.innerHTML = ''; return; }
    el.hidden = false;
    const motivo = (m) => (m === 'QUEDA' ? 'Queda de consumo' : m === 'AUMENTO' ? 'Aumento de consumo' : '–');
    el.innerHTML = `<h2>⚠ O.S. abertas — prazo de ${OS_PRAZO_DIAS} dias</h2>`
        + `<p class="nota-secao">${vencidas.length ? `<b>${vencidas.length}</b> matrícula(s) com O.S. aberta há ${OS_PRAZO_DIAS} dias ou mais: verifique se foram realizadas ou estão em atraso.` : 'Nenhuma O.S. com prazo vencido.'}`
        + (noPrazo ? ` ${noPrazo} ainda dentro do prazo.` : '') + ' Depois de conferir, marque como realizada.</p>'
        + (vencidas.length ? '<div class="tabela-wrap"><table class="tabela-garantia"><thead><tr><th>Matrícula</th><th>Cliente</th><th>Grupo</th><th>SUP</th><th>Motivo</th>'
            + '<th>Retorno superintendência</th><th>Nº O.S.</th><th>Análise</th><th>Prazo (D+' + OS_PRAZO_DIAS + ')</th><th class="num">Dias após o prazo</th><th></th></tr></thead><tbody>'
            + vencidas.map((o) => `<tr><td><b>${garEsc(o.lig)}</b></td><td class="gar-cli" title="${garEsc(o.d && o.d.nome)}">${garEsc(o.d && o.d.nome)}</td>`
                + `<td>${garEsc(o.d && o.d.grupo)}</td><td>${garEsc(o.d && o.d.sup)}</td><td>${motivo(o.v.motivo)}</td><td>${garEsc(o.v.retorno)}</td>`
                + `<td>${o.v.os_num ? '<b>' + garEsc(o.v.os_num) + '</b>' : '<span class="gar-sit">não informado</span>'}</td><td>${garDataBR(o.data)}</td><td>${o.prazo.toLocaleDateString('pt-BR')}</td><td class="num gar-neg"><b>${o.dias}</b></td>`
                + `<td><button type="button" class="btn-just gar-os-ok" data-k="${garEsc(o.k)}" title="O.S. conferida e realizada: sai do aviso">✓ Realizada</button></td></tr>`).join('')
            + '</tbody></table></div>' : '');
}
document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('.gar-os-ok'); if (!b) return;
    const it = garItens[b.dataset.k]; if (!it) return;
    it.os_status = 'Realizada'; it.os_realizada = garHoje();
    garSalvar(); garDesenharOS();
});

// --- Resumo de Ganhos ---
function garTotais() {
    const t = { AUMENTO: { n: 0, lib: 0, orig: 0, ajust: 0, gar: 0 }, QUEDA: { n: 0, lib: 0, orig: 0, ajust: 0, gar: 0 } }, porGrupo = {};
    const lib = GAR.soLiberados ? gruposLiberados() : null;
    garItensDoMes().forEach((it) => {
        if (!t[it.motivo]) return;
        const { d, calc, atual } = garCalcItem(it);
        if (!garVisivel(d)) return;
        if (lib && !(d && lib.has(normGrupo(d.grupo)))) return;            // só grupos com situação Liberado
        const x = t[it.motivo], ant = it.anterior || 0, at = atual || 0;
        const ajust = it.motivo === 'AUMENTO' ? (calc || 0) : at;
        const gar = it.motivo === 'AUMENTO' ? (calc == null ? 0 : at - calc) : at - ant;
        x.n++; if (d && !garEmAnalise(d)) x.lib++;
        x.orig += ant; x.ajust += ajust; x.gar += gar;
        const g = (d && d.grupo) || '—', pg = porGrupo[g] = porGrupo[g] || { n: 0, QUEDA: 0, AUMENTO: 0 };
        pg.n++; pg[it.motivo] += gar;
    });
    return { t, porGrupo };
}
function garDesenharResumo() {
    const el = document.getElementById('garResumo'); if (!el || !GAR.dados) return;
    const { t, porGrupo } = garTotais();
    const tot = ['n', 'lib', 'orig', 'ajust', 'gar'].reduce((o, k) => (o[k] = t.AUMENTO[k] + t.QUEDA[k], o), {});
    const lin = (nome, x, cls) => `<tr class="${cls || ''}"><td>${nome}</td><td class="num">${x.n}</td><td class="num">${x.lib}</td><td class="num">${garR(x.orig)}</td>`
        + `<td class="num">${garR(x.ajust)}</td><td class="num ${x.gar < 0 ? 'gar-neg' : 'gar-ganho'}"><b>${garR(x.gar)}</b></td></tr>`;
    const grupos = Object.keys(porGrupo).sort((a, b) => (parseInt(a, 10) || 0) - (parseInt(b, 10) || 0));
    const b = document.getElementById('garSoLiberados');
    if (b) {
        const ng = GAR.soLiberados ? gruposLiberados().size : 0;
        b.classList.toggle('ativo', !!GAR.soLiberados); b.setAttribute('aria-pressed', GAR.soLiberados ? 'true' : 'false');
        b.textContent = GAR.soLiberados ? `Só grupos liberados (${ng}) — ver todos` : 'Somente grupos liberados';
    }
    el.innerHTML = '<div class="gar-kpis">'
        + `<div class="gar-kpi"><span>Garantia total${GAR.soLiberados ? ' — grupos liberados' : ''}</span><b>${garR(tot.gar)}</b><small>${tot.n} matrícula(s) · ${tot.lib} liberada(s)</small></div>`
        + `<div class="gar-kpi"><span>Queda de consumo</span><b>${garR(t.QUEDA.gar)}</b><small>${t.QUEDA.n} matrícula(s)</small></div>`
        + `<div class="gar-kpi"><span>Aumento de consumo</span><b>${garR(t.AUMENTO.gar)}</b><small>${t.AUMENTO.n} matrícula(s)</small></div>` + '</div>'
        + '<div class="tabela-wrap"><table class="tabela-garantia gar-resumo"><thead><tr><th>Resumo</th><th class="num">Ligações</th><th class="num">Liberadas</th>'
        + '<th class="num">Valor original</th><th class="num">Valor ajustado / média</th><th class="num">Garantia</th></tr></thead><tbody>'
        + lin('Aumento de consumo', t.AUMENTO) + lin('Queda de consumo', t.QUEDA) + lin('<b>Total</b>', tot, 'linha-media') + '</tbody></table></div>'
        + (grupos.length ? '<h3 class="gar-h3">Por grupo</h3><div class="tabela-wrap"><table class="tabela-garantia gar-resumo"><thead><tr><th>Grupo</th><th class="num">Ligações</th>'
            + '<th class="num">Garantia queda</th><th class="num">Garantia aumento</th><th class="num">Total</th></tr></thead><tbody>'
            + grupos.map((g) => { const p = porGrupo[g]; return `<tr><td>${garEsc(g)}</td><td class="num">${p.n}</td><td class="num">${garR(p.QUEDA)}</td><td class="num">${garR(p.AUMENTO)}</td><td class="num"><b>${garR(p.QUEDA + p.AUMENTO)}</b></td></tr>`; }).join('')
            + '</tbody></table></div>' : '<p class="nota-secao">Nenhuma matrícula com motivo preenchido na Análise de Garantia.</p>');
}
function garRedesenhar() {
    if (!GAR.dados) return;
    garGrupos = gruposFiltro();
    garDesenharTop(); garDesenharVar(); garDesenharAnalise(); garDesenharResumo(); garDesenharOS();
}
var syncGarantia = criaSync('garantia', 'Análise de garantia', () => garItens,
    (m) => { garItens = m; try { localStorage.setItem(GAR_LS, JSON.stringify(garItens)); } catch (e) {} },
    () => garRedesenhar(),
    () => !!(document.activeElement && document.activeElement.closest && document.activeElement.closest('#garTabelaAnalise')));
garCarregar().then(() => { garRedesenhar(); syncGarantia.puxar(); }).catch((e) => console.warn('Garantia: dados não carregaram', e));

// ===== Aba Plano de ação: tabela colada da planilha =====
// Cada referência (mês) tem um plano { colunas, linhas, atualizado } na seção "plano" do ajustes_relatorio.json — o
// mesmo para todos e incluído no PDF executivo. Sem plano no mês, aparece o último colado (com aviso).
const PLANO_LS = 'faturamento_plano';
let planoMapa = {};
try { planoMapa = JSON.parse(localStorage.getItem(PLANO_LS) || '{}') || {}; } catch (e) { /* sem armazenamento */ }
const planoNorm = (v) => String(v || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().trim();
const planoRefChave = (r) => { const m = /^(\d{2})\/(\d{4})$/.exec(r || ''); return m ? m[2] + m[1] : String(r || ''); };
function planoInfo() {
    const el = document.getElementById('planoEntrada');
    return el ? { ref: el.dataset.ref, mes: el.dataset.mes } : null;
}
function planoAtual() {                          // [ref, plano] do mês; sem plano no mês, o último colado antes dele
    const inf = planoInfo(); if (!inf) return [null, null];
    if (planoMapa[inf.ref] && planoMapa[inf.ref].linhas && planoMapa[inf.ref].linhas.length) return [inf.ref, planoMapa[inf.ref]];
    const antes = Object.keys(planoMapa).filter((r) => planoMapa[r] && (planoMapa[r].linhas || []).length && planoRefChave(r) < planoRefChave(inf.ref))
        .sort((a, b) => (planoRefChave(a) < planoRefChave(b) ? 1 : -1));
    return antes.length ? [antes[0], planoMapa[antes[0]]] : [null, null];
}
function planoSalvar() {
    try { localStorage.setItem(PLANO_LS, JSON.stringify(planoMapa)); } catch (e) { /* ignora */ }
    if (typeof syncPlano !== 'undefined') syncPlano.agendar();
}
function planoDataDe(t) {                        // "dd/mm/aaaa" (ou dd/mm/aa) → Date
    const m = /(\d{1,2})\/(\d{1,2})\/(\d{2,4})/.exec(String(t || '')); if (!m) return null;
    const d = new Date(+(m[3].length === 2 ? '20' + m[3] : m[3]), +m[2] - 1, +m[1]); return isNaN(d) ? null : d;
}
function planoClasseStatus(v) {
    const n = planoNorm(v);
    if (!n) return '';
    if (/CONCLU|FINALIZ|REALIZAD|ENTREGUE|^OK$/.test(n)) return 'pl-ok';
    if (/ATRAS|VENCID|CRITIC/.test(n)) return 'pl-atraso';
    if (/ANDAMENTO|EXECU|INICIAD/.test(n) && !/NAO INICIAD/.test(n)) return 'pl-andamento';
    if (/PENDENTE|NAO INICIAD|A FAZER|AGUARD|PLANEJ/.test(n)) return 'pl-pendente';
    if (/CANCEL|SUSPEN/.test(n)) return 'pl-cancel';
    return 'pl-outro';
}
function planoDesenhar() {
    const tab = document.getElementById('planoTabela'); if (!tab) return;
    const card = document.getElementById('plano-card'), info = document.getElementById('planoInfo'), inf = planoInfo();
    const [ref, plano] = planoAtual();
    if (!plano) {
        card.classList.remove('tem-dados');
        tab.tHead.innerHTML = ''; tab.tBodies[0].innerHTML = '<tr><td class="gar-vazio">Nenhum plano de ação colado ainda. Copie as linhas da planilha (com o cabeçalho) e cole no campo acima.</td></tr>';
        info.textContent = ''; return;
    }
    const cols = plano.colunas, cab = cols.map(planoNorm);
    const iStatus = cab.findIndex((c) => /^STATUS|SITUACAO|ANDAMENTO/.test(c));
    const iPrazo = cab.findIndex((c) => /PRAZO|DATA LIMITE|DATA FIM|TERMINO|CONCLUSAO PREVISTA/.test(c));
    const iSup = cab.findIndex((c) => /^SUP\b|SUPERINTEND/.test(c)), iGrupo = cab.findIndex((c) => /^GRUPO/.test(c));
    const grupos = typeof gruposFiltro === 'function' ? gruposFiltro() : null;
    const hoje = new Date(); hoje.setHours(0, 0, 0, 0);
    const linhas = plano.linhas.filter((l) => {
        if (iSup >= 0 && ESTADO.sup !== 'TODAS' && l[iSup] && !planoNorm(l[iSup]).includes(planoNorm(ESTADO.sup))
            && !planoNorm(ESTADO.sup).includes(planoNorm(l[iSup]))) return false;
        if (iGrupo >= 0 && grupos && l[iGrupo]) {
            const gs = String(l[iGrupo]).split(/[^0-9.]+/).filter((t) => /\d/.test(t)).map(normGrupo);   // "Todos"/"Geral" = sempre aparece
            if (gs.length && !gs.some((g) => grupos.has(g))) return false;
        }
        return true;
    });
    tab.tHead.innerHTML = '<tr>' + cols.map((c) => `<th>${garEsc(c)}</th>`).join('') + '</tr>';
    tab.tBodies[0].innerHTML = linhas.map((l) => {
        const st = iStatus >= 0 ? planoClasseStatus(l[iStatus]) : '';
        const prazo = iPrazo >= 0 ? planoDataDe(l[iPrazo]) : null, vencido = prazo && prazo < hoje && st !== 'pl-ok' && st !== 'pl-cancel';
        return '<tr>' + cols.map((c, i) => {
            const v = l[i] == null ? '' : String(l[i]);
            if (i === iStatus && v) return `<td><span class="pl-status ${st}">${garEsc(v)}</span></td>`;
            if (i === iPrazo && vencido) return `<td class="pl-vencido" title="Prazo vencido">${garEsc(v)}</td>`;
            return `<td>${garEsc(v).replace(/\n/g, '<br>')}</td>`;
        }).join('') + '</tr>';
    }).join('') || `<tr><td colspan="${cols.length}" class="gar-vazio">Nenhuma ação para os filtros escolhidos.</td></tr>`;
    const quando = plano.atualizado ? new Date(plano.atualizado).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '';
    const outro = ref !== inf.ref;
    const resumo = iStatus >= 0 ? (() => {
        const c = {}; linhas.forEach((l) => { const k = planoClasseStatus(l[iStatus]); if (k) c[k] = (c[k] || 0) + 1; });
        const nomes = { 'pl-ok': 'concluídas', 'pl-andamento': 'em andamento', 'pl-pendente': 'pendentes', 'pl-atraso': 'atrasadas', 'pl-cancel': 'canceladas', 'pl-outro': 'outras' };
        return Object.keys(nomes).filter((k) => c[k]).map((k) => `${c[k]} ${nomes[k]}`).join(' · ');
    })() : '';
    const vencidas = iPrazo >= 0 ? linhas.filter((l) => { const d = planoDataDe(l[iPrazo]), st = iStatus >= 0 ? planoClasseStatus(l[iStatus]) : '';
        return d && d < hoje && st !== 'pl-ok' && st !== 'pl-cancel'; }).length : 0;
    info.innerHTML = `${linhas.length} ação(ões)` + (resumo ? ` · ${resumo}` : '') + (vencidas ? ` · <b class="pl-vencido-txt">${vencidas} com prazo vencido</b>` : '')
        + (quando ? ` · colado em ${quando}` : '') + (outro ? ` · <b>plano de ${garEsc(ref)}</b> (o mês atual ainda não tem plano colado)` : '');
    card.classList.toggle('tem-dados', linhas.length > 0);
}
function planoImportar(texto) {
    const tab = garLerTSV(texto).map((l) => l.map((c) => String(c == null ? '' : c).trim()));
    const linhas = tab.filter((l) => l.some((c) => c !== ''));
    if (linhas.length < 2) { avisoNuvem('Cole as linhas da planilha com o cabeçalho (pelo menos o cabeçalho e uma linha).', true); return; }
    let cab = linhas[0];
    const usadas = cab.map((c, i) => c !== '' || linhas.slice(1).some((l) => (l[i] || '') !== ''));   // tira colunas vazias
    const pega = (l) => cab.map((_, i) => l[i] || '').filter((_, i) => usadas[i]);
    const colunas = pega(cab).map((c, i) => c || `Coluna ${i + 1}`), corpo = linhas.slice(1).map(pega);
    const inf = planoInfo();
    const ja = planoMapa[inf.ref] && (planoMapa[inf.ref].linhas || []).length;
    if (!confirm(`${ja ? 'Substituir' : 'Salvar'} o plano de ação de ${inf.mes} por ${corpo.length} linha(s) e ${colunas.length} coluna(s)?\n\nColunas: ${colunas.join(' · ')}`)) return;
    planoMapa[inf.ref] = { colunas, linhas: corpo, atualizado: new Date().toISOString() };
    planoSalvar(); planoDesenhar();
    const msg = document.getElementById('planoMsg'); if (msg) msg.textContent = `${corpo.length} linha(s) coladas.`;
}
document.addEventListener('paste', (e) => {
    if (e.target.id !== 'planoColar') return;
    e.preventDefault();
    planoImportar((e.clipboardData || window.clipboardData).getData('text'));
    e.target.value = '';
});
document.addEventListener('click', (e) => {
    if (e.target.id === 'planoLimpar') {
        const inf = planoInfo();
        if (!planoMapa[inf.ref]) { avisoNuvem(`O mês ${inf.mes} não tem plano colado.`, true); return; }
        if (!confirm(`Apagar o plano de ação de ${inf.mes}?`)) return;
        delete planoMapa[inf.ref]; planoSalvar(); planoDesenhar(); return;
    }
    if (e.target.id === 'planoBaixar') {
        const [ref, plano] = planoAtual(); if (!plano) return;
        const t = document.getElementById('planoTabela');
        const linhas = Array.from(t.tBodies[0].rows).filter((r) => !r.querySelector('.gar-vazio')).map((r) => Array.from(r.cells).map((c) => c.innerText));
        baixarPlanilha(plano.colunas, linhas, `Plano_de_acao_${String(ref).replace('/', '-')}.csv`);
    }
});
var syncPlano = criaSync('plano', 'Plano de ação', () => planoMapa,
    (m) => { planoMapa = m; try { localStorage.setItem(PLANO_LS, JSON.stringify(planoMapa)); } catch (e) {} },
    () => planoDesenhar(), () => false);
document.addEventListener('DOMContentLoaded', () => { planoDesenhar(); syncPlano.puxar(); });

// ===== Aba Análise: ver as tabelas com todas as economias ou só com as que faturam esgoto =====
// Ativas × cortadas, matriz de migração e acima × abaixo do mínimo vêm nas duas versões (.vista-serv); a escolha é de
// cada pessoa e fica lembrada neste navegador. Os downloads ⬇≡ dessas tabelas seguem a versão escolhida.
let analiseVista = 'todas';
function analiseAplicarVista(v) {
    analiseVista = v === 'esgoto' ? 'esgoto' : 'todas';
    document.querySelectorAll('.vista-serv').forEach((el) => { el.hidden = el.dataset.vista !== analiseVista; });
    document.querySelectorAll('[data-vista-btn]').forEach((b) => { const ok = b.dataset.vistaBtn === analiseVista; b.classList.toggle('ativo', ok); b.setAttribute('aria-pressed', ok ? 'true' : 'false'); });
    try { localStorage.setItem('faturamento_analise_vista', analiseVista); } catch (e) { /* sem armazenamento */ }
}
document.addEventListener('click', (e) => { const b = e.target.closest && e.target.closest('[data-vista-btn]'); if (b) analiseAplicarVista(b.dataset.vistaBtn); });
document.addEventListener('DOMContentLoaded', () => { let v = null; try { v = localStorage.getItem('faturamento_analise_vista'); } catch (e) {} analiseAplicarVista(v); });


// ===== Aba One page: acompanhamento do faturamento numa folha vertical (lê bem no celular; PDF de uma página) =====
// Responde: quanto faturamos, se estamos atingindo o orçamento, o que impactou o resultado e quais ações estão em curso.
// Números: DRE da superintendência (realizado e orçado de cada mês — o primeiro orçado escolhido em Comparar) e Resumo
// (grupos marcados). Faturamento total = direto + indireto; água/esgoto é outra visão do mesmo total (sem dupla contagem).
// Tarifa média = faturamento direto ÷ volume faturado de água; ticket médio = faturamento direto ÷ economias de água
// faturadas (as mesmas definições dos KPIs do Resumo). Tendência e forecast vêm das tabelas de forecast (abas Forecast e
// Indiretas) e são refeitos a cada edição do forecast. A folha não tem nada editável.
const OP_W = 900;                                       // largura da folha no PDF (no celular ela se ajusta à tela)
const OP_RELEVANTE = 0.03;                              // variação a partir da qual o desvio ganha cor
const OP_MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
let opGraficos = [];
const opAtiva = () => { const v = document.getElementById('view-onepage'); return !!v && v.classList.contains('ativo'); };
const opEditor = () => document.getElementById('opEditor');
// "R$ 119.432" · "R$ (3.240)" · "22,64" · "-27,0%" → número (null quando vazio ou "-")
function opNum(t) {
    t = String(t == null ? '' : t).trim();
    if (!t || /^[-–—]$/.test(t)) return null;
    const n = parseFloat(t.replace(/[^\d,]/g, '').replace(',', '.'));
    return isNaN(n) ? null : (/[(\-−]/.test(t) ? -n : n);
}
const opChaveMes = (m) => { const x = /^(\d{2})\/(\d{4})$/.exec(m || ''); return x ? +x[2] * 12 + (+x[1] - 1) : null; };
const opMesDeChave = (k) => String(k % 12 + 1).padStart(2, '0') + '/' + Math.floor(k / 12);
const opMesCurto = (m) => { const k = opChaveMes(m); return k == null ? m : OP_MESES[k % 12] + '/' + String(Math.floor(k / 12)).slice(2); };
function opMoeda(v, dec) {
    if (v == null || isNaN(v)) return '–';
    const a = Math.abs(v), s = v < 0 ? '-' : '';
    if (a >= 1e6) return `${s}R$ ${fmtBR(a / 1e6, dec == null ? 2 : dec)} mi`;
    if (a >= 1e3) return `${s}R$ ${fmtBR(a / 1e3, dec == null ? 1 : dec)} mil`;
    return `${s}R$ ${fmtBR(a, 0)}`;
}
const opPct = (v, sinal) => (v == null || !isFinite(v) ? '–' : (sinal && v > 0 ? '+' : '') + fmtBR(v * 100, 1) + '%');
const opVar = (a, b) => (a == null || b == null || !b ? null : (a - b) / Math.abs(b));
function opSeta(v, rot) {                       // ▲ 3,5% vs Ago/26 — cor só quando o desvio é relevante
    if (v == null || !isFinite(v)) return `<span class="op-var">– ${garEsc(rot)}</span>`;
    const cls = Math.abs(v) < OP_RELEVANTE ? '' : v > 0 ? ' op-pos' : ' op-neg';
    return `<span class="op-var${cls}">${v > 0 ? '▲' : v < 0 ? '▼' : '■'} ${opPct(Math.abs(v))} ${garEsc(rot)}</span>`;
}

// Uma DRE (superintendência + mês) em números: realizado (r) e orçado (o) das linhas usadas no One page
const OP_LINHAS = [['bruto', /^FATURAMENTO BRUTO/], ['diretas', /^DIRETAS TOTAIS/], ['dAgua', /^DIRETAS AGUA/], ['dEsg', /^DIRETAS ESGOTO/],
    ['iEsg', /^FAT\.? DE ESGOTO\s*-\s*INDIRETO/], ['iAgua', /^FAT\.? DE AGUA\s*-\s*INDIRETO/],
    ['eco', /^ECONOMIAS DE AGUA/], ['vol', /^VOLUME DE AGUA\s*-\s*FATURADO/]];
function opRefOrcado() {
    const sel = (ESTADO.ref || '').replace(/^cmp:/, '').split('|').filter(Boolean);
    if (sel.length) return sel[0];
    const th = document.querySelector('#view-dre th[data-tipo="orc"]');
    return th ? th.dataset.src : null;
}
function opDre(sup, mes, ref) {
    const t = document.querySelector(`#view-dre .sup-bloco[data-sup="${sup}"][data-mes="${mes}"] table.tabela-dre`);
    if (!t) return null;
    const d = {};
    t.querySelectorAll('tbody tr').forEach((tr) => {
        const rot = tr.querySelector('td.dre-rotulo'); if (!rot) return;
        const n = planoNorm(rot.textContent).replace(/\s+/g, ' ');
        const l = OP_LINHAS.find(([, re]) => re.test(n)); if (!l || d[l[0]]) return;
        const orc = ref ? tr.querySelector(`td[data-tipo="orc"][data-src="${ref}"]`) : null;
        d[l[0]] = { r: opNum((tr.querySelector('td.col-real') || {}).textContent), o: orc ? opNum(orc.textContent) : null };
    });
    if (!d.bruto) return null;
    const soma = (a, b, k) => (d[a] && d[a][k] != null) || (d[b] && d[b][k] != null) ? ((d[a] || {})[k] || 0) + ((d[b] || {})[k] || 0) : null;
    const div = (a, b) => (a == null || !b ? null : a / b);
    d.ind = { r: soma('iAgua', 'iEsg', 'r'), o: soma('iAgua', 'iEsg', 'o') };
    d.agua = { r: soma('dAgua', 'iAgua', 'r'), o: soma('dAgua', 'iAgua', 'o') };
    d.esg = { r: soma('dEsg', 'iEsg', 'r'), o: soma('dEsg', 'iEsg', 'o') };
    const dir = d.diretas || {}, vol = d.vol || {}, eco = d.eco || {};
    d.tarifa = { r: div(dir.r, vol.r), o: div(dir.o, vol.o) };
    d.ticket = { r: div(dir.r, eco.r), o: div(dir.o, eco.o) };
    return d;
}
// Resumo (grupos marcados, só o mês vigente): somas das linhas visíveis da tabela consolidada por grupo
function opResumo() {
    const linhas = Array.from(document.querySelectorAll('#tabela-dados-resumo tbody tr[data-grupo]')).filter((tr) => tr.style.display !== 'none');
    if (!linhas.length) return null;
    const s = (campo) => linhas.reduce((t, tr) => t + (parseFloat(tr.dataset[campo]) || 0), 0);
    const par = (c) => ({ r: s(c + 'Atual'), a: s(c + 'Anterior') });
    const r = { fat: par('fat'), agua: par('fatagua'), esg: par('fatesgoto'), eco: par('eco'), vol: par('volfat'), acima: par('acima') };
    r.tarifa = { r: r.vol.r ? r.fat.r / r.vol.r : null, a: r.vol.a ? r.fat.a / r.vol.a : null };
    r.ticket = { r: r.eco.r ? r.fat.r / r.eco.r : null, a: r.eco.a ? r.fat.a / r.eco.a : null };
    r.temAcima = linhas.some((tr) => tr.dataset.acimaAtual != null);
    return r;
}
// Faturamento bruto previsto (Realizado + Forecast) do mês vigente, quando o Forecast tem valor
function opProjecao(sup) {
    const tr = document.querySelector(`#view-forecast .prev-bloco[data-sup="${sup}"] tr[data-k="bruto"]`);
    return tr ? opNum((tr.querySelector('.p-fech') || {}).textContent) : null;
}

function opDados() {
    const sup = ESTADO.sup, ed = opEditor();
    const fontes = Array.from(new Set(Array.from(document.querySelectorAll('#view-dre th[data-tipo="orc"]')).map((th) => th.dataset.src)));
    const mes = ESTADO.mes || (ed ? ed.dataset.ref : ''), ref = fontes.find((f) => /SUP/i.test(f)) || opRefOrcado(), k = opChaveMes(mes);
    const meses = Array.from(new Set(Array.from(document.querySelectorAll(`#view-dre .sup-bloco[data-sup="${sup}"]`)).map((b) => b.dataset.mes)))
        .filter((m) => opChaveMes(m) != null && opChaveMes(m) <= k).sort((a, b) => opChaveMes(a) - opChaveMes(b)).slice(-12);
    const serie = meses.map((m) => ({ mes: m, d: opDre(sup, m, ref) })).filter((x) => x.d);
    const atual = opDre(sup, mes, ref), ant = k != null ? opDre(sup, opMesDeChave(k - 1), ref) : null;
    const anoAnt = k != null ? opDre(sup, opMesDeChave(k - 12), ref) : null;
    const vigente = !!ed && mes === ed.dataset.ref;
    return { sup, mes, ref, serie, atual, ant, anoAnt, vigente, resumo: vigente ? opResumo() : null,
             projecao: vigente ? opProjecao(sup) : null, rotAnt: k != null ? opMesCurto(opMesDeChave(k - 1)) : 'mês anterior' };
}

// ---- Destaque: realizado do mês contra o orçado e a tendência de fechamento ----
const opBarra = (rot, dir, frac, cls) => `<div class="op-barra-lin"><span>${rot}</span><span>${dir}</span></div>`
    + `<div class="op-barra${cls ? ' ' + cls : ''}"><i style="width:${Math.max(0, Math.min(1, frac || 0)) * 100}%"></i></div>`;
function opBlocoDestaque(D) {
    const A = D.atual, P = D.ant, ed = opEditor();
    if (!A) return '<p class="op-vazio">Sem DRE para o mês e a superintendência escolhidos.</p>';
    const corte = D.ultimo ? D.ultimo.data : ed ? ed.dataset.corte.slice(0, 5) : '';
    const rot = D.vigente ? `Realizado até ${corte}` + (D.ultimo ? ` · último grupo lido: ${D.ultimo.grupo}` : '') : `Realizado em ${opMesCurto(D.mes)}`;
    const dv = opVar(A.bruto.r, A.bruto.o);
    const cls = dv == null || Math.abs(dv) < OP_RELEVANTE ? '' : dv > 0 ? ' op-pos' : ' op-neg';
    const ant = P ? `${garEsc(opMesCurto(opMesDeChave(opChaveMes(D.mes) - 1)))}: ${opMoeda(P.bruto.r, 2)}`
        + (P.bruto.o ? ` (${opPct(opVar(P.bruto.r, P.bruto.o), true)} vs ${garEsc(D.ref)})` : '') : '';
    let h = `<div class="op-hero"><div class="op-hero-esq"><span class="op-rot">${garEsc(rot)}</span><b class="op-hero-val">${opMoeda(A.bruto.r, 2)}</b></div>`
        + `<div class="op-hero-dir"><b class="op-hero-pct${cls}">${dv == null ? '–' : (dv > 0 ? '▲ ' : dv < 0 ? '▼ ' : '') + opPct(Math.abs(dv))}</b>`
        + `<span>${A.bruto.o != null ? `vs ${garEsc(D.ref)} no mês: ${opMoeda(A.bruto.r - A.bruto.o, 2)} (orçado ${opMoeda(A.bruto.o, 2)})` : 'mês sem orçado'}</span></div></div>`;
    if (A.bruto.o) h += opBarra(`Realizado × orçado do mês (${garEsc(D.ref)})`, `${opMoeda(A.bruto.r, 2)} de ${opMoeda(A.bruto.o, 2)} · ${opPct(A.bruto.r / A.bruto.o)}`, A.bruto.r / A.bruto.o);
    if (D.projecao != null && A.bruto.o) h += opBarra('Tendência de fechamento (realizado + forecast)', `${opMoeda(D.projecao, 2)} de ${opMoeda(A.bruto.o, 2)} · ${opPct(D.projecao / A.bruto.o)}`, D.projecao / A.bruto.o, 'op-barra-clara');
    return { html: h, ant };
}
// Quatro quadros: cada orçado do mês (realizado contra ele) e a tendência de fechamento
function opBlocoCards(D) {
    const A = D.atual; if (!A) return '';
    const base = D.projecao != null ? D.projecao : A.bruto.r;
    const quadros = D.refs.slice(0, 3).map((ref) => {
        const d = ref === D.ref ? A : opDre(D.sup, D.mes, ref), o = d && d.bruto.o;
        return `<div class="op-card"><span class="op-rot">${garEsc(ref)} — ${garEsc(opMesCurto(D.mes))}</span><b>${opMoeda(o, 2)}</b>`
            + (o ? opSeta(opVar(A.bruto.r, o), 'realizado vs orçado') : '<span class="op-var">sem orçado</span>') + '</div>';
    });
    if (D.projecao != null) quadros.push(`<div class="op-card op-card-tend"><span class="op-rot">Tendência — ${garEsc(opMesCurto(D.mes))}</span><b>${opMoeda(D.projecao, 2)}</b>`
        + (A.bruto.o ? opSeta(opVar(D.projecao, A.bruto.o), 'vs ' + D.ref) : '') + '</div>');
    else if (D.ant) quadros.push(`<div class="op-card op-card-tend"><span class="op-rot">Mês anterior — ${garEsc(D.rotAnt)}</span><b>${opMoeda(D.ant.bruto.r, 2)}</b>`
        + opSeta(opVar(A.bruto.r, D.ant.bruto.r), 'realizado vs ' + D.rotAnt) + '</div>');
    void base;
    return `<div class="op-cards">${quadros.join('')}</div>`;
}

// ---- Faturamento aberto: números da aba Forecast (mês vigente), já com as edições do forecast ----
// {chave: {r: realizado, o: orçado (D.ref), f: forecast, t: realizado + forecast}}. O forecast é um só (editar na aba
// Forecast ou na Indiretas muda os dois); mês fechado ou sem a aba Forecast: tabela da aba Indiretas, sem forecast.
function opLinhasPrev(D) {
    const fc = D.vigente ? document.querySelector(`#view-forecast .prev-bloco[data-sup="${D.sup}"] table.tabela-previsao`) : null;
    const t = fc || document.querySelector(`#view-indiretas .sup-bloco[data-sup="${D.sup}"][data-mes="${D.mes}"] table.tabela-previsao`);
    const comFc = D.vigente && !!t;
    const L = {};
    if (t) t.querySelectorAll('tbody tr[data-k]').forEach((tr) => {
        const k = tr.dataset.k; if (L[k] || /^ev_/.test(k)) return;
        const txt = (sel) => (tr.querySelector(sel) || {}).textContent;
        const orc = tr.querySelector(`td[data-tipo="orc"][data-src="${D.ref}"]`);
        L[k] = { r: opNum(txt('.p-real')), o: orc ? opNum(orc.textContent) : null, f: comFc ? opNum(txt('.p-prev')) : null,
                 t: comFc ? opNum(txt('.p-fech')) : null };
    });
    if (fc || (!L.tot && (L.iA || L.iE))) {             // aba Forecast: total indiretas = água + esgoto indireto dela
        const s = (c) => [L.iA, L.iE].some((x) => x && x[c] != null) ? [L.iA, L.iE].reduce((t, x) => t + ((x && x[c]) || 0), 0) : null;
        L.tot = { r: s('r'), o: s('o'), f: s('f'), t: s('t') };
    }
    return L;
}
const OP_ABERTO_FAT = [['dA', 'Diretas água'], ['dE', 'Diretas esgoto'], ['tot', 'Indiretas (água + esgoto)']];
const OP_ABERTO_IND = [['ri_CORTE', 'Cortes / recorte'], ['ri_RELIGAÇÃO', 'Religações'], ['ri_LNA', 'Ligações de água'],
    ['ri_SANÇÃO', 'Fiscalização'], ['ri_OUTROS', 'Outros (água)'], ['iA', 'Indiretas água', 'op-sub'], ['iE', 'Esgoto indireto (LNE)', 'op-sub']];
// tabela: realizado, forecast, tendência (realizado + forecast) e orçado; no celular ficam realizado, tendência e o desvio
function opTabAberta(D, L, linhas, total, rotTotal) {
    const comFc = D.vigente && Object.values(L).some((x) => x.t != null);
    const v = (x) => opMoeda(x, 2);
    const cols = (x) => {
        const base = comFc && x.t != null ? x.t : x.r;
        return `<td class="num op-forte">${v(x.r)}</td>`
            + (comFc ? `<td class="num op-col-val op-apagado">${v(x.f)}</td><td class="num">${v(x.t)}</td>` : '')
            + `<td class="num op-col-val op-apagado">${x.o != null ? v(x.o) : '–'}</td><td class="num">${x.o ? opSeta(opVar(base, x.o), '') : '–'}</td>`;
    };
    const corpo = linhas.filter(([k]) => L[k]).map(([k, rot, cls]) => `<tr${cls ? ` class="${cls}"` : ''}><td>${garEsc(rot)}</td>${cols(L[k])}</tr>`).join('');
    if (!corpo) return '<p class="op-vazio">Sem dados para o mês e a superintendência escolhidos.</p>';
    return `<table class="op-tab op-tab-aberta"><thead><tr><th></th><th class="num">Realizado</th>`
        + (comFc ? '<th class="num op-col-val">Forecast</th><th class="num">Tendência</th>' : '')
        + `<th class="num op-col-val">${garEsc('Orçado ' + (D.ref || ''))}</th><th class="num">${comFc ? 'Tendência' : 'Realizado'} × orçado</th></tr></thead>`
        + `<tbody>${corpo}</tbody>` + (total && L[total] ? `<tfoot><tr class="op-tot"><td>${garEsc(rotTotal)}</td>${cols(L[total])}</tr></tfoot>` : '') + '</table>';
}
// Mês fechado ou sem a tabela de forecast: as linhas da composição saem da DRE do mês
function opAbertoFat(D, L) {
    if (L.dA && L.dE && L.bruto) return L;
    const A = D.atual; if (!A) return L;
    const x = (o) => ({ r: o ? o.r : null, o: o ? o.o : null, f: null, t: null });
    return Object.assign({ dA: x(A.dAgua), dE: x(A.dEsg), bruto: x(A.bruto) }, L, L.tot ? {} : { tot: x(A.ind) });
}

// ---- Acompanhamento por semana: grupos lidos em cada semana do mês, contra o orçado SUP e o mês anterior ----
// Semana = semana do calendário (segunda a domingo) da primeira data de leitura do grupo no cronograma do mês vigente.
let opSemanasAbertas = null;                    // semanas abertas na tela (null = abre só a última com grupos)
function opGrupos(D) {
    const blocos = Array.from(document.querySelectorAll('#view-tabelas .orc-ciclo-bloco'));
    const bloco = blocos.find((b) => b.dataset.orcCiclo === D.ref) || blocos.find((b) => /SUP/i.test(b.dataset.orcCiclo)) || null;
    const mapa = new Map();
    const pega = (g) => { const k = normGrupo(g); if (!mapa.has(k)) mapa.set(k, { grupo: g, r: 0, a: 0, o: null, sit: '' }); return mapa.get(k); };
    ['tabela-agua', 'tabela-esgoto'].map((id) => document.getElementById(id)).filter(Boolean).forEach((t) => t.querySelectorAll('tbody tr[data-grupo]').forEach((tr) => {
        if (tr.style.display === 'none' || !tr.dataset.grupo) return;
        const g = pega(tr.dataset.grupo);
        // grupo ainda não lido (linha-pendente): o mês anterior aparece na tabela das Diretas, mas aqui segue sem valores
        if (!tr.classList.contains('linha-pendente')) { g.r += parseFloat(tr.dataset.fatAtual) || 0; g.a += parseFloat(tr.dataset.fatAnterior) || 0; }
        const s = tr.querySelector('.sit-grupo'); if (s && !g.sit) g.sit = s.textContent.trim();
    }));
    if (bloco) bloco.querySelectorAll('table.tabela-comparativo tbody tr[data-grupo]').forEach((tr) => {
        const g = mapa.get(normGrupo(tr.dataset.grupo)); if (!g) return;      // só os grupos marcados
        g.o = (g.o || 0) + (parseFloat(tr.dataset.fatAnterior) || 0);
    });
    let datas = {}; try { datas = JSON.parse((document.getElementById('opDatasLeitura') || {}).textContent || '{}') || {}; } catch (e) { datas = {}; }
    const semanaDe = (iso) => {                 // {n, ini, fim} da semana (segunda a domingo) dentro do mês
        const d = new Date(iso + 'T12:00:00'), p = new Date(d.getFullYear(), d.getMonth(), 1, 12);
        const desl = (p.getDay() + 6) % 7;      // dias do dia 1 até a segunda anterior
        const n = Math.floor((d.getDate() + desl - 1) / 7) + 1;
        const ult = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
        const ini = Math.max(1, (n - 1) * 7 - desl + 1), fim = Math.min(ult, n * 7 - desl);
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        return { n, rot: `${String(ini).padStart(2, '0')} a ${String(fim).padStart(2, '0')}/${mm}` };
    };
    const semanas = new Map();
    Array.from(mapa.values()).forEach((g) => {
        const iso = datas[normGrupo(g.grupo)];
        const s = iso ? semanaDe(iso) : { n: 99, rot: 'sem data no cronograma' };
        g.iso = iso || ''; g.data = iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) : '';
        if (!semanas.has(s.n)) semanas.set(s.n, { n: s.n, rot: s.rot, grupos: [] });
        semanas.get(s.n).grupos.push(g);
    });
    const lista = Array.from(semanas.values()).sort((a, b) => a.n - b.n);
    lista.forEach((s) => {
        s.grupos.sort((x, y) => (x.data || '99').localeCompare(y.data || '99') || x.grupo.localeCompare(y.grupo, 'pt-BR', { numeric: true }));
        s.r = s.grupos.reduce((t, g) => t + g.r, 0); s.a = s.grupos.reduce((t, g) => t + g.a, 0);
        s.o = s.grupos.some((g) => g.o != null) ? s.grupos.reduce((t, g) => t + (g.o || 0), 0) : null;
    });
    return { fonte: bloco ? bloco.dataset.orcCiclo : '', semanas: lista, grupos: lista.flatMap((s) => s.grupos) };
}
function opBlocoGrupos(D, G) {
    if (!G.grupos.length) return '<p class="op-vazio">Nenhum grupo marcado.</p>';
    if (opSemanasAbertas === null) { const ult = G.semanas.filter((s) => s.n !== 99).pop(); opSemanasAbertas = new Set(ult ? [ult.n] : []); }
    const v = (x) => opMoeda(x, 2);
    const cols = (o) => `<td class="num op-forte">${v(o.r)}</td>`
        + `<td class="num op-col-val op-apagado">${o.o != null ? v(o.o) : '–'}</td><td class="num">${o.o != null ? opSeta(opVar(o.r, o.o), '') : '–'}</td>`
        + `<td class="num op-col-val op-apagado">${v(o.a)}</td><td class="num">${opSeta(opVar(o.r, o.a), '')}</td>`;
    const corpo = G.semanas.map((s) => {
        const aberta = opSemanasAbertas.has(s.n);
        const nome = s.n === 99 ? 'Sem semana' : `Semana ${s.n}`;
        return `<tr class="op-sem${aberta ? ' op-aberta' : ''}" data-semana="${s.n}" title="Clique para ${aberta ? 'fechar' : 'abrir'} os grupos desta semana">`
            + `<td><span class="op-seta-sem">${aberta ? '▾' : '▸'}</span> ${nome} <small>${garEsc(s.rot)} · ${s.grupos.length} grupo(s)</small></td>${cols(s)}</tr>`
            + (aberta ? s.grupos.map((g) => `<tr class="op-grp"><td>Grupo ${garEsc(g.grupo)} <small>${g.data ? 'leitura ' + garEsc(g.data) : ''}${g.sit ? ' · ' + garEsc(g.sit) : ''}</small></td>${cols(g)}</tr>`).join('') : '');
    }).join('');
    const tot = { r: G.grupos.reduce((t, g) => t + g.r, 0), a: G.grupos.reduce((t, g) => t + g.a, 0),
                  o: G.grupos.some((g) => g.o != null) ? G.grupos.reduce((t, g) => t + (g.o || 0), 0) : null };
    return `<table class="op-tab op-tab-grupos"><thead><tr><th>Semana / grupo</th><th class="num">Realizado</th>`
        + `<th class="num op-col-val">${garEsc(G.fonte ? 'Orçado ' + G.fonte : 'Orçado')}</th><th class="num">Δ orçado</th>`
        + `<th class="num op-col-val">${garEsc(D.rotAnt)}</th><th class="num">Δ ${garEsc(D.rotAnt)}</th></tr></thead>`
        + `<tbody>${corpo}</tbody><tfoot><tr class="op-tot"><td>Total (diretas)</td>${cols(tot)}</tr></tfoot></table>`;
}
function opGraficoGrupos(D, G, alvo) {
    if (!G.grupos.length || typeof Chart === 'undefined') return;
    const area = document.createElement('div'); area.className = 'op-grafico'; const cv = document.createElement('canvas'); area.appendChild(cv); alvo.appendChild(area);
    const gs = G.grupos, temOrc = gs.some((g) => g.o != null);
    const base = (g) => (temOrc ? g.o : g.a), rotBase = temOrc ? 'Orçado ' + G.fonte : D.rotAnt;
    const mil = (v) => fmtBR(v / 1e3, Math.abs(v) >= 1e5 ? 0 : 1);
    opGraficos.push(new Chart(cv, {
        data: { labels: gs.map((g) => g.grupo), datasets: [
            { type: 'line', label: 'Realizado', data: gs.map((g) => g.r), borderColor: '#1A2740', backgroundColor: '#1A2740', borderWidth: 2.5, pointRadius: 3.5, tension: 0.15, order: 0 },
            { type: 'bar', label: rotBase, data: gs.map(base), backgroundColor: '#C9D6E3', borderRadius: 2, maxBarThickness: 46, order: 1 }] },
        options: { animation: false, responsive: true, maintainAspectRatio: false, devicePixelRatio: 2,
            layout: { padding: { top: 34 } },
            plugins: { legend: { position: 'bottom', labels: { boxWidth: 18, boxHeight: 6, font: { size: 11 } } }, tooltip: { enabled: false } },
            scales: { x: { grid: { display: false }, ticks: { font: { size: 10 } } }, y: { display: false, beginAtZero: true } } },
        plugins: [{ id: 'opRotulos', afterDatasetsDraw(c) {
            const g = c.ctx, linha = c.getDatasetMeta(0).data, barras = c.getDatasetMeta(1).data, topo = c.chartArea.top - 26;
            g.save(); g.textAlign = 'center';
            gs.forEach((x, i) => {
                const b = base(x), d = x.r - (b || 0);
                if (b) {
                    g.font = "600 9.5px 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif"; g.textBaseline = 'top';
                    g.fillStyle = Math.abs(opVar(x.r, b) || 0) < OP_RELEVANTE ? '#64748b' : d > 0 ? '#1f8a70' : '#C2560C';
                    g.fillText((d > 0 ? '+' : '') + mil(d), linha[i].x, topo);
                }
                g.fillStyle = '#1A2740'; g.font = "600 11px 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif"; g.textBaseline = 'bottom';
                g.fillText(mil(x.r), linha[i].x, linha[i].y - 6);
                if (b && barras[i]) { g.fillStyle = '#475569'; g.font = "400 9px 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif"; g.fillText(mil(b), barras[i].x, c.chartArea.bottom - 3); }
            });
            g.restore(); } }],
    }));
    const p = document.createElement('p'); p.className = 'op-nota';
    p.textContent = `Diretas (água + esgoto) por grupo, na ordem da leitura. Valores em R$ mil; no alto, a diferença realizado − ${temOrc ? 'orçado' : 'mês anterior'}.`;
    alvo.appendChild(p);
}

// ---- KPIs do mês contra o anterior: os mesmos quadros do Resumo (seguem os grupos marcados) ----
function opBlocoVolumes(D) {
    const cards = Array.from(document.querySelectorAll('#view-resumo .kpis-grid .kpi-card'));
    if (!cards.length) return '<p class="op-vazio">Sem indicadores.</p>';
    return '<div class="op-vols">' + cards.map((c) => {
        const tit = (c.querySelector('h3') || {}).textContent || '', val = (c.querySelector('.kpi-valor') || {}).textContent || '–';
        const dEl = c.querySelector('.kpi-delta'), dTxt = dEl ? dEl.textContent.replace(/vs mês anterior/i, 'vs ' + D.rotAnt) : '';
        const m = /([▲▼])\s*(-?[\d.,]+)%/.exec(dTxt), pct = m ? parseFloat(m[2].replace(',', '.')) / 100 * (m[1] === '▼' ? -1 : 1) : null;
        return `<div class="op-vol"><span class="op-rot">${garEsc(tit)}</span><b>${garEsc(val)}</b>${pct != null ? opSeta(pct, 'vs ' + D.rotAnt) : `<small>${garEsc(dTxt)}</small>`}</div>`;
    }).join('') + '</div>';
}

// ---- Top 5: maiores quedas e aumentos de faturamento (água) entre os clientes do Top 100 ----
// chave pessoal (navegador): só matrículas liberadas = Situação Conta do mês diferente de "Em análise" (base da aba Garantia)
let opSoLiberadas = false;
try { opSoLiberadas = localStorage.getItem('faturamento_op_top_liberadas') === '1'; } catch (e) { opSoLiberadas = false; }
const opLig = (v) => String(v == null ? '' : v).trim().replace(/\.0+$/, '');
function opTop5(D, tipo) {
    const chave = `${tipo}-agua`, d = lerJson('top100-dados');
    const tirar5 = (itens) => itens.sort((a, b) => b.v - a.v).slice(0, 5);
    if (d && d[chave]) {
        // as mesmas linhas da tabela Top 100 da aba Análise (SUP e grupos marcados); com a chave, as em análise saem antes do corte de 100
        const cols = d[chave].columns, ix = (n) => cols.indexOf(n), iSup = ix('Superintendência'), iG = ix('Grupo'), iL = ix('N. Ligação'),
            iN = ix('Nome_Cliente'), iV = ix((tipo === 'aumento' ? 'Aumento' : 'Queda') + '_Valor_R$'), grupos = gruposFiltro();
        const liberada = (l) => !opSoLiberadas || !garEmAnalise(GAR.porLig.get(opLig(l[iL])));
        const linhas = d[chave].data.filter((l) => (D.sup === 'TODAS' || iSup < 0 || l[iSup] === D.sup) && (!grupos || grupos.has(normGrupo(l[iG]))) && liberada(l))
            .slice(0, 100);
        return tirar5(linhas.map((l) => ({ nome: String(l[iN] == null ? '' : l[iN]).trim(), grupo: iG >= 0 ? normGrupo(l[iG]) : '', v: Math.abs(+l[iV] || 0) })));
    }
    const t = document.querySelector(`#view-analise .sup-top-bloco[data-sup="${D.sup}"] table[data-top="${chave}"]`)
        || document.querySelector(`.sup-top-bloco[data-sup="${D.sup}"] table[data-top="${chave}"]`)
        || document.querySelector(`table[data-top="${chave}"]`);
    if (!t) return [];
    const cab = Array.from(t.tHead.rows[0].cells).map((c) => planoNorm(c.textContent));
    const iNome = cab.findIndex((c) => /NOME/.test(c)), iGrupo = cab.findIndex((c) => /^GRUPO/.test(c)), iVal = cab.length - 1,
        iLig = cab.findIndex((c) => /LIGA/.test(c));
    return tirar5(Array.from(t.tBodies[0].rows).filter((tr) => tr.style.display !== 'none' && tr.cells.length === cab.length)
        .filter((tr) => !opSoLiberadas || iLig < 0 || !garEmAnalise(GAR.porLig.get(opLig(tr.cells[iLig].textContent))))
        .map((tr) => ({ nome: tr.cells[iNome].textContent.trim(), grupo: iGrupo >= 0 ? tr.cells[iGrupo].textContent.trim() : '', v: Math.abs(opNum(tr.cells[iVal].textContent) || 0) })));
}
function opBlocoTop(D) {
    // o nome comprido quebra linha; o grupo e o valor ficam sempre inteiros, em colunas fixas
    const lista = (tit, cls, itens) => `<div class="op-top ${cls}"><div class="op-top-tit">${tit}</div>`
        + (itens.length ? itens.map((x, i) => `<div class="op-top-lin"><span class="op-top-nome" title="${garEsc(x.nome)}">${i + 1}. ${garEsc(x.nome)}</span>`
            + `<span class="op-top-grupo">${x.grupo ? `Grupo ${garEsc(x.grupo)}` : ''}</span><b>${opMoeda(x.v, 2)}</b></div>`).join('')
            : `<p class="op-vazio">${opSoLiberadas && !GAR.dados ? 'Carregando as matrículas…' : 'Sem clientes.'}</p>`) + '</div>';
    const m = opMesCurto((opEditor() || { dataset: {} }).dataset.ref || '');
    return `<div class="op-tops">${lista('Maiores aumentos de faturamento — ' + garEsc(m), 'op-top-pos', opTop5(D, 'aumento'))}`
        + `${lista('Maiores quedas de faturamento — ' + garEsc(m), 'op-top-neg', opTop5(D, 'queda'))}</div>`;
}
function opCabTop() {
    const tem = !!document.getElementById('garantia-dados');
    return (opSoLiberadas ? '<small class="op-h-dir">somente matrículas liberadas (fora de "Em análise")</small>' : '')
        + (tem ? `<button type="button" class="btn-just gar-filtro op-so-tela op-top-chave${opSoLiberadas ? ' ativo' : ''}" id="opTopLiberadas" aria-pressed="${opSoLiberadas}"`
            + ` title="Mostra no Top 5 só as matrículas cuja conta do mês não está em análise">Somente liberadas</button>` : '');
}

function opSecao(titulo, extra) {
    const s = document.createElement('section'); s.className = 'op-secao';
    if (titulo) s.innerHTML = `<h3>${titulo}${extra || ''}</h3>`;
    return s;
}
function opDesenhar() {
    const folha = document.getElementById('opFolha'); if (!folha) return;
    if (!opAtiva()) return;
    opGraficos.forEach((g) => { try { g.destroy(); } catch (e) { /* já destruído */ } }); opGraficos = [];
    const D = opDados(), ed = opEditor(), corte = ed ? ed.dataset.corte : '';
    D.refs = Array.from(new Set(Array.from(document.querySelectorAll('#view-dre th[data-tipo="orc"]')).map((th) => th.dataset.src)));
    const nomeSup = D.sup === 'TODAS' ? 'Todas as superintendências' : D.sup;
    // data da folha: leitura do último grupo lido (o de data mais recente no cronograma entre os que já têm faturamento)
    const G = opGrupos(D);
    const lido = G.grupos.filter((g) => g.iso && g.r > 0).sort((a, b) => a.iso.localeCompare(b.iso)).pop();
    D.ultimo = D.vigente && lido ? { grupo: lido.grupo, data: lido.data, dataAno: lido.data + '/' + lido.iso.slice(2, 4), completa: lido.data + '/' + lido.iso.slice(0, 4) } : null;
    folha.innerHTML = '';
    const cab = document.createElement('header'); cab.className = 'op-cab';
    cab.innerHTML = `<span class="op-cab-sub">Águas do Rio · One page</span><h2>${garEsc(nomeSup)}: Acompanhamento do Faturamento — ${garEsc(D.ultimo ? D.ultimo.dataAno : corte.slice(0, 6) + corte.slice(8))}</h2>`;
    folha.appendChild(cab);
    const dest = opBlocoDestaque(D);
    const s1 = opSecao('➤ Faturamento', typeof dest === 'object' && dest.ant ? `<small class="op-h-dir">${dest.ant}</small>` : '');
    s1.insertAdjacentHTML('beforeend', `<div class="op-painel">${typeof dest === 'object' ? dest.html : dest}</div>${opBlocoCards(D)}`);
    folha.appendChild(s1);
    const L = opLinhasPrev(D), dica = D.vigente ? 'tendência = realizado + forecast da aba Forecast' : 'mês fechado';
    const sA = opSecao('Faturamento aberto', `<small class="op-h-dir">${garEsc(opMesCurto(D.mes))} · ${dica}</small>`);
    sA.insertAdjacentHTML('beforeend', opTabAberta(D, opAbertoFat(D, L), OP_ABERTO_FAT, 'bruto', 'Faturamento bruto'));
    folha.appendChild(sA);
    const s2 = opSecao(`Acompanhamento semanal por grupo — realizado × ${G.fonte ? garEsc('orçado ' + G.fonte) : 'orçado'} e ${garEsc(D.rotAnt)}`,
        `<small class="op-h-dir">${garEsc(opMesCurto(ed ? ed.dataset.ref : ''))} · diretas (água + esgoto) · clique na semana para abrir</small>`);
    s2.insertAdjacentHTML('beforeend', opBlocoGrupos(D, G)); folha.appendChild(s2); opGraficoGrupos(D, G, s2);
    const s3 = opSecao(''); s3.classList.add('op-secao-faixa');
    s3.insertAdjacentHTML('beforeend', `<div class="op-faixa">Indicadores do mês — ${garEsc(opMesCurto(ed ? ed.dataset.ref : ''))} vs ${garEsc(D.rotAnt)}</div>${opBlocoVolumes(D)}`);
    folha.appendChild(s3);
    if (opSoLiberadas && !GAR.dados && document.getElementById('garantia-dados')) garCarregar().then(() => { if (opAtiva()) opDesenhar(); });
    const s4 = opSecao('Top 5 clientes', opCabTop()); s4.classList.add('op-secao-top'); s4.insertAdjacentHTML('beforeend', opBlocoTop(D)); folha.appendChild(s4);
    // indiretas sempre depois de tudo das diretas (abertura semanal, indicadores e Top 5)
    const sI = opSecao('Indiretas por classe', `<small class="op-h-dir">${garEsc(opMesCurto(D.mes))} · serviços avulsos faturados</small>`);
    sI.insertAdjacentHTML('beforeend', opTabAberta(D, L, OP_ABERTO_IND, 'tot', 'Total indiretas'));
    folha.appendChild(sI);
    const rod = document.createElement('footer'); rod.className = 'op-rodape';
    rod.innerHTML = `<span>Fonte: painel de faturamento · ${garEsc(nomeSup)} · competência ${garEsc(opMesCurto(D.mes))} · orçado ${garEsc(D.ref || '—')}`
        + (D.ultimo ? ` · último grupo lido: ${garEsc(D.ultimo.grupo)} (leitura ${garEsc(D.ultimo.completa)})` : ` · dados até ${garEsc(corte)} (D-1)`) + ` · gerado em ${new Date().toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}</span><b class="op-marca">Águas do Rio</b>`;
    folha.appendChild(rod);
}
// tendência e forecast acompanham as edições do forecast (aba Forecast ou Indiretas, ou vindas da pasta)
document.addEventListener('forecast-recalculado', () => opDesenhar());
document.addEventListener('click', (e) => {
    const t = e.target;
    if (t.id === 'opPdf') { gerarOnePage(); return; }
    if (t.id === 'opTopLiberadas') {
        opSoLiberadas = !opSoLiberadas;
        try { localStorage.setItem('faturamento_op_top_liberadas', opSoLiberadas ? '1' : '0'); } catch (er) { /* sem armazenamento */ }
        opDesenhar(); return;
    }
    const sem = t.closest && t.closest('#opFolha tr.op-sem');
    if (sem) {
        const n = +sem.dataset.semana; if (!opSemanasAbertas) opSemanasAbertas = new Set();
        if (opSemanasAbertas.has(n)) opSemanasAbertas.delete(n); else opSemanasAbertas.add(n);
        opDesenhar();
    }
});

// PDF de uma página só (da altura da folha): a folha é copiada (gráfico como imagem, sem botões e dicas de edição) para um documento à
// parte, fotografada (html2canvas) e posta numa página do tamanho de um slide (jsPDF). Sem as bibliotecas, imprime.
async function gerarOnePage(libs) {
    if (opSoLiberadas && document.getElementById('garantia-dados')) await garCarregar();      // o Top 5 precisa da situação das contas
    if (!opAtiva()) mostrarView('onepage'); else opDesenhar();
    const folha = document.getElementById('opFolha');
    const copia = folha.cloneNode(true);
    const origs = folha.querySelectorAll('canvas'), copias = copia.querySelectorAll('canvas');
    origs.forEach((cv, i) => { try { const img = new Image(); img.src = cv.toDataURL('image/png'); img.className = 'op-grafico-img'; copias[i].replaceWith(img); } catch (e) { copias[i].remove(); } });
    copia.querySelectorAll('[contenteditable]').forEach((x) => x.removeAttribute('contenteditable'));
    copia.querySelectorAll('.op-so-tela').forEach((x) => x.remove());
    copia.removeAttribute('id'); copia.style.transform = ''; copia.classList.add('op-pdf');
    const nomeMes = opMesCurto(ESTADO.mes || '');
    const nome = `OnePage_${ESTADO.sup}_${nomeMes}`;
    if (!libs) { try { const p = window.parent; if (p && p !== window && p.libsPdfSite) libs = await p.libsPdfSite(); } catch (e) { libs = null; } }
    const l = await obterLibsPdf(libs);
    const aviso = document.createElement('div');
    aviso.textContent = 'Gerando o PDF do One page…';
    aviso.style.cssText = 'position:fixed; right:16px; bottom:16px; z-index:99999; background:#1A2740; color:#fff; padding:10px 16px; border-radius:8px; font:600 13px sans-serif; box-shadow:0 6px 20px rgba(0,0,0,.25);';
    document.body.appendChild(aviso);
    const fr = document.createElement('iframe');
    fr.setAttribute('aria-hidden', 'true'); fr.title = 'One page';
    fr.style.cssText = `position:fixed; left:0; top:0; width:${OP_W}px; height:800px; border:0; opacity:0; pointer-events:none; z-index:-1;`;
    document.body.appendChild(fr);
    try {
        const estilos = Array.from(document.querySelectorAll('style')).map((s) => s.textContent).join('\n');
        const doc = fr.contentDocument;
        doc.open();
        doc.write('<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><style>' + estilos
            + '\nhtml, body { margin:0; padding:0; background:#FFFFFF; overflow:hidden !important; }</style></head><body>' + copia.outerHTML + '</body></html>');
        doc.close();
        const imgs = Array.from(doc.images);
        await Promise.race([Promise.all([...imgs.map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = r; }))),
            doc.fonts && doc.fonts.ready ? doc.fonts.ready.catch(() => null) : null]), new Promise((r) => setTimeout(r, 4000))]);
        await Promise.race([injetaLibs(doc, l), new Promise((_, r) => setTimeout(() => r(new Error('bibliotecas do PDF demoraram')), 15000))]);
        const w = fr.contentWindow;
        if (!w.jspdf || !w.html2canvas) throw new Error('bibliotecas do PDF indisponíveis');
        const raiz = doc.body.firstElementChild, alt = Math.ceil(raiz.scrollHeight);
        fr.style.height = alt + 'px'; await new Promise((r) => setTimeout(r, 50));
        const foto = await w.html2canvas(raiz, { scale: 2, backgroundColor: '#FFFFFF', logging: false, imageTimeout: 3000,
            windowWidth: OP_W, windowHeight: alt, width: OP_W, height: alt });
        const PW = 210, PH = PW * alt / OP_W;                          // largura de uma A4; a altura acompanha a folha
        const pdf = new w.jspdf.jsPDF({ orientation: 'portrait', unit: 'mm', format: [PW, PH], compress: true });
        pdf.addImage(foto.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, PW, PH);
        const url = URL.createObjectURL(new Blob([pdf.output('blob')], { type: 'application/pdf' }));
        const a = document.createElement('a');
        a.href = url; a.download = nome.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9_-]+/g, '_') + '.pdf';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (erro) {
        console.warn('PDF do One page indisponível, usando a impressão:', erro);
        const cont = document.createElement('div'); cont.id = 'view-executivo'; cont.appendChild(copia);
        imprimirDocumentoLeve(cont);
    } finally {
        fr.remove(); aviso.remove();
    }
}
document.addEventListener('DOMContentLoaded', () => opDesenhar());

// ===== Prints para a apresentação semanal: imagem (PNG) em alta resolução de um quadro do painel =====
// 'dre' = tabela do Forecast (Realizado + Forecast, sem a coluna Forecast); 'garantia' = quadros do Resumo de Ganhos;
// 'indiretas' = indiretas (R$) e, logo abaixo, o plano de ação do mês (se houver). Segue os filtros da tela.
// A folha é montada à parte numa largura fixa (letra do tamanho da tela) e fotografada em escala 3: colada no slide, fica nítida.
const PRINT_SLIDE = 2.05;      // área livre de um slide 16:9 abaixo do título (largura ÷ altura)
const PRINT_TIPOS = { dre: ['DRE', 1000], garantia: ['Analise_Garantia', 1300], indiretas: ['Indiretas_Plano', 1300] };
function printAviso(texto, ms) {
    let a = document.getElementById('printAviso');
    if (!a) {
        a = document.createElement('div'); a.id = 'printAviso';
        a.style.cssText = 'position:fixed; right:16px; bottom:16px; z-index:99999; background:#1A2740; color:#fff; padding:10px 16px; border-radius:8px; font:600 13px sans-serif; box-shadow:0 6px 20px rgba(0,0,0,.25); max-width:360px;';
        document.body.appendChild(a);
    }
    a.textContent = texto; clearTimeout(a._t);
    if (ms) a._t = setTimeout(() => a.remove(), ms);
}
async function printItens(tipo) {
    const q = (sel) => document.querySelector(sel), sup = ESTADO.sup, mes = ESTADO.mes;
    const limpa = (el, cls) => {
        if (!el) return null;
        const c = el.cloneNode(true);
        c.querySelectorAll('[contenteditable]').forEach((x) => x.removeAttribute('contenteditable'));
        c.querySelectorAll('[id]').forEach((x) => x.removeAttribute('id')); c.removeAttribute('id');
        c.querySelectorAll('[title]').forEach((x) => x.removeAttribute('title'));
        if (cls) c.classList.add(...cls.split(' '));
        return c;
    };
    if (tipo === 'dre') return [limpa(q(`#view-forecast .prev-bloco[data-sup="${sup}"] table.tabela-previsao`), 'prev-sem-forecast')];
    if (tipo === 'garantia') {
        await garCarregar(); garGrupos = gruposFiltro(); garDesenharResumo();
        return [limpa(q('#garResumo'))];
    }
    const ind = limpa(q(`#view-indiretas .sup-bloco[data-sup="${sup}"][data-mes="${mes}"] table.tabela-previsao`), 'prev-sem-forecast');
    const plano = limpa(q('#plano-card.tem-dados #planoTabela'));
    return [ind, plano];
}
async function gerarPrint(tipo, libs) {
    const [rotulo, W] = PRINT_TIPOS[tipo] || PRINT_TIPOS.dre;
    const itens = (await printItens(tipo)).filter(Boolean);
    if (!itens.length) { printAviso('Nada para fotografar: o quadro não existe para os filtros da tela.', 5000); throw new Error('sem quadro'); }
    if (!libs) { try { const p = window.parent; if (p && p !== window && p.libsPdfSite) libs = await p.libsPdfSite(); } catch (e) { libs = null; } }
    const l = await obterLibsPdf(libs);
    printAviso('Gerando o print…');
    const folha = document.createElement('div'); folha.className = 'print-folha print-' + tipo;
    itens.forEach((el) => { const b = document.createElement('div'); b.className = 'print-bloco'; b.appendChild(el); folha.appendChild(b); });
    const fr = document.createElement('iframe');
    fr.setAttribute('aria-hidden', 'true'); fr.title = 'Print';
    fr.style.cssText = `position:fixed; left:0; top:0; width:${W}px; height:800px; border:0; opacity:0; pointer-events:none; z-index:-1;`;
    document.body.appendChild(fr);
    try {
        const estilos = Array.from(document.querySelectorAll('style')).map((x) => x.textContent).join('\n');
        const doc = fr.contentDocument;
        doc.open();
        doc.write('<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><style>' + estilos
            + '\nhtml, body { margin:0; padding:0; background:#FFFFFF; overflow:hidden !important; }</style></head><body>' + folha.outerHTML + '</body></html>');
        doc.close();
        await Promise.race([doc.fonts && doc.fonts.ready ? doc.fonts.ready.catch(() => null) : null, new Promise((r) => setTimeout(r, 3000))]);
        await Promise.race([injetaLibs(doc, l), new Promise((_, r) => setTimeout(() => r(new Error('bibliotecas demoraram')), 15000))]);
        const w = fr.contentWindow;
        if (!w.html2canvas) throw new Error('html2canvas indisponível');
        const raiz = doc.body.firstElementChild;
        // tabela mais larga que a folha: a folha alarga para caber inteira (com a margem dos dois lados)
        let largura = W;
        raiz.querySelectorAll('table').forEach((t) => { largura = Math.max(largura, Math.ceil(t.scrollWidth) + 34); });
        fr.style.width = largura + 'px'; await new Promise((r) => setTimeout(r, 50));
        if (tipo === 'indiretas') {
            // indiretas + plano vão sozinhos num slide: testa larguras e fica com a que, encaixada na área do slide
            // (PRINT_SLIDE, largura ÷ altura), deixa a letra maior — textos longos do plano quebram menos e a imagem fica baixa e larga
            let melhor = null;
            for (let L = largura; L <= 3400; L += 100) {
                fr.style.width = L + 'px'; await new Promise((r) => requestAnimationFrame(() => r()));
                const H = Math.ceil(raiz.scrollHeight), nota = Math.min(1 / L, 1 / (PRINT_SLIDE * H));
                if (!melhor || nota > melhor.nota) melhor = { L, nota };
            }
            largura = melhor.L; fr.style.width = largura + 'px'; await new Promise((r) => setTimeout(r, 50));
        }
        const alt = Math.ceil(raiz.scrollHeight);
        fr.style.width = largura + 'px'; fr.style.height = alt + 'px'; await new Promise((r) => setTimeout(r, 50));
        const foto = await w.html2canvas(raiz, { scale: Math.min(3, 6600 / largura), backgroundColor: '#FFFFFF', logging: false,
            windowWidth: largura, windowHeight: alt, width: largura, height: alt });
        const blob = await new Promise((ok) => foto.toBlob(ok, 'image/png'));
        const url = URL.createObjectURL(blob), a = document.createElement('a');
        a.href = url; a.download = `Print_${rotulo}_${ESTADO.sup}_${opMesCurto(ESTADO.mes || '')}`.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9_-]+/g, '_') + '.png';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        printAviso('Print baixado (PNG).', 5000);
        return blob;
    } catch (erro) {
        printAviso('Não foi possível gerar o print: ' + erro.message, 6000);
        throw erro;
    } finally {
        fr.remove();
    }
}

// chave "Somente grupos liberados" do Resumo de Ganhos: preferência de cada pessoa (lembrada neste navegador)
try { GAR.soLiberados = localStorage.getItem('faturamento_gar_so_liberados') === '1'; } catch (e) { GAR.soLiberados = false; }
document.addEventListener('click', (e) => {
    if (e.target.id !== 'garSoLiberados') return;
    GAR.soLiberados = !GAR.soLiberados;
    try { localStorage.setItem('faturamento_gar_so_liberados', GAR.soLiberados ? '1' : '0'); } catch (er) { /* sem armazenamento */ }
    garDesenharResumo();
});

// Análise > Cortadas com consumo: linhas pelos grupos marcados e pela SUP do cabeçalho, totais refeitos
function cortRecalcular() {
    const t = document.getElementById('tabela-cortadas-consumo');
    if (!t) return;
    const marcados = new Set(Array.from(document.querySelectorAll('.chk-grupo:checked')).map(c => c.value));
    const todos = !document.querySelector('.chk-grupo');
    let qtd = 0, med = 0, val = 0, reinc = 0;
    t.querySelectorAll('tbody tr').forEach(tr => {
        const ok = (todos || marcados.has(tr.dataset.grupo)) && (ESTADO.sup === 'TODAS' || tr.dataset.sup === ESTADO.sup);
        tr.style.display = ok ? '' : 'none';
        if (!ok) return;
        qtd++; med += parseFloat(tr.dataset.med) || 0; val += parseFloat(tr.dataset.val) || 0; reinc += tr.dataset.reinc === '1' ? 1 : 0;
    });
    const f = (v, d) => v.toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d });
    const p = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
    p('cort-qtd', f(qtd, 0)); p('cort-med', f(med, 1)); p('cort-val', 'R$ ' + f(val, 2)); p('cort-reinc', f(reinc, 0));
}
document.addEventListener('DOMContentLoaded', cortRecalcular);
// seta da lista: baixa as linhas visíveis (grupos e SUP filtrados); números voltam a ser números
document.addEventListener('click', async function (e) {
    const b = e.target.closest && e.target.closest('.btn-cortadas');
    const t = document.getElementById('tabela-cortadas-consumo');
    if (!b || !t) return;
    const cols = Array.from(t.querySelectorAll('thead th')).map(th => th.textContent.trim());
    const num = (s) => { const x = parseFloat(s.replace('R$', '').replace(/\./g, '').replace(',', '.')); return isNaN(x) ? s : x; };
    const linhas = Array.from(t.querySelectorAll('tbody tr')).filter(tr => tr.style.display !== 'none')
        .map(tr => Array.from(tr.children).map((td, i) => { const s = td.textContent.trim(); return [6, 7, 9, 10, 11].includes(i) ? num(s) : s; }));   // Economias, medidos, faturado e valor
    const sup = ESTADO.sup !== 'TODAS' ? '_' + ESTADO.sup.replace(/[^A-Za-z0-9]/g, '') : '';
    await baixarPlanilha(cols, linhas, `Cortadas_com_consumo_${b.dataset.mes}${sup}.xlsx`);
});
