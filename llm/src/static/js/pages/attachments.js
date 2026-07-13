// ===== STATE =====
let allFiles = [];
let activeFilter = 'all';
let searchQuery = '';

// ===== INIT =====
async function initAttachmentsPage() {
    try {
        allFiles = await apiGet('/api/v1/files/');
    } catch (e) {
        console.error('Failed to load attachments:', e);
        allFiles = [];
    }
    setupSearch();
    setupFilters();
    renderGrid();

    // Bind ?file=<uuid> to the detail modal.
    registerModalUrl({
        key: 'file',
        idType: 'uuid',
        onOpen: (id) => {
            if (allFiles.some(f => f.id === id)) {
                openFileDetail(id);
            }
        },
        onClose: closeFileDetail,
    });
}

// ===== SEARCH =====
function setupSearch() {
    document.getElementById('searchInput').addEventListener('input', onSearch);
}

function onSearch() {
    searchQuery = document.getElementById('searchInput').value.toLowerCase().trim();
    renderGrid();
}

// ===== FILTERS =====
function setupFilters() {
    // onclick handlers are inline in HTML
}

function setFilter(filter) {
    activeFilter = filter;
    document.querySelectorAll('.filter-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === filter);
    });
    renderGrid();
}

// ===== RENDER GRID =====
function renderGrid() {
    const grid = document.getElementById('attachmentsGrid');
    const emptyState = document.getElementById('emptyState');
    const statsBar = document.getElementById('statsBar');

    const filtered = filterFiles();

    // Stats
    const total = allFiles.length;
    const images = allFiles.filter(f => f.file_type === 'image').length;
    const docs = allFiles.filter(f => f.file_type !== 'image').length;
    statsBar.textContent = `${total} file${total !== 1 ? 's' : ''} total · ${images} image${images !== 1 ? 's' : ''} · ${docs} document${docs !== 1 ? 's' : ''}`;

    if (filtered.length === 0) {
        grid.innerHTML = '';
        emptyState.classList.remove('hidden');
        return;
    }
    emptyState.classList.add('hidden');

    grid.innerHTML = filtered.map(f => buildTileHTML(f)).join('');
}

function filterFiles() {
    return allFiles.filter(f => {
        // Type filter
        if (activeFilter === 'image' && f.file_type !== 'image') return false;
        if (activeFilter === 'document' && f.file_type === 'image') return false;

        // Search filter
        if (searchQuery) {
            const haystack = [
                f.original_filename,
                f.student_name,
                f.chat_name,
                f.file_type,
            ].join(' ').toLowerCase();
            if (!haystack.includes(searchQuery)) return false;
        }

        return true;
    });
}

function buildTileHTML(f) {
    const previewHTML = f.file_type === 'image'
        ? `<img src="/api/v1/files/view/${f.id}" alt="${escapeHtml(f.original_filename)}" loading="lazy">`
        : `<div class="tile-doc-icon">${docIcon(f.file_type)}</div>`;

    return `
        <div class="attachment-tile" onclick="openModalUrl('file', '${f.id}')">
            <div class="tile-preview">${previewHTML}</div>
            <div class="tile-footer">
                <div class="tile-name" title="${escapeHtml(f.original_filename)}">${escapeHtml(f.original_filename)}</div>
                <div class="tile-student">${escapeHtml(f.student_name)}</div>
            </div>
        </div>
    `;
}

function docIcon(fileType) {
    if (fileType === 'pdf') return '📄';
    if (fileType === 'docx') return '📝';
    return '📎';
}

// ===== MODAL =====
function openFileDetail(fileId) {
    const f = allFiles.find(x => x.id === fileId);
    if (!f) return;

    // Preview
    const preview = document.getElementById('modalPreview');
    if (f.file_type === 'image') {
        preview.innerHTML = `<img src="/api/v1/files/view/${f.id}" alt="${escapeHtml(f.original_filename)}">`;
    } else {
        preview.innerHTML = `<div class="modal-preview-icon">${docIcon(f.file_type)}</div>`;
    }

    // Info
    const info = document.getElementById('modalInfo');
    info.innerHTML = `
        <div class="modal-info-row">
            <span class="modal-info-label">Filename</span>
            <span class="modal-info-value">${escapeHtml(f.original_filename)}</span>
        </div>
        <div class="modal-info-row">
            <span class="modal-info-label">Type</span>
            <span class="modal-info-value">${escapeHtml(f.file_type)}</span>
        </div>
        <div class="modal-info-row">
            <span class="modal-info-label">Size</span>
            <span class="modal-info-value">${formatFileSize(f.file_size)}</span>
        </div>
        <div class="modal-info-row">
            <span class="modal-info-label">Date</span>
            <span class="modal-info-value">${formatUploadDate(f.uploaded_at)}</span>
        </div>
        <div class="modal-info-row">
            <span class="modal-info-label">Student</span>
            <span class="modal-info-value">${escapeHtml(f.student_name)}</span>
        </div>
        <div class="modal-info-row">
            <span class="modal-info-label">Chat</span>
            <span class="modal-info-value">${escapeHtml(f.chat_name)}</span>
        </div>
    `;

    // Actions
    document.getElementById('modalDownload').href = `/api/v1/files/download/${f.id}`;
    document.getElementById('modalChatLink').href = `/${f.project_id}`;

    document.getElementById('detailModal').classList.remove('hidden');
}

function closeFileDetail() {
    document.getElementById('detailModal').classList.add('hidden');
}

function handleOverlayClick(event) {
    if (event.target === document.getElementById('detailModal')) {
        closeModalUrl('file');
    }
}

// ===== HELPERS =====
function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatUploadDate(isoString) {
    if (!isoString) return '—';
    const d = new Date(isoString);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

// Close modal on Escape
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModalUrl('file');
});

initAttachmentsPage();
