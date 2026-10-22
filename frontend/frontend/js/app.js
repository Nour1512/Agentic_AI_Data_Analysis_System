/**
 * app.js — Main application controller for the Agentic AI Analytics workspace.
 *
 * Coordinates:
 *  - Navigation between Analysis and Reports views
 *  - Analysis request submission via AnalyticsAPI.analyzeRequest()
 *  - Result rendering (summary, KPIs, charts, insights, report panel)
 *  - Report download via AnalyticsAPI.downloadReport()
 *  - Report modal (HTML preview + DOCX download)
 */

document.addEventListener('DOMContentLoaded', () => {

    // -----------------------------------------------------------------------
    // Element references — Analysis view
    // -----------------------------------------------------------------------
    const analyzeBtn       = document.getElementById('analyzeBtn');
    const queryInput       = document.getElementById('queryInput');
    const loadingState     = document.getElementById('loadingState');
    const errorState       = document.getElementById('errorState');
    const resultsContainer = document.getElementById('resultsContainer');
    const errorMessage     = document.getElementById('errorMessage');
    const retryBtn         = document.getElementById('retryBtn');

    // Result sub-elements
    const analysisSummaryText = document.getElementById('analysisSummaryText');
    const kpiContainer        = document.getElementById('kpiContainer');
    const insightsContainer   = document.getElementById('insightsContainer');
    const chartsContainer     = document.getElementById('chartsContainer');
    const downloadReportBtn   = document.getElementById('downloadReportBtn');
    const previewReportBtn    = document.getElementById('previewReportBtn');
    const reportMetaText      = document.getElementById('reportMetaText');
    const reportPreviewContent= document.getElementById('reportPreviewContent');
    const modalDownloadBtn    = document.getElementById('modalDownloadBtn');
    const dataHead            = document.getElementById('dataHead');
    const dataBody            = document.getElementById('dataBody');
    const dataRowCount        = document.getElementById('dataRowCount');

    // Section wrappers (hidden when no data)
    const kpiSection      = document.getElementById('kpiSection');
    const chartsSection   = document.getElementById('chartsSection');
    const insightsSection = document.getElementById('insightsSection');
    const reportSection   = document.getElementById('reportSection');
    const dataSection     = document.getElementById('dataSection');

    // Views
    const analysisView = document.getElementById('analysis-view');
    const reportsView  = document.getElementById('reports-view');

    // Reports view container
    const reportsListContainer = document.getElementById('reportsListContainer');

    // Modal
    const reportModal    = document.getElementById('reportModal');
    const closeModalBtn  = document.getElementById('closeModalBtn');

    // Nav items
    const navItems = document.querySelectorAll('.nav-item');

    // Tracks the last successful request_id for downloads
    let currentRequestId = null;

    // -----------------------------------------------------------------------
    // Navigation
    // -----------------------------------------------------------------------
    function showView(viewName) {
        // Hide all views
        if (analysisView) analysisView.classList.add('hidden');
        if (reportsView)  reportsView.classList.add('hidden');

        // Update nav active state
        navItems.forEach(n => n.classList.remove('active'));

        if (viewName === 'reports') {
            if (reportsView) reportsView.classList.remove('hidden');
            navItems.forEach(n => {
                if (n.dataset.view === 'reports') n.classList.add('active');
            });
            // Load reports when the view becomes visible
            if (reportsListContainer && window.ReportsPage) {
                window.ReportsPage.loadReports(reportsListContainer);
            }
        } else {
            // Default: analysis
            if (analysisView) analysisView.classList.remove('hidden');
            navItems.forEach(n => {
                if (n.dataset.view === 'analyze') n.classList.add('active');
            });
        }
    }

    navItems.forEach(item => {
        item.addEventListener('click', e => {
            e.preventDefault();
            showView(item.dataset.view || 'analyze');
        });
    });

    // -----------------------------------------------------------------------
    // Suggestion chips
    // -----------------------------------------------------------------------
    document.querySelectorAll('.suggestion-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            queryInput.value = chip.dataset.query || chip.textContent.trim();
            queryInput.focus();
        });
    });

    // -----------------------------------------------------------------------
    // Keyboard shortcut: Enter to submit
    // -----------------------------------------------------------------------
    queryInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            analyzeBtn.click();
        }
    });

    retryBtn.addEventListener('click', () => analyzeBtn.click());

    // -----------------------------------------------------------------------
    // Collapsible data panel
    // -----------------------------------------------------------------------
    const dataPanelToggle = document.querySelector('.data-panel .toggle-collapse');
    if (dataPanelToggle) {
        dataPanelToggle.addEventListener('click', () => {
            const panel = dataPanelToggle.closest('.collapsible');
            panel.classList.toggle('open');
            panel.querySelector('.panel-content').classList.toggle('hidden');
        });
    }

    // -----------------------------------------------------------------------
    // Table search
    // -----------------------------------------------------------------------
    const tableSearch = document.querySelector('.table-search');
    if (tableSearch) {
        tableSearch.addEventListener('input', () => {
            const q = tableSearch.value.toLowerCase();
            document.querySelectorAll('#dataBody tr').forEach(row => {
                row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
            });
        });
    }

    // -----------------------------------------------------------------------
    // Modal handlers
    // -----------------------------------------------------------------------
    if (previewReportBtn) {
        previewReportBtn.addEventListener('click', () => {
            reportModal.classList.remove('hidden');
        });
    }
    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', () => {
            reportModal.classList.add('hidden');
        });
    }
    if (reportModal) {
        reportModal.addEventListener('click', e => {
            if (e.target === reportModal) reportModal.classList.add('hidden');
        });
    }

    // -----------------------------------------------------------------------
    // Download report button handler (main panel)
    // -----------------------------------------------------------------------
    if (downloadReportBtn) {
        downloadReportBtn.addEventListener('click', async e => {
            e.preventDefault();
            if (!currentRequestId) return;

            downloadReportBtn.disabled = true;
            downloadReportBtn.textContent = 'Downloading…';

            try {
                const question = queryInput.value.trim().slice(0, 40) || 'report';
                await window.AnalyticsAPI.downloadReport(currentRequestId, `${question}.docx`);
            } catch (err) {
                console.error('Report download failed:', err);
                alert(`Download failed: ${err.message}`);
            } finally {
                downloadReportBtn.disabled = false;
                downloadReportBtn.textContent = '⬇ Download Report';
            }
        });
    }

    // Modal download button handler
    if (modalDownloadBtn) {
        modalDownloadBtn.addEventListener('click', async e => {
            e.preventDefault();
            if (!currentRequestId) return;
            try {
                const question = queryInput.value.trim().slice(0, 40) || 'report';
                await window.AnalyticsAPI.downloadReport(currentRequestId, `${question}.docx`);
            } catch (err) {
                console.error('Modal download failed:', err);
                alert(`Download failed: ${err.message}`);
            }
        });
    }

    // -----------------------------------------------------------------------
    // Execute Analysis
    // -----------------------------------------------------------------------
    analyzeBtn.addEventListener('click', async () => {
        const query = queryInput.value.trim();
        if (!query) return;

        // Reset UI
        analyzeBtn.disabled = true;
        analyzeBtn.textContent = 'Analyzing…';
        currentRequestId = null;

        errorState.classList.add('hidden');
        resultsContainer.classList.add('hidden');
        loadingState.classList.remove('hidden');

        // Hide all sections initially (rendered only if data arrives)
        hideSection(kpiSection);
        hideSection(chartsSection);
        hideSection(insightsSection);
        hideSection(reportSection);
        hideSection(dataSection);

        try {
            const data = await window.AnalyticsAPI.analyzeRequest(query);

            // Developer debug (uncomment to enable)
            const debugContent = document.getElementById('debugContent');
            if (debugContent) debugContent.textContent = JSON.stringify(data, null, 2);

            if (data && data.success !== false) {
                currentRequestId = data.request_id || null;
                renderWorkspace(data);
                loadingState.classList.add('hidden');
                resultsContainer.classList.remove('hidden');
            } else {
                const errMsg = (data && (data.error || data.detail)) || 'Analysis failed on the server.';
                throw new Error(errMsg);
            }

        } catch (error) {
            console.error('Analysis error:', error);
            loadingState.classList.add('hidden');
            errorState.classList.remove('hidden');
            errorMessage.textContent = error.message || 'An unexpected error occurred.';
        } finally {
            analyzeBtn.disabled = false;
            analyzeBtn.textContent = 'Analyze →';
        }
    });

    // -----------------------------------------------------------------------
    // Section visibility helpers
    // -----------------------------------------------------------------------
    function showSection(el) { if (el) el.classList.remove('hidden'); }
    function hideSection(el) { if (el) el.classList.add('hidden'); }

    // -----------------------------------------------------------------------
    // Main render function
    // -----------------------------------------------------------------------
    function renderWorkspace(data) {

        // 1. Summary
        const summary =
            (data.analysis && data.analysis.summary) ||
            (data.dashboard && data.dashboard.description) ||
            null;

        if (summary && analysisSummaryText) {
            analysisSummaryText.textContent = summary;
        } else if (analysisSummaryText) {
            analysisSummaryText.textContent =
                'The analysis pipeline completed successfully.';
        }

        // 2. KPIs
        const kpis = (data.dashboard && data.dashboard.kpis) || [];
        if (kpiContainer) {
            kpiContainer.innerHTML = '';
            if (kpis.length > 0) {
                kpis.forEach(kpi => {
                    const deltaHtml = kpi.delta
                        ? `<div class="kpi-delta ${kpi.delta_color === 'inverse' ? 'kpi-delta-down' : ''}">${kpi.delta}</div>`
                        : '';
                    kpiContainer.insertAdjacentHTML('beforeend', `
                        <div class="kpi-card">
                            <div class="kpi-label">${escapeHtml(kpi.label)}</div>
                            <div class="kpi-value">${escapeHtml(String(kpi.value))}</div>
                            ${deltaHtml}
                        </div>
                    `);
                });
                showSection(kpiSection);
            } else {
                hideSection(kpiSection);
            }
        }

        // 3. Charts
        const charts = (data.dashboard && data.dashboard.charts) || [];
        if (charts.length > 0 && window.renderDashboardCharts) {
            window.renderDashboardCharts(charts);
            showSection(chartsSection);
        } else {
            if (chartsContainer) chartsContainer.innerHTML = '';
            hideSection(chartsSection);
        }

        // 4. Insights / Key Findings
        // The backend normalizes key_findings into "insights" on the final response.
        // Fall back to analysis.key_findings if insights is missing.
        const insights =
            data.insights ||
            (data.analysis && data.analysis.key_findings) ||
            [];

        if (insightsContainer) {
            insightsContainer.innerHTML = '';
            if (insights.length > 0) {
                insights.forEach(insight => {
                    const item = typeof insight === 'string'
                        ? { title: insight, description: '', metric: null }
                        : insight;

                    const metricHtml = item.metric
                        ? `<div class="insight-metric">${escapeHtml(String(item.metric))}</div>`
                        : '';
                    const importanceDot = item.importance === 'high'
                        ? '<span class="importance-dot importance-high"></span>'
                        : item.importance === 'low'
                            ? '<span class="importance-dot importance-low"></span>'
                            : '<span class="importance-dot importance-medium"></span>';

                    insightsContainer.insertAdjacentHTML('beforeend', `
                        <div class="insight-card">
                            <div class="insight-title">${importanceDot}${escapeHtml(item.title || '')}</div>
                            ${metricHtml}
                            <div class="insight-desc">${escapeHtml(item.description || '')}</div>
                        </div>
                    `);
                });
                showSection(insightsSection);
            } else {
                // Check recommendations as a fallback
                const recs = (data.analysis && data.analysis.recommendations) || [];
                if (recs.length > 0) {
                    recs.forEach(rec => {
                        insightsContainer.insertAdjacentHTML('beforeend', `
                            <div class="insight-card">
                                <div class="insight-title">Recommendation</div>
                                <div class="insight-desc">${escapeHtml(typeof rec === 'string' ? rec : JSON.stringify(rec))}</div>
                            </div>
                        `);
                    });
                    showSection(insightsSection);
                } else {
                    hideSection(insightsSection);
                }
            }
        }

        // 5. Report panel
        const reportData = data.report || {};
        const hasReport = reportData.available === true ||
                          (reportData.success && reportData.report_path);

        if (reportSection) {
            if (hasReport && currentRequestId) {
                if (reportMetaText) reportMetaText.textContent = 'Report generated successfully';

                // Show download + preview buttons
                if (downloadReportBtn) {
                    downloadReportBtn.classList.remove('hidden');
                    downloadReportBtn.style.display = '';
                }
                if (previewReportBtn) {
                    previewReportBtn.classList.remove('hidden');
                    previewReportBtn.style.display = '';
                }

                // Populate the HTML preview
                if (reportPreviewContent) {
                    if (reportData.report_html) {
                        reportPreviewContent.innerHTML = reportData.report_html;
                    } else {
                        reportPreviewContent.innerHTML =
                            '<p>Report preview not available. Please download the document.</p>';
                    }
                }

                showSection(reportSection);

            } else {
                // Analysis succeeded but no report was generated
                if (reportMetaText) {
                    const errors = data.errors || [];
                    const reportError = errors.find(e =>
                        typeof e === 'string' && e.toLowerCase().includes('report')
                    );
                    reportMetaText.textContent = reportError
                        ? `⚠ ${reportError}`
                        : 'Report generation was not requested or failed.';
                }
                if (downloadReportBtn) downloadReportBtn.style.display = 'none';
                if (previewReportBtn)  previewReportBtn.style.display = 'none';
                showSection(reportSection);
            }
        }

        // 6. Data Table
        const tableData = (data.dashboard && data.dashboard.data_table) || [];
        if (dataSection && dataHead && dataBody) {
            dataHead.innerHTML = '';
            dataBody.innerHTML = '';

            if (tableData.length > 0) {
                if (dataRowCount) dataRowCount.textContent = tableData.length.toLocaleString();

                const sampleData = tableData.slice(0, 100);
                const columns = Object.keys(sampleData[0]);

                let headHtml = '<tr>';
                columns.forEach(col => { headHtml += `<th>${escapeHtml(col)}</th>`; });
                headHtml += '</tr>';
                dataHead.innerHTML = headHtml;

                let bodyHtml = '';
                sampleData.forEach(row => {
                    bodyHtml += '<tr>';
                    columns.forEach(col => {
                        const val = row[col] !== null && row[col] !== undefined ? row[col] : '';
                        bodyHtml += `<td>${escapeHtml(String(val))}</td>`;
                    });
                    bodyHtml += '</tr>';
                });
                dataBody.innerHTML = bodyHtml;
                showSection(dataSection);

            } else {
                if (dataRowCount) dataRowCount.textContent = '0';
                hideSection(dataSection);
            }
        }

        // Show any pipeline warnings/errors as a toast
        const pipelineErrors = data.errors || [];
        if (pipelineErrors.length > 0) {
            showWarningToast(pipelineErrors.join(' · '));
        }
    }

    // -----------------------------------------------------------------------
    // Toast notification for pipeline warnings
    // -----------------------------------------------------------------------
    function showWarningToast(message) {
        let toast = document.getElementById('pipeline-warning-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'pipeline-warning-toast';
            toast.className = 'pipeline-warning-toast';
            document.body.appendChild(toast);
        }
        toast.textContent = `⚠ ${message}`;
        toast.classList.add('toast-visible');
        setTimeout(() => toast.classList.remove('toast-visible'), 6000);
    }

    // -----------------------------------------------------------------------
    // HTML escape utility
    // -----------------------------------------------------------------------
    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // -----------------------------------------------------------------------
    // Initial state — show analysis view
    // -----------------------------------------------------------------------
    showView('analyze');
});
