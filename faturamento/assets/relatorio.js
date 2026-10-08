const CHAVE_JUSTIFICATIVA = '__CHAVE_JUSTIFICATIVA__';

const VIEWS = ['resumo', 'tabelas', 'analise', 'indiretas', 'forecast', 'dre', 'dados'];
function mostrarView(view) {
    VIEWS.forEach(v => {
        document.getElementById('view-' + v).classList.toggle('ativo', v === view);
        document.getElementById('view-' + v).style.display = (v === view) ? 'block' : 'none';
        document.getElementById('btn-' + v).classList.toggle('active', v === view);
    });
    const seletor = document.getElementById('seletorSup');
    if (seletor) seletor.hidden = !(view === 'dre' || view === 'indiretas' || view === 'forecast');
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
    [['selSup', ESTADO.sup], ['selMes', ESTADO.mes], ['selRef', ESTADO.ref]].forEach(([id, v]) => {
        const el = document.getElementById(id); if (el && v) el.value = v;
    });
    desenharGraficosIndiretas();
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
    caixas.forEach(c => {
        const ok = !algum || daSup(c);
        c.checked = ok;
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
            const seta = card.querySelector('.btn-sitl-dl'); if (seta) seta.style.display = at[0] ? '' : 'none';
        });
    });
}

// Botões Excel com alternativa: com grupos desmarcados, baixa o CSV refeito só com os grupos marcados
async function baixarCsvFiltrado(alt) {
    const tipo = alt.dataset.csvFiltrado, sufixo = '_grupos_filtrados.csv';
    if (tipo === 'top') {
        let colunas = null; const linhas = [];
        alt.dataset.tops.split(',').forEach(k => {
            const r = topLinhas(k, alt.dataset.sup || 'TODAS'); if (!r) return;
            colunas = ['Lista'].concat(r.colunas);
            r.linhas.forEach(l => linhas.push([k.endsWith('agua') ? 'Água' : 'Esgoto'].concat(l)));
        });
        if (colunas) baixarTexto(csvDe(colunas, linhas), alt.dataset.nome + sufixo);
    } else if (tipo === 'semfat') {
        const el = document.getElementById('semfat-dados'); if (!el) return;
        const bin = atob(el.textContent.trim()), bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const texto = await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
        const filtros = {}; filtros[el.dataset.colGrupo] = gruposFiltro();
        const csv = filtraCsv(texto, filtros);
        if (csv !== null) baixarTexto(csv, alt.dataset.nome + sufixo);
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
    if (b) sitlVisao(b.dataset.visao);
});
document.addEventListener('DOMContentLoaded', function () {
    let v = null; try { v = localStorage.getItem('faturamento_sitl_visao'); } catch (e) { /* sem armazenamento */ }
    if (v === 'sintetica') sitlVisao(v);
});

// Setas da Situação de lançamento: a do título baixa todas as matrículas; a de cada card, as daquela situação (analítica)
// ou de todos os códigos do grupo (sintética) — sempre da SUP do quadro e dos grupos marcados.
// A lista vem embutida uma vez, em gzip (script#sitl-detalhe); o navegador descompacta na hora.
document.addEventListener('click', async function (e) {
    const b = e.target.closest && e.target.closest('.btn-sitl-dl');
    if (!b) return;
    const el = document.getElementById('sitl-detalhe');
    if (!el) return;
    try {
        const bin = atob(el.textContent.trim()), bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const fluxo = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
        const texto = await new Response(fluxo).text();
        const filtros = {};
        if (b.dataset.sit !== undefined) filtros[el.dataset.colSit] = b.dataset.sit;
        else if (b.dataset.gsit !== undefined) filtros[el.dataset.colGsit] = b.dataset.gsit;
        if (b.dataset.sup && b.dataset.sup !== 'TODAS') filtros['Superintendência'] = b.dataset.sup;
        const grupos = gruposFiltro();
        if (grupos) filtros['Grupo'] = grupos;
        const csv = filtraCsv(texto, filtros);
        if (csv === null) return;
        const partes = [b.dataset.sit || b.dataset.gsit || 'todas', b.dataset.sup && b.dataset.sup !== 'TODAS' ? b.dataset.sup : '']
            .filter(Boolean).join('_');
        const nome = el.dataset.arquivo + '_' + partes.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
            .replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '') + (grupos ? '_grupos_filtrados' : '') + '.csv';
        const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
        const a = document.createElement('a');
        a.href = url; a.download = nome; document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (erro) {
        alert('Não foi possível baixar a lista desta situação neste navegador (' + erro.message + ').');
    }
});

// base64 (e gzip, com data-gz="1") embutido num <script> → bytes do arquivo
async function bytesEmbutidos(el) {
    const bin = atob(el.textContent.trim()), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    if (el.dataset.gz !== '1') return bytes;
    const fluxo = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    return new Uint8Array(await new Response(fluxo).arrayBuffer());
}

// Botões "Base: ... (CSV)": a base vem embutida uma vez (script#base-dl-<chave>, comprimida) e vários botões a usam
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
    const url = URL.createObjectURL(new Blob([conteudo], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url; a.download = nome; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
});

// Botões "Baixar (Excel)": o arquivo vem embutido no relatório em base64
document.addEventListener('click', function (e) {
    const b = e.target.closest && e.target.closest('.btn-baixar');
    if (!b) return;
    const alt = b.closest('[data-csv-filtrado]');
    if (alt && gruposFiltro()) { baixarCsvFiltrado(alt); return; }
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
try { const salvo = JSON.parse(localStorage.getItem(PREV_CHAVE_LS) || '{}'); prevEdicoes = salvo.edicoes || {}; prevOculta = !!salvo.oculta; prevOcultaInd = !!salvo.ocultaInd; } catch (e) { /* sem armazenamento: vale só nesta abertura */ }
function prevSalvar() { try { localStorage.setItem(PREV_CHAVE_LS, JSON.stringify({ edicoes: prevEdicoes, oculta: prevOculta, ocultaInd: prevOcultaInd })); } catch (e) { /* ignora */ } }

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

function prevRecalcularTodas() { document.querySelectorAll('table.tabela-previsao').forEach(prevRecalcular); }

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
}
prevRecalcularTodas(); previsaoAplicarVisibilidade();


// Diretas: por padrão só as colunas principais; o botão mostra as demais (dias de leitura, Δ absolutos, volume médio)
function alternarColunas() {
    const v = document.getElementById('view-tabelas'), compacto = v.classList.toggle('compacto');
    document.getElementById('btn-colunas').textContent = compacto ? 'Mostrar todas as colunas' : 'Mostrar só as principais';
    v.querySelectorAll('th[data-full]').forEach(th => { th.colSpan = parseInt(compacto ? th.dataset.comp : th.dataset.full, 10); });
    v.querySelectorAll('th[data-full]').forEach(th => { if (compacto) th.colSpan = parseInt(th.dataset.comp, 10); });
}
document.querySelectorAll('#view-tabelas th[data-full]').forEach(th => { th.colSpan = parseInt(th.dataset.comp, 10); });


// ===== Relatório executivo (PDF): copia o que está na tela agora — filtros, orçado escolhido e botões de ocultar valem =====
function gerarExecutivo(libs) {
    const antigo = document.getElementById('view-executivo'); if (antigo) antigo.remove();
    const cont = document.createElement('div'); cont.id = 'view-executivo';
    if (document.getElementById('view-tabelas').classList.contains('compacto')) cont.classList.add('compacto');
    const clona = (el) => {
        if (!el) return null;
        const c = el.cloneNode(true), origs = el.querySelectorAll('canvas'), copias = c.querySelectorAll('canvas');
        origs.forEach((cv, i) => {                                    // gráfico: vira imagem do que está desenhado
            try { const img = new Image(); img.src = cv.toDataURL('image/png'); img.className = 'exec-grafico'; copias[i].replaceWith(img); }
            catch (e) { copias[i].remove(); }
        });
        c.querySelectorAll('script').forEach(x => x.remove());          // só o conteúdo: nada roda no documento do PDF
        c.querySelectorAll('[contenteditable]').forEach(x => x.removeAttribute('contenteditable'));
        c.querySelectorAll('[id]').forEach(x => x.removeAttribute('id'));
        c.removeAttribute('id');
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
        ['Análise de Ciclo', [q('#card-justificativa')]],         // título só no PDF, em cima das justificativas
    ];
    secoes.forEach(([nome, els]) => {
        const copias = els.map(clona).filter(Boolean);
        if (!copias.length) return;
        if (nome) {
            const t = document.createElement('div'); t.className = 'exec-secao';
            const h = document.createElement('h2'); h.textContent = nome; t.appendChild(h);
            cont.appendChild(t);
        }
        copias.forEach(c => { c.classList.add('exec-item'); cont.appendChild(c); });
    });
    // PDF gerado direto (arquivo .pdf baixado, sem a janela de impressão); sem as bibliotecas, cai na impressão
    obterLibsPdf(libs).then(l => (l ? gerarPdfDireto(cont, l, `Executivo_${sup}_${nomeMes}`) : Promise.reject(new Error('sem bibliotecas'))))
        .catch(erro => { console.warn('PDF direto indisponível, usando a impressão:', erro); imprimirDocumentoLeve(cont); });
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
    fr.style.cssText = 'position:fixed; left:0; top:0; width:1062px; height:800px; border:0; opacity:0; pointer-events:none; z-index:-1;';
    document.body.appendChild(fr);
    try {
        const doc = fr.contentDocument;
        doc.open(); doc.write(montaDocumentoExecutivo(cont, true)); doc.close();
        const imgs = Array.from(doc.images);
        await Promise.race([Promise.all([...imgs.map(i => i.complete ? null : new Promise(r => { i.onload = i.onerror = r; })),
            doc.fonts && doc.fonts.ready ? doc.fonts.ready.catch(() => null) : null]), new Promise(r => setTimeout(r, 4000))]);
        // tabela mais larga que a folha (ex.: orçado por ciclo com Abs e %): alarga o documento para caber inteira;
        // a imagem depois é reduzida para a largura da página
        let largura = 1062;
        doc.querySelectorAll('#view-executivo table').forEach(t => { largura = Math.max(largura, Math.ceil(t.scrollWidth) + 48); });
        if (largura > 1062) { fr.style.width = largura + 'px'; await new Promise(r => setTimeout(r, 50)); }
        await Promise.race([injetaLibs(doc, libs), new Promise((_, r) => setTimeout(() => r(new Error('bibliotecas do PDF demoraram')), 15000))]);
        const w = fr.contentWindow;
        if (!w.jspdf || !w.html2canvas) throw new Error('bibliotecas do PDF indisponíveis');
        const pdf = new w.jspdf.jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4', compress: true });
        const W = 297, H = 210, M = 8, LW = W - 2 * M, LH = H - 2 * M - 6;       // 6 mm do rodapé
        let y = M, primeira = true;
        const novaPagina = () => { pdf.addPage(); y = M; };
        const raiz = doc.getElementById('view-executivo') || doc.body.firstElementChild;
        // uma única "foto" do Executivo inteiro (rápido); depois cada quadro é recortado dela pela posição na tela
        const ESC = 2;
        const foto = await w.html2canvas(raiz, { scale: ESC, backgroundColor: '#FFFFFF', logging: false, imageTimeout: 3000,
            windowWidth: largura, width: raiz.scrollWidth, height: raiz.scrollHeight });
        const r0 = raiz.getBoundingClientRect();
        const recorte = (topoPx, altPx) => {
            const c = document.createElement('canvas'); c.width = foto.width; c.height = Math.max(1, Math.round(altPx));
            c.getContext('2d').drawImage(foto, 0, Math.round(topoPx), foto.width, c.height, 0, 0, foto.width, c.height);
            return c.toDataURL('image/jpeg', 0.92);
        };
        const mmPorPx = LW / foto.width;
        for (const el of Array.from(raiz.children)) {
            const r = el.getBoundingClientRect();
            if (!r.height) continue;
            const topo = (r.top - r0.top) * ESC, altPx = r.height * ESC, alt = altPx * mmPorPx;
            if (el.classList.contains('exec-secao') && !primeira && y > M) novaPagina();
            if (alt <= LH) {
                if (y + alt > M + LH) novaPagina();
                pdf.addImage(recorte(topo, altPx), 'JPEG', M, y, LW, alt);
                y += alt + 3;
            } else {                                                  // quadro mais alto que a página: fatias de uma página
                if (y > M) novaPagina();
                const fatiaPx = Math.floor(LH / mmPorPx);
                for (let d = 0; d < altPx; d += fatiaPx) {
                    const h = Math.min(fatiaPx, altPx - d);
                    if (d > 0) novaPagina();
                    pdf.addImage(recorte(topo + d, h), 'JPEG', M, y, LW, h * mmPorPx);
                    y += h * mmPorPx + 3;
                }
            }
            primeira = false;
        }
        const total = pdf.getNumberOfPages();
        for (let i = 1; i <= total; i++) {                            // rodapé: página X de N
            pdf.setPage(i); pdf.setFontSize(8); pdf.setTextColor(73, 102, 140);
            pdf.text(`Águas do Rio · Relatório Executivo · página ${i} de ${total}`, W - M, H - 5, { align: 'right' });
        }
        // baixa pelo documento do relatório (o iframe do PDF é removido logo depois; um clique dentro dele cancelaria o download)
        const blob = pdf.output('blob');
        const url = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
        const a = document.createElement('a');
        a.href = url; a.download = String(nome).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Za-z0-9_-]+/g, '_') + '.pdf';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    } finally {
        fr.remove(); aviso.remove();
    }
}

// Imprime só o conteúdo do Executivo num documento à parte (iframe escondido), com os estilos do relatório.
// Imprimir o relatório inteiro (vários MB com as bases embutidas) fazia a visualização de impressão falhar e o PDF
// salvo sair corrompido ("Não é possível abrir este arquivo").
function montaDocumentoExecutivo(cont, telaComoImpressao) {
    let estilos = Array.from(document.querySelectorAll('style')).map(s => s.textContent).join('\n');
    // PDF direto: o documento é desenhado na tela, então as regras de impressão do Executivo passam a valer na tela também
    if (telaComoImpressao) estilos = estilos.replace(/@media\s+print/g, '@media all') +
        '\n#view-executivo .card, #view-executivo .tabela-wrap { overflow: visible !important; }';   // nada cortado na foto
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
