const CHAVE_JUSTIFICATIVA = '__CHAVE_JUSTIFICATIVA__';

const VIEWS = ['resumo', 'dre', 'tabelas', 'indiretas', 'dados'];
function mostrarView(view) {
    VIEWS.forEach(v => {
        document.getElementById('view-' + v).classList.toggle('ativo', v === view);
        document.getElementById('view-' + v).style.display = (v === view) ? 'block' : 'none';
        document.getElementById('btn-' + v).classList.toggle('active', v === view);
    });
    const seletor = document.getElementById('seletorSup');
    if (seletor) seletor.hidden = !(view === 'dre' || view === 'indiretas');
}

// Filtros da DRE/Indiretas: superintendência, mês e referência (RF / SUP / ambos)
const ESTADO = { sup: 'TODAS', mes: null, ref: null };
function definirFiltros(parcial) {
    Object.assign(ESTADO, parcial || {});
    document.querySelectorAll('.sup-bloco').forEach(b => {
        b.style.display = (b.dataset.sup === ESTADO.sup && b.dataset.mes === ESTADO.mes) ? 'block' : 'none';
    });
    aplicarFontes();
    [['selSup', ESTADO.sup], ['selMes', ESTADO.mes], ['selRef', ESTADO.ref]].forEach(([id, v]) => {
        const el = document.getElementById(id); if (el && v) el.value = v;
    });
    desenharGraficosIndiretas();
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
        el.style.display = (el.dataset.combo === chave && sel.length === 2) ? '' : 'none';
    });
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
}

function recalcularTotais() {
    document.querySelectorAll('table.tabela-comparativo').forEach(function (tabela) {
        const marcados = Array.from(document.querySelectorAll('.chk-grupo:checked')).map(c => c.value);
        let fatAt=0, fatAnt=0, ecoAt=0, ecoAnt=0, volAt=0, volAnt=0, diasAtSoma=0, diasAntSoma=0, diasCount=0;
        tabela.querySelectorAll('tbody tr[data-grupo]').forEach(function (tr) {
            const grupo = tr.getAttribute('data-grupo');
            if (grupo === '' || !marcados.includes(grupo)) return;
            fatAt += parseFloat(tr.getAttribute('data-fat-atual')) || 0;
            fatAnt += parseFloat(tr.getAttribute('data-fat-anterior')) || 0;
            ecoAt += parseFloat(tr.getAttribute('data-eco-atual')) || 0;
            ecoAnt += parseFloat(tr.getAttribute('data-eco-anterior')) || 0;
            volAt += parseFloat(tr.getAttribute('data-vol-atual')) || 0;
            volAnt += parseFloat(tr.getAttribute('data-vol-anterior')) || 0;
            diasAtSoma += parseFloat(tr.getAttribute('data-dias-atual')) || 0;
            diasAntSoma += parseFloat(tr.getAttribute('data-dias-anterior')) || 0;
            diasCount++;
        });
        const linhaTotal = tabela.querySelector('tbody tr.linha-media');
        if (!linhaTotal) return;
        const vmAt = ecoAt ? volAt / ecoAt : 0;
        const vmAnt = ecoAnt ? volAnt / ecoAnt : 0;
        const tarAt = volAt ? fatAt / volAt : 0;
        const tarAnt = volAnt ? fatAnt / volAnt : 0;
        const ticAt = ecoAt ? fatAt / ecoAt : 0;
        const ticAnt = ecoAnt ? fatAnt / ecoAnt : 0;
        const diasAt = diasCount ? diasAtSoma / diasCount : 0;
        const diasAnt = diasCount ? diasAntSoma / diasCount : 0;

        function fmt(v, dec) {
            dec = dec || 0;
            return v.toLocaleString('pt-BR', { minimumFractionDigits: dec, maximumFractionDigits: dec });
        }
        function setCell(campo, valor, dec) {
            const el = linhaTotal.querySelector('[data-field="' + campo + '"]');
            if (el) el.innerText = fmt(valor, dec);
        }
        function setDelta(campo, valor, pct) {
            const el = linhaTotal.querySelector('[data-field="' + campo + '"]');
            if (!el) return;
            const cor = valor < 0 ? '#C2560C' : '#05050D';
            el.style.color = cor;
            el.innerText = pct ? (valor * 100).toFixed(1).replace('.', ',') + '%' : fmt(valor, 0);
        }

        setCell('dias-atual', diasAt, 1);
        setCell('dias-anterior', diasAnt, 1);
        setCell('fat-atual', fatAt);
        setCell('fat-anterior', fatAnt);
        setDelta('delta-fat', fatAt - fatAnt);
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
        setDelta('delta-vm', vmAt - vmAnt);
        setCell('tar-atual', tarAt, 2);
        setCell('tar-anterior', tarAnt, 2);
        setDelta('delta-tar', tarAt - tarAnt);
        setCell('tic-atual', ticAt, 2);
        setCell('tic-anterior', ticAnt, 2);
        setDelta('delta-tic', ticAt - ticAnt);
    });
}

function recalcularTotalAtivaCortada() {
    const tabela = document.querySelector('table.tabela-ativa-cortada');
    if (!tabela) return;
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

function recalcularTabelaMinimo() {
    const tabela = document.querySelector('table.tabela-min-consumo');
    if (!tabela) return;
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

function recalcularMatrizGrupos() {
    const tabela = document.querySelector('table.tabela-matriz-grupo');
    if (!tabela) return;
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
    let fatAguaAt=0, fatAguaAnt=0, fatEsgotoAt=0, fatEsgotoAnt=0;
    tabelaResumo.querySelectorAll('tr[data-grupo]').forEach(function (tr) {
        const grupo = tr.getAttribute('data-grupo');
        if (!marcados.includes(grupo)) return;
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
        const novosLabels = [], novosAtuais = [], novosAnteriores = [];
        original.labels.forEach(function (label, idx) {
            if (marcados.includes(label)) {
                novosLabels.push(label);
                novosAtuais.push(original.atual[idx]);
                novosAnteriores.push(original.anterior[idx]);
            }
        });
        chart.data.labels = novosLabels;
        chart.data.datasets[1].data = novosAtuais;
        chart.data.datasets[0].data = novosAnteriores;
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

function carregarJustificativas() {
    const salvo = localStorage.getItem(CHAVE_JUSTIFICATIVA);
    if (salvo) document.getElementById('lista-justificativas').innerHTML = salvo;
    aplicarBotoesRemover();
}

function salvarJustificativas() {
    const conteudo = document.getElementById('lista-justificativas').innerHTML;
    localStorage.setItem(CHAVE_JUSTIFICATIVA, conteudo);
}

function toggleEdicaoJustificativa() {
    const lista = document.getElementById('lista-justificativas');
    const btn = document.getElementById('btnEditarJust');
    const emEdicao = lista.classList.contains('modo-edicao');
    if (emEdicao) {
        lista.classList.remove('modo-edicao');
        lista.querySelectorAll('p').forEach(p => p.contentEditable = false);
        btn.innerText = 'Editar';
        salvarJustificativas();
    } else {
        lista.classList.add('modo-edicao');
        lista.querySelectorAll('p').forEach(p => p.contentEditable = true);
        btn.innerText = 'Salvar';
    }
}

function adicionarJustificativa() {
    const lista = document.getElementById('lista-justificativas');
    const novoP = document.createElement('p');
    novoP.innerHTML = '<strong>Novo item:</strong> clique em Editar e escreva aqui...';
    novoP.contentEditable = lista.classList.contains('modo-edicao');
    const btnRemover = document.createElement('button');
    btnRemover.className = 'btn-remover-item';
    btnRemover.innerText = '';
    btnRemover.onclick = function () { novoP.remove(); salvarJustificativas(); };
    novoP.appendChild(btnRemover);
    lista.appendChild(novoP);
    if (!lista.classList.contains('modo-edicao')) toggleEdicaoJustificativa();
    aplicarBotoesRemover();
    salvarJustificativas();
}

function limparJustificativas() {
    if (!confirm('Remover todas as justificativas? Esta ação não pode ser desfeita.')) return;
    document.getElementById('lista-justificativas').innerHTML = '';
    salvarJustificativas();
}

function aplicarBotoesRemover() {
    const lista = document.getElementById('lista-justificativas');
    lista.querySelectorAll('p').forEach(function (p) {
        if (p.querySelector('.btn-remover-item')) return;
        const btnRemover = document.createElement('button');
        btnRemover.className = 'btn-remover-item';
        btnRemover.innerText = '';
        btnRemover.onclick = function () { p.remove(); salvarJustificativas(); };
        p.appendChild(btnRemover);
    });
}

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
