// Materials Page - Teaching Materials Library
// Dependencies: utils/dom.js, utils/helpers.js, components/sidebar.js, components/modal.js

// State
let materials = [];
let currentEditingMaterialId = null;
let filters = {
    level: 'all',
    tags: []
};
let searchQuery = '';
let allTags = new Set();

// Attachment state for add/edit modal
let pendingLinks = [];   // { url, name }
let pendingFiles = [];   // File objects
let existingLinks = [];  // Already saved links (when editing)
let existingFiles = [];  // Already saved files (when editing)

//////////////////////////////////////////////////
///////////////////INITIALIZATION/////////////////
//////////////////////////////////////////////////

function initMaterialsPage() {
    initTheme();
    loadMaterials();
    setupEventListeners();
    updateSearchClearButton();
}

// Theme toggle (inlined — no sidebar.js on this page)
function initTheme() {
    const saved = localStorage.getItem('theme') || 'dark';
    if (saved === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    }
    updateThemeIcon(saved);
}

function toggleTheme() {
    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    const newTheme = isLight ? 'dark' : 'light';
    if (newTheme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    } else {
        document.documentElement.removeAttribute('data-theme');
    }
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    const sun = document.getElementById('themeIconSun');
    const moon = document.getElementById('themeIconMoon');
    if (!sun || !moon) return;
    if (theme === 'light') {
        sun.style.display = 'block';
        moon.style.display = 'none';
    } else {
        sun.style.display = 'none';
        moon.style.display = 'block';
    }
}

//////////////////////////////////////////////////
///////////////////CRUD OPERATIONS////////////////
//////////////////////////////////////////////////

async function loadMaterials() {
    try {
        const data = await apiGet('/api/v1/materials/');
        materials = data.materials || [];

        extractAllTags();
        renderMaterials();
    } catch (error) {
        console.error('Ошибка загрузки материалов:', error);
        materials = [];
        renderMaterials();
    }

    // Bind ?material=<int> to the view modal. Registered after data is in
    // memory so the helper's initial sweep can resolve the id against
    // `materials`. Open: route through the helper; missing id → no-op.
    registerModalUrl({
        key: 'material',
        idType: 'int',
        onOpen: (id) => {
            if (materials.some(m => m.id === id)) {
                viewMaterial(id);
            }
        },
        onClose: closeViewMaterialModal,
    });
}

function extractAllTags() {
    allTags.clear();
    materials.forEach(material => {
        if (material.tags && Array.isArray(material.tags)) {
            material.tags.forEach(tag => {
                allTags.add(tag.toLowerCase());
            });
        }
    });
}

async function saveMaterial(event) {
    event.preventDefault();

    const form = event.target;
    const editingId = form.dataset.editingId || currentEditingMaterialId;

    const materialData = {
        name: document.getElementById('materialName').value.trim(),
        level: document.getElementById('materialLevel').value,
        tags: document.getElementById('materialTags').value.split(',').map(t => t.trim()).filter(t => t),
        content: document.getElementById('materialContent').value.trim(),
        answers: document.getElementById('materialAnswers').value.trim()
    };

    try {
        flushPendingLinkInput();

        let materialId;
        if (editingId) {
            // Update existing material
            const data = await apiPatch(`/api/v1/materials/${editingId}`, materialData);
            materialId = editingId;

            const numericId = Number(editingId);
            const index = materials.findIndex(m => m.id === numericId);

            if (index !== -1) {
                materials[index] = data.material;
            }
        } else {
            // Create new material
            const data = await apiPost('/api/v1/materials/', materialData);
            materialId = data.material.id;
            materials.push(data.material);
        }

        // Upload pending files
        for (const file of pendingFiles) {
            await uploadMaterialFile(materialId, file);
        }

        // Save pending links
        for (const link of pendingLinks) {
            await apiPost(`/api/v1/materials/${materialId}/links`, link);
        }

        // Reload to get fresh data with attachments
        await loadMaterials();
        closeAddMaterialModal();
        renderMaterials();
    } catch (error) {
        console.error('Ошибка сохранения материала:', error);
        alert(error.message || 'Ошибка сохранения материала');
    }
}

async function deleteMaterial(materialId, event) {
    if (event) {
        event.stopPropagation();
    }

    if (!confirm('Удалить этот материал?')) {
        return;
    }

    try {
        await apiDelete(`/api/v1/materials/${materialId}`);
        materials = materials.filter(m => m.id !== materialId);
        extractAllTags();
        renderMaterials();
    } catch (error) {
        console.error('Ошибка удаления материала:', error);
        alert('Ошибка удаления материала');
    }
}

//////////////////////////////////////////////////
////////////////////RENDERING/////////////////////
//////////////////////////////////////////////////

function renderMaterials() {
    const grid = document.getElementById('materialsGrid');

    // Filter materials
    let filteredMaterials = materials;

    // Apply level filter
    if (filters.level !== 'all') {
        filteredMaterials = filteredMaterials.filter(m => m.level === filters.level);
    }

    // Apply tag filters
    if (filters.tags.length > 0) {
        filteredMaterials = filteredMaterials.filter(material => {
            const materialTags = (material.tags || []).map(t => t.toLowerCase());

            return filters.tags.every(filterTag =>
                materialTags.some(tag => tag.includes(filterTag.toLowerCase()))
            );
        });
    }

    // Apply search query
    if (searchQuery) {
        const query = searchQuery.toLowerCase();
        filteredMaterials = filteredMaterials.filter(material => {
            const searchableText = [
                material.name,
                material.content,
                material.answers,
                ...(material.tags || [])
            ].filter(t => t).join(' ').toLowerCase();

            return searchableText.includes(query);
        });
    }

    // Check if empty
    if (filteredMaterials.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📚</div>
                <div>Материалы не найдены</div>
            </div>
        `;
        return;
    }

    // Render materials
    grid.innerHTML = filteredMaterials.map(material => `
        <div class="material-card" onclick="openModalUrl('material', ${material.id})">
            <div class="material-header">
                <div class="material-actions">
                    <button class="btn-material-action" onclick="editMaterial(${material.id}, event)" title="Редактировать">
                        ✏️
                    </button>
                    <button class="btn-material-action delete" onclick="deleteMaterial(${material.id}, event)" title="Удалить">
                        🗑️
                    </button>
                </div>
            </div>
            <div class="material-name">${escapeHtml(material.name)}</div>
            <div class="material-tags">
                ${material.level ? `<span class="material-tag level level-${material.level.toLowerCase().replace(/\s+/g, '-')}">${material.level}</span>` : ''}
                ${(material.tags || []).slice(0, 2).map(tag => `<span class="material-tag clickable" onclick="addTagFilterFromCard(event, '${escapeHtml(tag)}')">${escapeHtml(tag)}</span>`).join('')}
                ${(material.tags || []).length > 2 ? `<span class="material-tag">+${(material.tags || []).length - 2}</span>` : ''}
            </div>
        </div>
    `).join('');
}

//////////////////////////////////////////////////
/////////////////////FILTERS//////////////////////
//////////////////////////////////////////////////

function toggleFilter(filterType, value) {
    if (value === 'all') {
        filters[filterType] = 'all';
    } else {
        filters[filterType] = value;
    }

    // Update active buttons
    document.querySelectorAll('.level-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    const targetBtn = document.querySelector(`.level-btn[data-level="${value}"]`);
    if (targetBtn) {
        targetBtn.classList.add('active');
    }

    renderMaterials();
}

function addTagFilter(tag) {
    const normalizedTag = tag.toLowerCase().trim();
    if (normalizedTag && !filters.tags.includes(normalizedTag)) {
        filters.tags.push(normalizedTag);
        renderSelectedTags();
        renderMaterials();

        const tagInput = document.getElementById('tagSearchInput');
        if (tagInput) {
            tagInput.value = '';
        }
        hideTagDropdown();
    }
}

function addTagFilterFromCard(event, tag) {
    event.stopPropagation();
    addTagFilter(tag);
}

function removeTagFilter(tag) {
    filters.tags = filters.tags.filter(t => t !== tag);
    renderSelectedTags();
    renderMaterials();
}

function renderSelectedTags() {
    const container = document.getElementById('selectedTags');

    if (filters.tags.length === 0) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = filters.tags.map(tag => `
        <div class="selected-tag">
            ${escapeHtml(tag)}
            <button onclick="removeTagFilter('${escapeHtml(tag)}')">×</button>
        </div>
    `).join('');
}

function clearAllFilters() {
    filters = {
        level: 'all',
        tags: []
    };
    searchQuery = '';

    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.value = '';
    }
    updateSearchClearButton();

    const tagInput = document.getElementById('tagSearchInput');
    if (tagInput) {
        tagInput.value = '';
    }

    // Reset all level buttons
    document.querySelectorAll('.level-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelectorAll('.level-btn[data-level="all"]').forEach(btn => {
        btn.classList.add('active');
    });

    renderSelectedTags();
    hideTagDropdown();
    renderMaterials();
}

function searchMaterials() {
    searchQuery = document.getElementById('searchInput').value.trim();
    updateSearchClearButton();
    renderMaterials();
}

function clearSearchQuery() {
    const searchInput = document.getElementById('searchInput');
    if (!searchInput) return;

    searchInput.value = '';
    searchQuery = '';
    updateSearchClearButton();
    renderMaterials();
    searchInput.focus();
}

function updateSearchClearButton() {
    const searchInput = document.getElementById('searchInput');
    const clearBtn = document.getElementById('searchClearBtn');
    if (!searchInput || !clearBtn) return;

    clearBtn.classList.toggle('visible', searchInput.value.trim().length > 0);
}

//////////////////////////////////////////////////
////////////////TAG DROPDOWN//////////////////////
//////////////////////////////////////////////////

function showTagDropdown() {
    renderAvailableTags();
    const dropdown = document.getElementById('tagDropdown');
    if (dropdown) {
        dropdown.classList.add('active');
    }
}

function hideTagDropdown() {
    const dropdown = document.getElementById('tagDropdown');
    if (dropdown) {
        dropdown.classList.remove('active');
    }
}

function filterAvailableTags() {
    const input = document.getElementById('tagSearchInput');
    if (input) {
        const searchTerm = input.value.toLowerCase().trim();
        renderAvailableTags(searchTerm);
    }
}

function renderAvailableTags(searchTerm = '') {
    const dropdown = document.getElementById('tagDropdown');
    if (!dropdown) return;

    // Get all tags and count their usage
    const tagCounts = new Map();
    materials.forEach(material => {
        if (material.tags && Array.isArray(material.tags)) {
            material.tags.forEach(tag => {
                const lowerTag = tag.toLowerCase();
                tagCounts.set(lowerTag, (tagCounts.get(lowerTag) || 0) + 1);
            });
        }
    });

    // Filter tags based on search term and already selected tags
    let availableTags = Array.from(tagCounts.keys())
        .filter(tag => !filters.tags.includes(tag))
        .filter(tag => !searchTerm || tag.includes(searchTerm))
        .sort();

    let html = '';

    // If user typed something not in existing tags, show "Add new tag" option
    if (searchTerm && !availableTags.includes(searchTerm) && !filters.tags.includes(searchTerm)) {
        html += `
            <div class="tag-dropdown-item tag-dropdown-add" onclick="addTagFilter('${escapeHtml(searchTerm)}')">
                <span>+ Добавить "${escapeHtml(searchTerm)}"</span>
            </div>
        `;
    }

    if (availableTags.length === 0 && !searchTerm) {
        html += `
            <div class="tag-dropdown-item no-results">
                Нет доступных тегов
            </div>
        `;
    } else if (availableTags.length === 0 && searchTerm) {
        html += `
            <div class="tag-dropdown-item no-results">
                Теги не найдены
            </div>
        `;
    } else {
        html += availableTags.map(tag => `
            <div class="tag-dropdown-item" onclick="addTagFilter('${escapeHtml(tag)}')">
                <span>${escapeHtml(tag)}</span>
                <span class="tag-count">${tagCounts.get(tag)}</span>
            </div>
        `).join('');
    }

    dropdown.innerHTML = html;
}

//////////////////////////////////////////////////
/////////////////////MODALS///////////////////////
//////////////////////////////////////////////////

function openAddMaterialModal() {
    currentEditingMaterialId = null;
    const form = document.querySelector('#addMaterialModal form');
    if (form) {
        delete form.dataset.editingId;
    }
    document.getElementById('modalTitle').textContent = 'Добавить материал';
    document.getElementById('materialName').value = '';
    setCustomSelectValue('materialLevel', 'Any');
    document.getElementById('materialTags').value = '';
    document.getElementById('materialContent').value = '';
    document.getElementById('materialAnswers').value = '';
    resetAttachmentState();
    openModal('addMaterialModal');
}

function closeAddMaterialModal() {
    closeModal('addMaterialModal');
    currentEditingMaterialId = null;
    const form = document.querySelector('#addMaterialModal form');
    if (form) {
        delete form.dataset.editingId;
    }
}

function editMaterial(materialId, event) {
    if (event) {
        event.stopPropagation();
    }

    const material = materials.find(m => m.id === materialId);
    if (!material) return;

    currentEditingMaterialId = materialId;

    // Store the ID on the form element itself
    const form = document.querySelector('#addMaterialModal form');
    if (form) {
        form.dataset.editingId = materialId;
    }

    document.getElementById('modalTitle').textContent = 'Редактировать материал';
    document.getElementById('materialName').value = material.name;
    setCustomSelectValue('materialLevel', material.level);
    document.getElementById('materialTags').value = (material.tags || []).join(', ');
    document.getElementById('materialContent').value = material.content;
    document.getElementById('materialAnswers').value = material.answers || '';
    resetAttachmentState();
    existingLinks = (material.links || []).slice();
    existingFiles = (material.files || []).slice();
    renderAttachmentsList();
    openModal('addMaterialModal');
}

function viewMaterial(materialId) {
    const material = materials.find(m => m.id === materialId);
    if (!material) return;

    currentEditingMaterialId = materialId;
    document.getElementById('viewMaterialTitle').textContent = material.name;

    // Render tags
    const tagsHtml = `
        ${material.level ? `<span class="material-tag level level-${material.level.toLowerCase().replace(/\s+/g, '-')}">${material.level}</span>` : ''}
        ${(material.tags || []).map(tag => `<span class="material-tag clickable" onclick="addTagFilterFromView(event, '${escapeHtml(tag)}')">${escapeHtml(tag)}</span>`).join('')}
    `;
    document.getElementById('viewMaterialTags').innerHTML = tagsHtml;

    // Render content and answers
    let contentHtml = `
        <div class="view-section">
            <div class="view-section-header">
                <h4 class="view-section-title">Упражнение:</h4>
                <button class="btn-copy-section" onclick="copySectionContent(event, 'content')" title="Copy">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                </button>
            </div>
            <div class="view-section-content" data-section="content">${escapeHtml(material.content)}</div>
        </div>
    `;

    if (material.answers && material.answers.trim()) {
        contentHtml += `
            <div class="view-section">
                <div class="view-section-header">
                    <h4 class="view-section-title">Ответы:</h4>
                    <button class="btn-copy-section" onclick="copySectionContent(event, 'answers')" title="Copy">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="9" y="9" width="13" height="13" rx="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                    </button>
                </div>
                <div class="view-section-content" data-section="answers">${escapeHtml(material.answers)}</div>
            </div>
        `;
    }

    document.getElementById('viewMaterialContent').innerHTML = contentHtml;

    // Render attachments
    const attachments = [
        ...(material.links || []).map(l => ({ ...l, _type: 'link' })),
        ...(material.files || []).map(f => ({ ...f, _type: 'file' })),
    ];
    const attachmentsContainer = document.getElementById('viewMaterialAttachments');
    if (attachments.length > 0) {
        attachmentsContainer.innerHTML = `
            <div class="view-section">
                <div class="view-section-header">
                    <h4 class="view-section-title">Вложения:</h4>
                </div>
                <div class="view-attachments-list">
                    ${attachments.map(att => {
                        if (att._type === 'link') {
                            return `
                                <a href="${escapeHtml(att.url)}" target="_blank" rel="noopener" class="view-attachment-item view-attachment-link">
                                    <div class="view-attachment-icon" style="background: rgba(46,125,184,0.08); border-color: rgba(46,125,184,0.15); color: #2E7DB8;">
                                        <svg width="14" height="14" fill="none" viewBox="0 0 16 16"><path d="M6.5 9.5a3 3 0 0 0 4.24 0l2-2a3 3 0 0 0-4.24-4.24L7.5 4.25" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M9.5 6.5a3 3 0 0 0-4.24 0l-2 2a3 3 0 0 0 4.24 4.24L8.5 11.75" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
                                    </div>
                                    <div class="view-attachment-info">
                                        <div class="view-attachment-name link-name">${escapeHtml(att.name)}</div>
                                        <div class="view-attachment-meta">${escapeHtml(att.url)}</div>
                                    </div>
                                    <svg class="view-attachment-external" width="14" height="14" fill="none" viewBox="0 0 16 16"><path d="M6 3h-2.5A1.5 1.5 0 0 0 2 4.5v8A1.5 1.5 0 0 0 3.5 14h8A1.5 1.5 0 0 0 13 12.5V10M9.5 2H14v4.5M14 2L7 9" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                </a>`;
                        }
                        const fileColor = getAttachmentColor(att.file_type);
                        const fileIcon = getAttachmentIcon(att.file_type);
                        const sizeStr = formatFileSize(att.file_size);
                        const isAudio = att.file_type === 'audio';
                        return `
                            <div class="view-attachment-item" onclick="window.open('/api/v1/materials/files/view/${att.id}', '_blank')">
                                <div class="view-attachment-icon" style="background: ${fileColor}12; border-color: ${fileColor}25; color: ${fileColor};">
                                    ${fileIcon}
                                </div>
                                <div class="view-attachment-info">
                                    <div class="view-attachment-name">${escapeHtml(att.original_filename)}</div>
                                    <div class="view-attachment-meta">${sizeStr}</div>
                                </div>
                                ${isAudio ? `
                                    <button class="view-attachment-play" style="background: ${fileColor}15; border-color: ${fileColor}30; color: ${fileColor};" onclick="event.stopPropagation(); window.open('/api/v1/materials/files/view/${att.id}', '_blank')">
                                        <svg width="14" height="14" fill="none" viewBox="0 0 16 16"><path d="M4 2.5v11l9-5.5-9-5.5Z" fill="currentColor" opacity="0.8"/></svg>
                                    </button>
                                ` : ''}
                            </div>`;
                    }).join('')}
                </div>
            </div>
        `;
    } else {
        attachmentsContainer.innerHTML = '';
    }

    openModal('viewMaterialModal');
}

function copySectionContent(event, section) {
    event.stopPropagation();

    const sectionElement = document.querySelector(`[data-section="${section}"]`);
    if (!sectionElement) return;

    const text = sectionElement.innerText;

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(() => showCopiedState(event.currentTarget))
            .catch(() => fallbackCopy(text, event.currentTarget));
    } else {
        fallbackCopy(text, event.currentTarget);
    }
}

function fallbackCopy(text, button) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.top = '-1000px';
    textarea.style.left = '-1000px';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();

    try {
        document.execCommand('copy');
        showCopiedState(button);
    } catch (err) {
        console.error('Copy failed:', err);
    }

    document.body.removeChild(textarea);
}

function showCopiedState(button) {
    button.style.opacity = '0.6';
    setTimeout(() => {
        button.style.opacity = '1';
    }, 800);
}

function addTagFilterFromView(event, tag) {
    event.stopPropagation();
    closeModalUrl('material');
    addTagFilter(tag);
}

function closeViewMaterialModal() {
    closeModal('viewMaterialModal');
    currentEditingMaterialId = null;
}

function editCurrentMaterial() {
    editMaterial(currentEditingMaterialId, { stopPropagation: () => {} });
    closeModalUrl('material');
}

function deleteCurrentMaterial() {
    deleteMaterial(currentEditingMaterialId, null);
    closeModalUrl('material');
}

//////////////////////////////////////////////////
////////////////EVENT LISTENERS///////////////////
//////////////////////////////////////////////////

function setupEventListeners() {
    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        const dropdown = document.getElementById('tagDropdown');
        const input = document.getElementById('tagSearchInput');

        if (dropdown && input && !dropdown.contains(e.target) && e.target !== input) {
            hideTagDropdown();
        }
    });

    // Add tag on Enter key
    const tagInput = document.getElementById('tagSearchInput');
    if (tagInput) {
        tagInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const value = tagInput.value.trim();
                if (value) {
                    addTagFilter(value);
                }
            } else if (e.key === 'Escape') {
                hideTagDropdown();
                tagInput.blur();
            }
        });
    }

    // Close modals when clicking outside
    document.addEventListener('click', (e) => {
        const addMaterialModal = document.getElementById('addMaterialModal');
        const viewMaterialModal = document.getElementById('viewMaterialModal');

        // Close add/edit material modal
        if (addMaterialModal && addMaterialModal.classList.contains('active')) {
            const modalContent = addMaterialModal.querySelector('.modal-content');
            if (e.target === addMaterialModal && !modalContent.contains(e.target)) {
                closeAddMaterialModal();
            }
        }

        // Close view material modal
        if (viewMaterialModal && viewMaterialModal.classList.contains('active')) {
            const modalContent = viewMaterialModal.querySelector('.modal-content');
            if (e.target === viewMaterialModal && !modalContent.contains(e.target)) {
                closeModalUrl('material');
            }
        }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeAddMaterialModal();
            closeModalUrl('material');
        }
    });
}

//////////////////////////////////////////////////
//////////////ATTACHMENT HELPERS//////////////////
//////////////////////////////////////////////////

function resetAttachmentState() {
    pendingLinks = [];
    pendingFiles = [];
    existingLinks = [];
    existingFiles = [];
    const linkInput = document.getElementById('materialLinkInput');
    if (linkInput) linkInput.value = '';
    renderAttachmentsList();
}

function flushPendingLinkInput() {
    const input = document.getElementById('materialLinkInput');
    if (!input) return;

    const url = input.value.trim();
    if (!url) return;

    const alreadyAdded =
        pendingLinks.some(link => link.url === url) ||
        existingLinks.some(link => link.url === url);

    if (!alreadyAdded) {
        pendingLinks.push({ url, name: url });
    }

    input.value = '';
    renderAttachmentsList();
}

function addPendingLink() {
    flushPendingLinkInput();
}

function removePendingLink(index) {
    pendingLinks.splice(index, 1);
    renderAttachmentsList();
}

async function removeExistingLink(linkId) {
    try {
        await apiDelete(`/api/v1/materials/links/${linkId}`);
        existingLinks = existingLinks.filter(l => l.id !== linkId);
        renderAttachmentsList();
    } catch (err) {
        console.error('Error deleting link:', err);
    }
}

function handleMaterialFileDrop(event) {
    event.preventDefault();
    event.currentTarget.classList.remove('dragover');
    const files = Array.from(event.dataTransfer.files);
    pendingFiles.push(...files);
    renderAttachmentsList();
}

function handleMaterialFileSelect(event) {
    const files = Array.from(event.target.files);
    pendingFiles.push(...files);
    event.target.value = '';
    renderAttachmentsList();
}

function removePendingFile(index) {
    pendingFiles.splice(index, 1);
    renderAttachmentsList();
}

async function removeExistingFile(fileId) {
    try {
        await apiDelete(`/api/v1/materials/files/${fileId}`);
        existingFiles = existingFiles.filter(f => f.id !== fileId);
        renderAttachmentsList();
    } catch (err) {
        console.error('Error deleting file:', err);
    }
}

async function uploadMaterialFile(materialId, file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`/api/v1/materials/${materialId}/files`, {
        method: 'POST',
        credentials: 'same-origin',
        body: formData,
    });

    if (response.status === 401) {
        window.location.href = '/login';
        throw new Error('Unauthorized');
    }

    if (!response.ok) {
        let message = `Ошибка загрузки файла "${file.name}"`;

        try {
            const data = await response.json();
            if (data && data.detail) {
                message = `${message}: ${data.detail}`;
            }
        } catch (_) {
            message = `${message}: ${response.status} ${response.statusText}`;
        }

        throw new Error(message);
    }

    return response.json();
}

function renderAttachmentsList() {
    const container = document.getElementById('materialAttachmentsList');
    if (!container) return;

    const items = [];

    // Existing links
    existingLinks.forEach(link => {
        items.push(`
            <div class="attachment-item">
                <span class="attachment-item-icon" style="color: var(--link-color, #2E7DB8);">
                    <svg width="14" height="14" fill="none" viewBox="0 0 16 16"><path d="M6.5 9.5a3 3 0 0 0 4.24 0l2-2a3 3 0 0 0-4.24-4.24L7.5 4.25" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M9.5 6.5a3 3 0 0 0-4.24 0l-2 2a3 3 0 0 0 4.24 4.24L8.5 11.75" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
                </span>
                <span class="attachment-item-name link-name">${escapeHtml(link.url)}</span>
                <button type="button" class="attachment-item-remove" onclick="removeExistingLink(${link.id})">×</button>
            </div>
        `);
    });

    // Pending links
    pendingLinks.forEach((link, i) => {
        items.push(`
            <div class="attachment-item">
                <span class="attachment-item-icon" style="color: var(--link-color, #2E7DB8);">
                    <svg width="14" height="14" fill="none" viewBox="0 0 16 16"><path d="M6.5 9.5a3 3 0 0 0 4.24 0l2-2a3 3 0 0 0-4.24-4.24L7.5 4.25" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M9.5 6.5a3 3 0 0 0-4.24 0l-2 2a3 3 0 0 0 4.24 4.24L8.5 11.75" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
                </span>
                <span class="attachment-item-name link-name">${escapeHtml(link.url)}</span>
                <button type="button" class="attachment-item-remove" onclick="removePendingLink(${i})">×</button>
            </div>
        `);
    });

    // Existing files
    existingFiles.forEach(file => {
        const color = getAttachmentColor(file.file_type);
        const icon = getAttachmentIcon(file.file_type);
        const size = formatFileSize(file.file_size);
        items.push(`
            <div class="attachment-item">
                <span class="attachment-item-icon" style="color: ${color};">${icon}</span>
                <span class="attachment-item-name">${escapeHtml(file.original_filename)}</span>
                <span class="attachment-item-size">${size}</span>
                <button type="button" class="attachment-item-remove" onclick="removeExistingFile(${file.id})">×</button>
            </div>
        `);
    });

    // Pending files
    pendingFiles.forEach((file, i) => {
        const fileType = getFileTypeFromMime(file.type);
        const color = getAttachmentColor(fileType);
        const icon = getAttachmentIcon(fileType);
        const size = formatFileSize(file.size);
        items.push(`
            <div class="attachment-item">
                <span class="attachment-item-icon" style="color: ${color};">${icon}</span>
                <span class="attachment-item-name">${escapeHtml(file.name)}</span>
                <span class="attachment-item-size">${size}</span>
                <button type="button" class="attachment-item-remove" onclick="removePendingFile(${i})">×</button>
            </div>
        `);
    });

    container.innerHTML = items.join('');
}

function getFileTypeFromMime(mime) {
    if (!mime) return 'file';
    if (mime.startsWith('audio')) return 'audio';
    if (mime.includes('pdf')) return 'pdf';
    if (mime.includes('word') || mime.includes('docx')) return 'docx';
    if (mime.startsWith('image')) return 'image';
    return 'file';
}

function getAttachmentColor(type) {
    switch (type) {
        case 'pdf': return '#C8553D';
        case 'docx': return '#2E7DB8';
        case 'audio': return '#8FA38B';
        case 'image': return '#D4960A';
        default: return '#6B7D8D';
    }
}

function getAttachmentIcon(type) {
    switch (type) {
        case 'pdf':
            return '<svg width="14" height="14" fill="none" viewBox="0 0 20 20"><path d="M11 1.5H5.5A2 2 0 0 0 3.5 3.5v13A2 2 0 0 0 5.5 18.5h9a2 2 0 0 0 2-2V7L11 1.5Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M11 1.5V7h5.5" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><text x="7" y="14.5" fill="currentColor" font-size="5" font-weight="600" font-family="sans-serif">PDF</text></svg>';
        case 'docx':
            return '<svg width="14" height="14" fill="none" viewBox="0 0 20 20"><path d="M11 1.5H5.5A2 2 0 0 0 3.5 3.5v13A2 2 0 0 0 5.5 18.5h9a2 2 0 0 0 2-2V7L11 1.5Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M11 1.5V7h5.5" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M7 11h6M7 13.5h4" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>';
        case 'audio':
            return '<svg width="14" height="14" fill="none" viewBox="0 0 16 16"><rect x="5" y="1.5" width="6" height="8" rx="3" stroke="currentColor" stroke-width="1.2"/><path d="M3 7.5a5 5 0 0 0 10 0M8 12.5v2M6 14.5h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>';
        case 'image':
            return '<svg width="14" height="14" fill="none" viewBox="0 0 20 20"><rect x="2.5" y="2.5" width="15" height="15" rx="2.5" stroke="currentColor" stroke-width="1.2"/><circle cx="7" cy="7" r="1.5" stroke="currentColor" stroke-width="1"/><path d="M2.5 13l4-3.5 3.5 3L13.5 9l4 4.5v2a2.5 2.5 0 0 1-2.5 2.5H5a2.5 2.5 0 0 1-2.5-2.5V13Z" stroke="currentColor" stroke-width="1" stroke-linejoin="round"/></svg>';
        default:
            return '<svg width="14" height="14" fill="none" viewBox="0 0 16 16"><path d="M9 1.5H4.5A1.5 1.5 0 0 0 3 3v10a1.5 1.5 0 0 0 1.5 1.5h7A1.5 1.5 0 0 0 13 13V5.5L9 1.5Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M9 1.5V5.5H13" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>';
    }
}

function formatFileSize(bytes) {
    if (!bytes && bytes !== 0) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Initialize page
initMaterialsPage();
