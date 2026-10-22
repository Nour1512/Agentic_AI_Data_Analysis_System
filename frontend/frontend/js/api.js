/**
 * api.js — Centralized API client for the Agentic AI Analytics platform.
 *
 * All fetch calls go through this module. Components never call fetch directly.
 */

const BASE_URL = '';  // Empty string = same origin (FastAPI serves both API + frontend)

/**
 * Submits a natural-language analysis request and blocks until the full
 * pipeline (SQL → Analysis → Visualization → Report) completes.
 *
 * @param {string} question  The user's natural-language query.
 * @returns {Promise<object>} The structured analysis result from the server.
 * @throws {Error} On network error, non-200 HTTP response, or server error.
 */
async function analyzeRequest(question) {
    const response = await fetch(`${BASE_URL}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
    });

    if (!response.ok) {
        // Try to extract a meaningful error message from the response body
        let detail = `HTTP ${response.status}`;
        try {
            const errorBody = await response.json();
            detail = errorBody.detail || errorBody.message || JSON.stringify(errorBody);
        } catch {
            try { detail = await response.text(); } catch { /* ignore */ }
        }
        throw new Error(detail);
    }

    const data = await response.json();
    return data;
}


/**
 * Fetches the report history list.
 *
 * @param {object} [params]
 * @param {number} [params.limit=20]   Max items to return.
 * @param {number} [params.offset=0]   Pagination offset.
 * @returns {Promise<{reports: Array, total: number}>}
 * @throws {Error} On network or HTTP error.
 */
async function getReports({ limit = 20, offset = 0 } = {}) {
    const url = `${BASE_URL}/api/reports?limit=${limit}&offset=${offset}`;
    const response = await fetch(url);

    if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
            const errorBody = await response.json();
            detail = errorBody.detail || errorBody.message || JSON.stringify(errorBody);
        } catch { /* ignore */ }
        throw new Error(detail);
    }

    return response.json();
}


/**
 * Downloads the .docx report for a given request_id.
 *
 * Fetches the file as a Blob, then triggers a browser download using a
 * temporary anchor element. The filename comes from the Content-Disposition
 * header when available.
 *
 * @param {string} requestId  The request_id returned by /api/analyze.
 * @param {string} [fallbackName='report.docx']  Filename if header is absent.
 * @returns {Promise<void>}
 * @throws {Error} On network error, 404, 409, or server error.
 */
async function downloadReport(requestId, fallbackName = 'report.docx') {
    const response = await fetch(`${BASE_URL}/api/report/${requestId}/download`);

    if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
            const errorBody = await response.json();
            detail = errorBody.detail || errorBody.message || JSON.stringify(errorBody);
        } catch { /* ignore */ }
        throw new Error(detail);
    }

    // Extract filename from Content-Disposition header if present
    const disposition = response.headers.get('Content-Disposition') || '';
    const filenameMatch = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
    const filename = filenameMatch
        ? filenameMatch[1].replace(/['"]/g, '')
        : fallbackName;

    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);

    // Trigger download via temporary anchor
    const anchor = document.createElement('a');
    anchor.href = blobUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);

    // Release blob URL after a short delay to allow the download to start
    setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
}


// Expose to global scope for use by other scripts (vanilla JS module pattern)
window.AnalyticsAPI = { analyzeRequest, getReports, downloadReport };
