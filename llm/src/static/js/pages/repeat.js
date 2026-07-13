// Repeat Page - Test/Quiz/Survey tracking
// Dependencies: utils/dom.js, utils/api.js, utils/helpers.js, components/sidebar.js

// State
let currentProjectId = null;
let repeatItems = [];
let vocabulary = [];
let currentFilter = 'all'; // 'all', 'todo', 'done'
let collapsedSections = { vocabulary: false };

// Get project ID from URL
const pathParts = window.location.pathname.split('/');
currentProjectId = pathParts[pathParts.length - 1];

//////////////////////////////////////////////////
///////////////////INITIALIZATION/////////////////
//////////////////////////////////////////////////

function initRepeatPage() {
    initSidebar(currentProjectId);
    loadRepeatItems();
    loadProjectData();
    loadVocabulary();
    setupFilterTabs();
}

//////////////////////////////////////////////////
//////////////////// DATA ////////////////////////
//////////////////////////////////////////////////

async function loadRepeatItems() {
    try {
        const data = await apiGet(`/api/v1/repeat-items/${currentProjectId}`);
        repeatItems = data.items;
        renderItems();
        updateSubtitle();
    } catch (error) {
        console.error('Error loading repeat items:', error);
        repeatItems = [];
        renderItems();
    }

    // Bind ?repeat=<int> to the edit modal. The add-mode of the same modal
    // does not participate in URL state.
    registerModalUrl({
        key: 'repeat',
        idType: 'int',
        onOpen: (id) => {
            if (repeatItems.some(i => i.id === id)) {
                openEditModal(id);
            }
        },
        onClose: closeAddModal,
    });
}

async function loadProjectData() {
    try {
        const data = await apiGet(`/api/v1/projects/${currentProjectId}`);
        const project = data.project;

        initSidebar(currentProjectId, {
            student_name: project.student_name,
            student_level: project.student_level,
            description: project.description,
            chats: data.chats,
        });
    } catch (error) {
        console.error('Error loading project:', error);
    }
}

async function loadVocabulary() {
    try {
        vocabulary = await refreshVocabulary(currentProjectId);
        renderVocabulary(vocabulary, 'vocabularyList', true);
    } catch (error) {
        console.error('Error loading vocabulary:', error);
    }
}

function addVocabulary() {
    openModal('addVocabularyModal');
    setTimeout(() => document.getElementById('addVocabularyInput').focus(), 100);
}

function closeAddVocabularyModal() {
    closeModal('addVocabularyModal');
    document.getElementById('addVocabularyInput').value = '';
}

async function submitAddVocabulary(event) {
    event.preventDefault();
    const input = document.getElementById('addVocabularyInput');
    const value = input.value.trim();
    if (!value) return;
    try {
        vocabulary = await addVocabularyItem(currentProjectId, value);
        renderVocabulary(vocabulary, 'vocabularyList', true);
    } catch (error) {
        console.error('Error adding word:', error);
        alert('Error adding word');
    }
    closeAddVocabularyModal();
}

async function removeVocabulary(wordId) {
    try {
        vocabulary = await removeVocabularyItem(currentProjectId, wordId);
        renderVocabulary(vocabulary, 'vocabularyList', true);
    } catch (error) {
        console.error('Error removing word:', error);
    }
}

//////////////////////////////////////////////////
//////////////////// RENDER //////////////////////
//////////////////////////////////////////////////

function renderItems() {
    const container = document.getElementById('repeatContent');
    const filtered = getFilteredItems();

    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="repeat-empty">
                <p>No items yet</p>
                <p>Click "+ Add item" to add a test, quiz or survey</p>
            </div>
        `;
        return;
    }

    const todoItems = filtered.filter(i => i.status !== 'done');
    const doneItems = filtered.filter(i => i.status === 'done');

    let html = '';

    if (todoItems.length > 0 && currentFilter !== 'done') {
        html += `<p class="repeat-section-title">To do <span class="count">(${todoItems.length})</span></p>`;
        html += '<div class="repeat-grid">';
        todoItems.forEach(item => { html += renderTile(item); });
        html += '</div>';
    }

    if (doneItems.length > 0 && currentFilter !== 'todo') {
        html += `<p class="repeat-section-title">Completed <span class="count">(${doneItems.length})</span></p>`;
        html += '<div class="repeat-grid">';
        doneItems.forEach(item => { html += renderTile(item); });
        html += '</div>';
    }

    container.innerHTML = html;
}

function renderTile(item) {
    const isDone = item.status === 'done';

    const checkbox = isDone
        ? `<div class="repeat-checkbox checked" onclick="event.stopPropagation(); toggleStatus(${item.id})">
             <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
           </div>`
        : `<div class="repeat-checkbox" onclick="event.stopPropagation(); toggleStatus(${item.id})"></div>`;

    const dateStr = isDone && item.done_at
        ? `Done ${formatShortDate(item.done_at)}`
        : `Added ${formatShortDate(item.created_at)}`;

    const description = item.description
        ? `<p class="repeat-tile-desc">${escapeHtml(item.description)}</p>`
        : '';

    const files = item.files || [];
    const fileBadge = files.length > 0
        ? `<span class="repeat-tile-file-badge" title="${files.length} attachment${files.length > 1 ? 's' : ''}">
             <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
             ${files.length}
           </span>`
        : '';

    return `
        <div class="repeat-tile ${isDone ? 'done' : ''}" onclick="openModalUrl('repeat', ${item.id})">
            <button class="repeat-tile-delete" onclick="event.stopPropagation(); deleteItem(${item.id})" title="Delete">&times;</button>
            <div class="repeat-tile-header">
                ${checkbox}
            </div>
            <p class="repeat-tile-title">${escapeHtml(item.title)}</p>
            ${description}
            <div class="repeat-tile-footer">
                <span class="repeat-tile-date">${dateStr}</span>
                ${fileBadge}
            </div>
        </div>
    `;
}

function getFilteredItems() {
    if (currentFilter === 'todo') return repeatItems.filter(i => i.status !== 'done');
    if (currentFilter === 'done') return repeatItems.filter(i => i.status === 'done');
    return repeatItems;
}

function updateSubtitle() {
    const done = repeatItems.filter(i => i.status === 'done').length;
    const total = repeatItems.length;
    const el = document.getElementById('repeatProgress');
    if (el) el.textContent = `${done} of ${total} completed`;
}

//////////////////////////////////////////////////
//////////////////// ACTIONS /////////////////////
//////////////////////////////////////////////////

async function toggleStatus(itemId) {
    const item = repeatItems.find(i => i.id === itemId);
    if (!item) return;

    const newStatus = item.status === 'done' ? 'todo' : 'done';

    try {
        const data = await apiPatch(`/api/v1/repeat-items/${itemId}`, { status: newStatus });

        const idx = repeatItems.findIndex(i => i.id === itemId);
        if (idx !== -1) repeatItems[idx] = data.item;

        renderItems();
        updateSubtitle();
    } catch (error) {
        console.error('Error toggling status:', error);
    }
}

async function deleteItem(itemId) {
    if (!confirm('Delete this item?')) return;

    try {
        await apiDelete(`/api/v1/repeat-items/${itemId}`);
        repeatItems = repeatItems.filter(i => i.id !== itemId);
        renderItems();
        updateSubtitle();
    } catch (error) {
        console.error('Error deleting item:', error);
    }
}

//////////////////////////////////////////////////
//////////////////// FILTER //////////////////////
//////////////////////////////////////////////////

function setupFilterTabs() {
    document.querySelectorAll('.repeat-filter-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            currentFilter = tab.dataset.filter;
            document.querySelectorAll('.repeat-filter-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            renderItems();
        });
    });
}

//////////////////////////////////////////////////
///////////////// ADD ITEM MODAL /////////////////
//////////////////////////////////////////////////

function openAddModal() {
    document.getElementById('addRepeatModal').style.display = 'flex';
    document.getElementById('repeatItemTitle').value = '';
    document.getElementById('repeatItemDesc').value = '';
    document.getElementById('repeatItemTitle').focus();

    // Reset modal to "add" mode
    document.getElementById('addRepeatModalTitle').textContent = 'Add item';
    document.getElementById('addRepeatSubmitBtn').textContent = 'Add';
    delete document.getElementById('addRepeatForm').dataset.editId;

    renderDropzone([]);
    setupDropzone(null);
}

function closeAddModal() {
    document.getElementById('addRepeatModal').style.display = 'none';
}

async function submitAddItem(e) {
    e.preventDefault();

    const form = document.getElementById('addRepeatForm');
    const editId = form.dataset.editId;

    const title = document.getElementById('repeatItemTitle').value.trim();
    const description = document.getElementById('repeatItemDesc').value.trim() || null;

    if (!title) return;

    try {
        if (editId) {
            // Update existing
            const data = await apiPatch(`/api/v1/repeat-items/${editId}`, { title, description });
            const idx = repeatItems.findIndex(i => i.id === parseInt(editId));
            if (idx !== -1) repeatItems[idx] = data.item;
        } else {
            // Create new
            const data = await apiPost(`/api/v1/repeat-items/${currentProjectId}`, { title, description });
            const newItem = data.item;

            // Upload any pending files
            newItem.files = [];
            for (const pf of _pendingFiles) {
                const formData = new FormData();
                formData.append('file', pf.file);
                try {
                    const fileResp = await fetch(`/api/v1/repeat-items/${newItem.id}/files`, {
                        method: 'POST',
                        credentials: 'same-origin',
                        body: formData,
                    });
                    if (fileResp.ok) {
                        const fileData = await fileResp.json();
                        newItem.files.push(fileData.file);
                    }
                } catch (err) {
                    console.error('Error uploading file:', err);
                }
            }
            _pendingFiles = [];

            repeatItems.unshift(newItem);
        }

        closeModalUrl('repeat');
        closeAddModal();
        renderItems();
        updateSubtitle();
    } catch (error) {
        console.error('Error saving repeat item:', error);
    }
}

//////////////////////////////////////////////////
//////////////// EDIT ITEM MODAL /////////////////
//////////////////////////////////////////////////

function openEditModal(itemId) {
    const item = repeatItems.find(i => i.id === itemId);
    if (!item) return;

    document.getElementById('addRepeatModal').style.display = 'flex';
    document.getElementById('repeatItemTitle').value = item.title;
    document.getElementById('repeatItemDesc').value = item.description || '';

    document.getElementById('addRepeatModalTitle').textContent = 'Edit item';
    document.getElementById('addRepeatSubmitBtn').textContent = 'Save';
    document.getElementById('addRepeatForm').dataset.editId = itemId;

    renderDropzone(item.files || []);
    setupDropzone(itemId);
}

//////////////////////////////////////////////////
////////////////// DROPZONE //////////////////////
//////////////////////////////////////////////////

// Pending files for add mode (not yet uploaded)
let _pendingFiles = []; // { file: File } objects
let _dropzoneItemId = null; // null = add mode, int = edit mode

function setupDropzone(itemId) {
    _dropzoneItemId = itemId;
    _pendingFiles = [];

    const zone = document.getElementById('repeatDropzone');
    zone.ondragover = (e) => { e.preventDefault(); zone.classList.add('drag-over'); };
    zone.ondragleave = () => zone.classList.remove('drag-over');
    zone.ondrop = (e) => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        handleRepeatFiles(Array.from(e.dataTransfer.files));
    };
}

function renderDropzone(savedFiles) {
    const tiles = document.getElementById('repeatDropzoneTiles');
    let html = '';

    // Saved files (already on server)
    savedFiles.forEach(f => {
        const ext = f.original_filename.split('.').pop().toUpperCase().slice(0, 4);
        html += `
            <div class="repeat-file-tile">
                <button type="button" class="repeat-file-tile-remove" onclick="deleteRepeatFile(${f.id})" title="Remove">&times;</button>
                <a href="/api/v1/repeat-items/files/view/${f.id}" target="_blank" onclick="event.stopPropagation()" class="repeat-file-tile-inner">
                    <div class="repeat-file-tile-icon">
                        <svg width="22" height="28" viewBox="0 0 24 30" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 2h10l6 6v20a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><polyline points="14 2 14 8 20 8"/></svg>
                        <span class="repeat-file-tile-ext">${escapeHtml(ext)}</span>
                    </div>
                    <span class="repeat-file-tile-name">${escapeHtml(f.original_filename)}</span>
                </a>
            </div>`;
    });

    // Pending files (add mode only, not yet uploaded)
    _pendingFiles.forEach((pf, idx) => {
        const ext = pf.file.name.split('.').pop().toUpperCase().slice(0, 4);
        html += `
            <div class="repeat-file-tile pending">
                <button type="button" class="repeat-file-tile-remove" onclick="removePendingFile(${idx})" title="Remove">&times;</button>
                <div class="repeat-file-tile-inner">
                    <div class="repeat-file-tile-icon">
                        <svg width="22" height="28" viewBox="0 0 24 30" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 2h10l6 6v20a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><polyline points="14 2 14 8 20 8"/></svg>
                        <span class="repeat-file-tile-ext">${escapeHtml(ext)}</span>
                    </div>
                    <span class="repeat-file-tile-name">${escapeHtml(pf.file.name)}</span>
                </div>
            </div>`;
    });

    // Add tile
    html += `
        <div class="repeat-file-tile add-tile" onclick="document.getElementById('repeatFileInput').click()" title="Add file">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </div>`;

    tiles.innerHTML = html;
}

function handleRepeatFileSelect(event) {
    handleRepeatFiles(Array.from(event.target.files));
    event.target.value = '';
}

async function handleRepeatFiles(files) {
    if (!files.length) return;

    if (_dropzoneItemId === null) {
        // Add mode: queue files, re-render
        files.forEach(f => _pendingFiles.push({ file: f }));
        // Get current saved files (empty in add mode)
        renderDropzone([]);
    } else {
        // Edit mode: upload immediately
        const editId = _dropzoneItemId;
        for (const file of files) {
            const formData = new FormData();
            formData.append('file', file);
            try {
                const response = await fetch(`/api/v1/repeat-items/${editId}/files`, {
                    method: 'POST',
                    headers: { ...getAuthHeaders() },
                    body: formData,
                });
                if (!response.ok) {
                    const err = await response.json();
                    alert(err.detail || 'Upload failed');
                    continue;
                }
                const data = await response.json();
                const idx = repeatItems.findIndex(i => i.id === editId);
                if (idx !== -1) {
                    if (!repeatItems[idx].files) repeatItems[idx].files = [];
                    repeatItems[idx].files.push(data.file);
                }
            } catch (err) {
                console.error('Error uploading file:', err);
            }
        }
        const idx = repeatItems.findIndex(i => i.id === editId);
        const savedFiles = idx !== -1 ? (repeatItems[idx].files || []) : [];
        renderDropzone(savedFiles);
        renderItems();
    }
}

function removePendingFile(idx) {
    _pendingFiles.splice(idx, 1);
    renderDropzone([]);
}

async function deleteRepeatFile(fileId) {
    const editId = _dropzoneItemId;

    try {
        await apiDelete(`/api/v1/repeat-items/files/${fileId}`);

        if (editId !== null) {
            const idx = repeatItems.findIndex(i => i.id === editId);
            if (idx !== -1) {
                repeatItems[idx].files = (repeatItems[idx].files || []).filter(f => f.id !== fileId);
                renderDropzone(repeatItems[idx].files);
                renderItems();
            }
        }
    } catch (error) {
        console.error('Error deleting file:', error);
    }
}

//////////////////////////////////////////////////
//////////////////// HELPERS /////////////////////
//////////////////////////////////////////////////

function formatShortDate(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${months[d.getMonth()]} ${d.getDate()}`;
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}


//////////////////////////////////////////////////
//////////////////// INIT ////////////////////////
//////////////////////////////////////////////////

document.addEventListener('DOMContentLoaded', initRepeatPage);
