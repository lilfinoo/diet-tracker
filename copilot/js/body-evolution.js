const bodyMetrics = {
    weight: ['Peso', 'kg'], body_fat: ['Gordura', '%'], waist: ['Cintura', 'cm'],
    chest: ['Peito', 'cm'], arm: ['Braço', 'cm'], thigh: ['Coxa', 'cm'],
    muscle_mass: ['Massa muscular', 'kg'],
};

function bodyDay(date) {
    return Date.parse(`${date}T00:00:00Z`) / 86400000;
}

function bodyNumber(value) {
    return value.toLocaleString('pt-BR', { maximumFractionDigits: 1 });
}

function bodyChart(points, label, unit) {
    const firstDay = bodyDay(points[0].date);
    const lastDay = bodyDay(points.at(-1).date);
    const values = points.map(point => point.value);
    const min = Math.min(...values), max = Math.max(...values);
    const padding = Math.max((max - min) * 0.15, 0.5);
    const low = min - padding, high = max + padding;
    const x = point => lastDay === firstDay ? 180 : 52 + (bodyDay(point.date) - firstDay) / (lastDay - firstDay) * 266;
    const y = point => 166 - (point.value - low) / (high - low) * 136;
    const coordinates = points.map(point => `${x(point)},${y(point)}`).join(' ');
    return `<svg class="body-chart" viewBox="0 0 340 210" role="img" aria-labelledby="bodyChartTitle bodyChartDesc">
        <title id="bodyChartTitle">${label} ao longo do tempo (${unit})</title>
        <desc id="bodyChartDesc">${points.length} registros. Distância horizontal proporcional ao intervalo entre datas. Valores detalhados abaixo.</desc>
        ${[min, max].filter((value, i, all) => all.indexOf(value) === i).map(value => `<line x1="52" x2="318" y1="${y({value})}" y2="${y({value})}" class="body-chart-grid"/><text x="46" y="${y({value}) + 4}" text-anchor="end">${bodyNumber(value)}</text>`).join('')}
        ${points.length > 1 ? `<polyline points="${coordinates}" fill="none" class="body-chart-line"/>` : ''}
        ${points.map(point => `<circle cx="${x(point)}" cy="${y(point)}" r="4" class="body-chart-point"><title>${formatDate(point.date)}: ${bodyNumber(point.value)} ${unit}</title></circle>`).join('')}
        <text x="52" y="198">${formatDate(points[0].date)}</text>
        ${lastDay !== firstDay ? `<text x="318" y="198" text-anchor="end">${formatDate(points.at(-1).date)}</text>` : ''}
    </svg>`;
}

function renderBodyEvolution(data, metric, today = new Date()) {
    const [label, unit] = bodyMetrics[metric];
    const points = (data.points || []).filter(point => typeof point.value === 'number' && Number.isFinite(point.value));
    const localToday = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    const age = data.latest_date ? bodyDay(localToday) - bodyDay(data.latest_date) : 0;
    const stale = age > 30 ? `<p class="body-stale">Último dado de ${label.toLowerCase()}: ${formatDate(data.latest_date)} · há ${age} dias. <button type="button" onclick="showAddMeasurementModal()">Atualizar medição</button></p>` : '';
    if (!points.length) return `<div class="body-empty"><strong>Sem registros de ${label.toLowerCase()} neste período</strong><p>Preencha esta métrica em uma medição para começar.</p><button type="button" onclick="showAddMeasurementModal()">Nova medição</button><button type="button" onclick="clearMeasurementFilters()">Ver todo o histórico</button></div>${stale}`;
    const first = points[0], last = points.at(-1);
    const change = Math.round((last.value - first.value) * 10) / 10;
    const changeUnit = metric === 'body_fat' ? 'p.p.' : unit;
    const variation = points.length < 2 ? '—' : `${change > 0 ? '+' : change < 0 ? '−' : ''}${bodyNumber(Math.abs(change))} ${changeUnit}`;
    const explanation = points.length === 1 ? 'Ponto inicial. Adicione outra medição para comparar.' : points.length === 2 ? 'Comparação entre dois registros; ainda não indica uma tendência consolidada.' : `${points.length} registros no período. A linha conecta os valores registrados, sem estimar dados ausentes.`;
    return `<h3 class="body-title">${label}</h3><div class="body-values">
        <div><small>Inicial</small><strong>${bodyNumber(first.value)} ${unit}</strong><time datetime="${first.date}">${formatDate(first.date)}</time></div>
        <span aria-hidden="true">→</span><div><small>Atual no período</small><strong>${bodyNumber(last.value)} ${unit}</strong><time datetime="${last.date}">${formatDate(last.date)}</time></div>
        <span aria-hidden="true">→</span><div><small>Variação</small><strong>${variation}</strong>${points.length > 1 && change === 0 ? '<small>Sem alteração</small>' : ''}</div>
        </div>${bodyChart(points, label, unit)}<p class="body-explanation">${explanation}${metric === 'body_fat' && points.length > 1 ? ' Variação em pontos percentuais.' : ''}</p>${stale}
        <details class="body-values-detail"><summary>Ver valores do gráfico</summary><table><caption>${label} · ${unit}</caption><thead><tr><th scope="col">Data</th><th scope="col">Valor</th></tr></thead><tbody>${points.map(point => `<tr><td>${formatDate(point.date)}</td><td>${bodyNumber(point.value)} ${unit}</td></tr>`).join('')}</tbody></table></details>`;
}

function setBodyPeriod(period) {
    getElement('bodyPeriod').value = period;
    const disclosure = getElement('bodyDateFilters');
    if (period === 'custom') {
        disclosure.open = true;
        getElement('measurementStartDate').focus();
        return;
    }
    const localDate = date => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    const end = new Date(), start = new Date(end);
    if (period !== 'all') start.setDate(start.getDate() - Number(period) + 1);
    getElement('measurementStartDate').value = period === 'all' ? '' : localDate(start);
    getElement('measurementEndDate').value = period === 'all' ? '' : localDate(end);
    disclosure.open = false;
    loadMeasurements();
    loadMeasurementSummary();
}

function changeBodyDates() {
    getElement('bodyPeriod').value = 'custom';
    loadMeasurements();
    loadMeasurementSummary();
}
