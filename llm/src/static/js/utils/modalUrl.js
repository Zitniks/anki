/**
 * modalUrl — keep one modal per page in sync with a URL query param so the
 * modal becomes shareable, reloadable, and Back-button closable.
 *
 * Pages register their modal types declaratively (no parser callbacks):
 *
 *   registerModalUrl({key, idType, onOpen, onClose})
 *
 * The helper owns all parsing and validation against a fixed `idType`
 * whitelist, so pages never receive an unvetted id from the URL.
 *
 *   - idType 'int'  → /^\d+$/ + Number.isSafeInteger
 *   - idType 'uuid' → canonical 8-4-4-4-12 hex, case-insensitive
 *
 * Open/close from app code go through openModalUrl(key, id) / closeModalUrl(key);
 * those push history state and invoke onOpen/onClose. Back/Forward (popstate)
 * keep URL ↔ modal in sync; malformed values on initial load are silently
 * scrubbed from the URL.
 */
(function () {
    'use strict';

    const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const INT_RE = /^\d+$/;

    // key -> { idType, onOpen, onClose, currentId }
    const registry = new Map();
    let suppressWrite = false;

    function parseRaw(raw, idType) {
        if (typeof raw !== 'string') return null;
        if (idType === 'int') {
            if (!INT_RE.test(raw)) return null;
            const n = Number(raw);
            return Number.isSafeInteger(n) ? n : null;
        }
        if (idType === 'uuid') {
            return UUID_RE.test(raw) ? raw : null;
        }
        return null;
    }

    function writeUrl(mutator) {
        const url = new URL(window.location.href);
        mutator(url.searchParams);
        const next = url.pathname + (url.search ? url.search : '') + url.hash;
        history.pushState(null, '', next);
    }

    function replaceUrl(mutator) {
        const url = new URL(window.location.href);
        mutator(url.searchParams);
        const next = url.pathname + (url.search ? url.search : '') + url.hash;
        history.replaceState(null, '', next);
    }

    function syncFromUrl(initial) {
        const params = new URLSearchParams(window.location.search);
        // Track keys whose raw URL value is malformed so we can scrub them
        // on initial load via replaceState (no history pollution).
        const toScrub = [];

        for (const [key, entry] of registry) {
            const raw = params.get(key);
            if (raw === null) {
                if (entry.currentId !== null) {
                    entry.currentId = null;
                    try { entry.onClose(); } catch (e) { console.error(e); }
                }
                continue;
            }

            const parsed = parseRaw(raw, entry.idType);
            if (parsed === null) {
                toScrub.push(key);
                continue;
            }

            // Stringified comparison so 12 vs "12" don't re-fire.
            if (String(entry.currentId) === String(parsed)) continue;

            entry.currentId = parsed;
            try { entry.onOpen(parsed); } catch (e) { console.error(e); }
        }

        if (initial && toScrub.length) {
            replaceUrl(p => toScrub.forEach(k => p.delete(k)));
        }
    }

    window.registerModalUrl = function registerModalUrl({key, idType, onOpen, onClose}) {
        if (!key || (idType !== 'int' && idType !== 'uuid')) {
            throw new Error(`modalUrl: invalid registration for key=${key}`);
        }
        registry.set(key, {
            idType,
            onOpen: typeof onOpen === 'function' ? onOpen : () => {},
            onClose: typeof onClose === 'function' ? onClose : () => {},
            currentId: null,
        });
        // Run an initial sweep so a page that registers after data loads
        // immediately opens any modal pointed at by the URL.
        syncFromUrl(true);
    };

    window.openModalUrl = function openModalUrl(key, id) {
        const entry = registry.get(key);
        if (!entry) {
            console.warn(`modalUrl: openModalUrl called for unregistered key=${key}`);
            return;
        }
        // Validate the id we're about to put into the URL by re-parsing its
        // string form — keeps the URL guaranteed-clean even from JS callers.
        const parsed = parseRaw(String(id), entry.idType);
        if (parsed === null) {
            console.warn(`modalUrl: rejected id=${id} for key=${key} (idType=${entry.idType})`);
            return;
        }
        entry.currentId = parsed;
        writeUrl(p => p.set(key, String(parsed)));
        suppressWrite = true;
        try { entry.onOpen(parsed); } finally { suppressWrite = false; }
    };

    window.closeModalUrl = function closeModalUrl(key) {
        const entry = registry.get(key);
        if (!entry) return;
        if (entry.currentId === null) return;
        entry.currentId = null;
        writeUrl(p => p.delete(key));
        suppressWrite = true;
        try { entry.onClose(); } finally { suppressWrite = false; }
    };

    window.addEventListener('popstate', () => {
        if (suppressWrite) return;
        syncFromUrl(false);
    });
})();
