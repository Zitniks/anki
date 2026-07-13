/**
 * API Utilities
 * Common fetch wrappers and API interaction patterns
 * Auth is handled via HttpOnly cookie — no manual headers needed.
 */

async function apiFetch(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    });

    if (response.status === 401) {
        window.location.href = '/login';
        throw new Error('Unauthorized');
    }

    if (!response.ok) {
        let detail = `${response.status} ${response.statusText}`;
        try { const body = await response.json(); if (body.detail) detail = body.detail; } catch (_) {}
        throw new Error(detail);
    }

    return await response.json();
}

async function apiGet(url) {
    return apiFetch(url, { method: 'GET' });
}

async function apiPost(url, data) {
    return apiFetch(url, {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

async function apiPatch(url, data) {
    return apiFetch(url, {
        method: 'PATCH',
        body: JSON.stringify(data),
    });
}

async function apiDelete(url) {
    return apiFetch(url, { method: 'DELETE' });
}
