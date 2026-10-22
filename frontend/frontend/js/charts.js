/**
 * charts.js — Plotly chart renderer for the Agentic AI Analytics dashboard.
 *
 * Renders charts from the DashboardConfig.charts array (ChartConfig objects)
 * into the #chartsContainer element using Plotly.js.
 *
 * Called by app.js after a successful /api/analyze response.
 */

window.renderDashboardCharts = function(charts) {
    const chartsContainer = document.getElementById('chartsContainer');
    if (!chartsContainer) return;

    chartsContainer.innerHTML = '';

    if (!charts || charts.length === 0) {
        // Visibility of the entire charts section is handled by app.js.
        // We don't render a "no charts" placeholder here.
        return;
    }

    charts.forEach((chart, index) => {
        if (!chart.success && chart.success !== undefined) {
            // Skip charts that the backend explicitly marked as failed
            return;
        }

        const chartId = `plotly-chart-${index}`;

        // Layout rule: 1 chart → full width; odd first chart of 3+ → full width
        const isFullWidth =
            charts.length === 1 ||
            (charts.length === 3 && index === 0) ||
            (charts.length >= 5 && index === 0);
        const widthClass = isFullWidth ? 'full-width' : '';

        const insightHtml = chart.insight
            ? `<div class="chart-insight"><strong>AI Insight:</strong> ${chart.insight}</div>`
            : '';

        const purposeHtml = chart.purpose
            ? `<div class="chart-badge" style="margin-left:8px" title="${chart.purpose}">${chart.chart_type}</div>`
            : `<span class="chart-badge">${chart.chart_type}</span>`;

        const html = `
            <div class="chart-panel ${widthClass}">
                <div class="chart-header">
                    <div>
                        <div class="chart-title">${chart.title || 'Chart'}</div>
                    </div>
                    ${purposeHtml}
                </div>
                <div class="chart-container" id="${chartId}"></div>
                ${insightHtml}
            </div>
        `;
        chartsContainer.insertAdjacentHTML('beforeend', html);

        const chartData = chart.data || [];
        if (chartData.length === 0) return;

        // Semantic axis columns provided by the VisualizationService
        const xCol = chart.x_column;
        const yCol = chart.y_column;

        if (!xCol) return; // Cannot render without at least an X axis

        // Extract data arrays
        const xData = chartData.map(row => row[xCol]).filter(v => v !== undefined && v !== null);
        const yData = yCol
            ? chartData.map(row => row[yCol]).filter(v => v !== undefined && v !== null)
            : [];

        // Base Plotly layout (dark theme)
        const layout = {
            margin: { t: 10, l: 50, r: 20, b: 50 },
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#9BA4B5', family: 'Inter, sans-serif', size: 12 },
            xaxis: {
                gridcolor: 'rgba(255,255,255,0.06)',
                zerolinecolor: 'rgba(255,255,255,0.1)',
                title: { text: chart.x_axis_label || xCol || '', font: { color: '#667085' } },
            },
            yaxis: {
                gridcolor: 'rgba(255,255,255,0.06)',
                zerolinecolor: 'rgba(255,255,255,0.1)',
                title: { text: chart.y_axis_label || yCol || '', font: { color: '#667085' } },
            },
        };

        const palette = [
            '#7C5CFC', '#4F8CFF', '#35D07F', '#F5B942',
            '#FF5C7A', '#388bfd', '#a371f7', '#3fb950',
        ];

        let trace = {};
        
        // Limit data for bar and pie charts to prevent overcrowding
        let plotX = xData;
        let plotY = yData;
        const cType = (chart.chart_type || 'bar').toLowerCase();
        
        if (['bar', 'horizontal_bar', 'pie'].includes(cType) && plotX.length > 30) {
            plotX = plotX.slice(0, 30);
            plotY = plotY.slice(0, 30);
        }

        switch (cType) {
            case 'bar':
                trace = {
                    x: plotX, y: plotY, type: 'bar',
                    marker: { color: '#7C5CFC', opacity: 0.9 },
                };
                break;

            case 'horizontal_bar':
                trace = {
                    x: plotY, y: plotX, type: 'bar', orientation: 'h',
                    marker: { color: '#4F8CFF', opacity: 0.9 },
                };
                // Swap axis labels for horizontal orientation
                layout.xaxis.title.text = chart.y_axis_label || yCol || '';
                layout.yaxis.title.text = chart.x_axis_label || xCol || '';
                break;

            case 'line':
                trace = {
                    x: plotX, y: plotY, type: 'scatter', mode: 'lines+markers',
                    line: { color: '#4F8CFF', width: 2.5 },
                    marker: { size: 6, color: '#4F8CFF' },
                };
                break;

            case 'pie': {
                trace = {
                    labels: plotX, values: plotY, type: 'pie',
                    marker: { colors: palette },
                    hole: 0.4,
                    textinfo: 'percent+label',
                    textfont: { color: '#9BA4B5' },
                };
                delete layout.xaxis;
                delete layout.yaxis;
                break;
            }

            case 'histogram':
                trace = {
                    x: xData, type: 'histogram',
                    marker: { color: '#4F8CFF', opacity: 0.85 },
                };
                break;

            case 'scatter':
                trace = {
                    x: xData, y: yData, type: 'scatter', mode: 'markers',
                    marker: { size: 9, color: '#35D07F', opacity: 0.75 },
                };
                break;

            default:
                trace = {
                    x: xData, y: yData, type: 'bar',
                    marker: { color: '#7C5CFC', opacity: 0.9 },
                };
        }

        Plotly.newPlot(chartId, [trace], layout, {
            responsive: true,
            displayModeBar: false,
        });
    });
};
