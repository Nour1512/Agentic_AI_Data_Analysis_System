/**
 * reports.js — Report history page module.
 *
 * Handles rendering the Reports view: loading the report list,
 * displaying status badges, dates, and download actions.
 */

(function () {
    'use strict';

    // -----------------------------------------------------------------------
    // Status badge configuration
    // -----------------------------------------------------------------------
    const STATUS_CONFIG = {
        completed: { label: 'Completed', cssClass: 'badge-success' },
        failed:    { label: 'Failed',    cssClass: 'badge-danger'  },
        processing:{ label: 'Processing',cssClass: 'badge-warning' },
    };

    function getStatusBadge(status) {
        const cfg = STATUS_CONFIG[status] || { label: status, cssClass: 'badge-default' };
        return `<span class="status-badge ${cfg.cssClass}">${cfg.label}</span>`;
    }

    // -----------------------------------------------------------------------
    // Date formatting
    // -----------------------------------------------------------------------
    function formatDate(isoString) {
        if (!isoString) return '—';
        try {
            const d = new Date(isoString);
            return d.toLocaleString(undefined, {
                year: 'numeric', month: 'short', day: 'numeric',
                hour: '2-digit', minute: '2-digit',
            });
        } catch {
            return isoString;
        }
    }

    // -----------------------------------------------------------------------
    // Render a single report card
    // -----------------------------------------------------------------------
    function renderReportCard(report) {
        const badge = getStatusBadge(report.status);
        const date = formatDate(report.created_at);
        const preview = report.summary_preview
            ? `<p class="report-history-preview">${escapeHtml(report.summary_preview)}</p>`
            : '';
        const questionText = escapeHtml(report.question || '—');

        const downloadBtn = report.report_available && report.download_url
            ? `<button
                class="secondary-btn btn-sm download-history-btn"
                data-request-id="${escapeHtml(report.request_id)}"
                data-fallback-name="${escapeHtml(report.question.slice(0, 40) || 'report')}.docx"
                title="Download .docx report">
                ↓ Download
               </button>`
            : `<button class="secondary-btn btn-sm" disabled title="No report file available">
                No Report
               </button>`;

        return `
        <div class="report-history-card" data-request-id="${escapeHtml(report.request_id)}">
            <div class="report-history-main">
                <div class="report-history-question">${questionText}</div>
                ${preview}
                <div class="report-history-meta">
                    ${badge}
                    <span class="report-history-date">◷ ${date}</span>
                    <span class="report-history-id" title="Request ID">${report.request_id.slice(0, 8)}…</span>
                </div>
            </div>
            <div class="report-history-actions">
                ${downloadBtn}
            </div>
        </div>
        `;
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // -----------------------------------------------------------------------
    // Loading state
    // -----------------------------------------------------------------------
    function showReportsLoading(container) {
        container.innerHTML = `
            <div class="reports-state-panel">
                <div class="reports-spinner"></div>
                <p>Loading report history…</p>
            </div>
        `;
    }

    // -----------------------------------------------------------------------
    // Empty state
    // -----------------------------------------------------------------------
    function showReportsEmpty(container) {
        container.innerHTML = `
            <div class="reports-state-panel reports-empty">
                <div class="reports-empty-icon">📋</div>
                <h3>No reports yet</h3>
                <p>Submit an analysis request and your generated reports will appear here.</p>
            </div>
        `;
    }

    // -----------------------------------------------------------------------
    // Error state
    // -----------------------------------------------------------------------
    function showReportsError(container, message) {
        container.innerHTML = `
            <div class="reports-state-panel reports-error">
                <div class="reports-empty-icon">⚠</div>
                <h3>Failed to load reports</h3>
                <p>${escapeHtml(message)}</p>
                <button class="secondary-btn" id="retryLoadReports">Retry</button>
            </div>
        `;
        const retryBtn = container.querySelector('#retryLoadReports');
        if (retryBtn) retryBtn.addEventListener('click', () => loadReports(container));
    }

    // -----------------------------------------------------------------------
    // Main load function
    // -----------------------------------------------------------------------
    async function loadReports(container) {
        showReportsLoading(container);

        try {
            const { reports, total } = await window.AnalyticsAPI.getReports({ limit: 50, offset: 0 });

            if (!reports || reports.length === 0) {
                showReportsEmpty(container);
                return;
            }

            // Header with total count
            let html = `
                <div class="reports-history-header">
                    <h3>Report History</h3>
                    <span class="reports-total-badge">${total} total</span>
                </div>
                <div class="reports-history-list">
            `;

            reports.forEach(report => {
                html += renderReportCard(report);
            });

            html += '</div>';
            container.innerHTML = html;

            // Attach download handlers
            container.querySelectorAll('.download-history-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const requestId = btn.dataset.requestId;
                    const fallbackName = btn.dataset.fallbackName || 'report.docx';

                    btn.disabled = true;
                    btn.textContent = 'Downloading…';

                    try {
                        await window.AnalyticsAPI.downloadReport(requestId, fallbackName);
                        btn.textContent = '↓ Download';
                    } catch (err) {
                        console.error('Download failed:', err);
                        btn.textContent = 'Error';
                        setTimeout(() => {
                            btn.textContent = '↓ Download';
                            btn.disabled = false;
                        }, 2000);
                        return;
                    }

                    btn.disabled = false;
                });
            });

        } catch (err) {
            console.error('Failed to load reports:', err);
            showReportsError(container, err.message || 'Unknown error');
        }
    }

    // -----------------------------------------------------------------------
    // Public interface
    // -----------------------------------------------------------------------
    window.ReportsPage = { loadReports };

})();
