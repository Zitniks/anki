// Chat Page - Messaging Interface
// Dependencies: utils/dom.js, utils/api.js, utils/helpers.js, components/sidebar.js, components/vocabulary.js, components/topics.js

// Get project ID from window (set in HTML)
const currentProjectId = PROJECT_ID;

// State
let currentChatId = null;
let chats = [];
let messages = [];
let vocabulary = [];
let currentAddItemType = null;
let currentAbortController = null;
let collapsedSections = { vocabulary: false };
let chatsSectionCollapsed = false;
let attachedFiles = [];

// Typewriter state — smooths out batchy network delivery
let twBuffer = '';     // chars received but not yet displayed
let twDisplayed = '';  // chars currently shown on screen
let twMsgIndex = null;
let twRAF = null;

// Configure marked
marked.setOptions({
    breaks: false,
    gfm: true,
    headerIds: false,
    mangle: false
});

//////////////////////////////////////////////////
///////////////////INITIALIZATION/////////////////
//////////////////////////////////////////////////

function initChatPage() {
    loadProject();
    loadSystemPrompts();
    setupEventListeners();
}

// Load project and chats
async function loadProject() {
    try {
        const data = await apiGet(`/api/v1/projects/${currentProjectId}`);

        const project = data.project;
        chats = data.chats || [];
        vocabulary = data.vocabulary || [];

        // Initialize shared sidebar with project data
        initSidebar(currentProjectId, {
            student_name: project.student_name,
            student_level: project.student_level,
            description: project.description,
            chats: chats,
        });

        // Render chats list
        renderChats();
        renderVocabulary(vocabulary, 'vocabularyList', true);

        // Chats aren't modals — drive URL <-> selection sync directly.
        // `selectChat` owns the URL push; initial load and Back/Forward
        // both flow through here.
        const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
        const urlPin = new URLSearchParams(location.search).get('chat');
        const validPin = urlPin && UUID_RE.test(urlPin) && chats.some(c => c.id === urlPin);
        if (validPin) {
            selectChat(urlPin);
        } else if (chats.length > 0) {
            selectChat(chats[0].id);
        } else {
            showChatWelcome();
        }

        window.addEventListener('popstate', () => {
            const id = new URLSearchParams(location.search).get('chat');
            if (id && UUID_RE.test(id) && chats.some(c => c.id === id) && id !== currentChatId) {
                selectChat(id);
            }
        });
    } catch (error) {
        console.error('Error loading project:', error);
        alert('Error loading project');
    }
}

//////////////////////////////////////////////////
/////////////////////CHATS////////////////////////
//////////////////////////////////////////////////

function renderChats() {
    // Sync sidebar chat list
    _sidebarChats = chats;
    renderSidebarChats();
}

// Create new chat
async function createNewChat() {
    const name = 'Untitled';

    try {
        const data = await apiPost(`/api/v1/projects/${currentProjectId}/chats`, { name });
        chats.push(data.chat);
        renderChats();
        selectChat(data.chat.id);
    } catch (error) {
        console.error('Error creating chat:', error);
        alert('Error creating chat');
    }
}

async function renameChat(chatId) {
    const chat = chats.find(c => c.id === chatId);
    if (!chat) return;

    const newName = prompt('Rename chat:', chat.name);
    if (!newName || newName.trim() === chat.name) return;

    try {
        await apiPatch(`/api/v1/chats/${chatId}`, { name: newName.trim() });

        chat.name = newName.trim();
        renderChats();
    } catch (error) {
        console.error('Rename chat failed:', error);
        alert('Error renaming chat');
    }
}

async function deleteChat(chatId) {
    if (!confirm('Delete this chat?')) return;

    try {
        await apiDelete(`/api/v1/chats/${chatId}`);

        chats = chats.filter(c => c.id !== chatId);

        if (currentChatId === chatId) {
            currentChatId = null;
            showChatWelcome();
        }

        renderChats();
    } catch (error) {
        console.error('Delete chat failed:', error);
        alert('Error deleting chat');
    }
}

async function generateChatName(chatId) {
    const chat = chats.find(c => c.id === chatId);
    if (!chat) return;

    if (chat.name !== "Untitled") return;

    try {
        const data = await apiPost(`/api/v1/chats/${chatId}/generate-name`);
        chat.name = data.generated_name;
        renderChats();
    } catch (error) {
        console.error('Generate chat name failed:', error);
    }
}

function openChatSettings() {
    const chat = chats.find(c => c.id === currentChatId);
    const toggle = document.getElementById('includeDescriptionToggle');
    if (toggle) toggle.checked = chat ? (chat.include_student_description ?? true) : true;
    const key = chat ? (chat.system_prompt_key ?? 'default') : 'default';
    setCustomSelectValue('systemPromptKeyInput', key);
    openModal('chatSettingsModal');
}

function closeChatSettings() {
    closeModal('chatSettingsModal');
}

async function saveChatSettings(includeDescription) {
    if (!currentChatId) return;
    const key = document.getElementById('systemPromptKeyInput')?.value ?? 'default';
    try {
        await apiPatch(`/api/v1/chats/${currentChatId}/settings`, {
            include_student_description: includeDescription,
            system_prompt_key: key,
        });
        const chat = chats.find(c => c.id === currentChatId);
        if (chat) chat.include_student_description = includeDescription;
    } catch (error) {
        console.error('Failed to save chat settings:', error);
    }
}

async function saveSystemPromptKey(key) {
    if (!currentChatId) return;
    const toggle = document.getElementById('includeDescriptionToggle');
    try {
        await apiPatch(`/api/v1/chats/${currentChatId}/settings`, {
            include_student_description: toggle?.checked ?? true,
            system_prompt_key: key,
        });
        const chat = chats.find(c => c.id === currentChatId);
        if (chat) chat.system_prompt_key = key;
    } catch (error) {
        console.error('Failed to save system prompt key:', error);
    }
}

async function loadSystemPrompts() {
    try {
        const data = await apiGet('/api/v1/system-prompts');
        const container = document.getElementById('systemPromptOptions');
        if (!container) return;
        container.innerHTML = data.prompts
            .map(p => `<div class="custom-select-option" data-value="${p.key}">${p.label}</div>`)
            .join('');
        document.getElementById('systemPromptKeyInput')?.addEventListener('change', (e) => {
            saveSystemPromptKey(e.target.value);
        });
    } catch (error) {
        console.error('Failed to load system prompts:', error);
    }
}

function toggleChatMenu(chatId) {
    document.querySelectorAll('.menu-dropdown').forEach(menu => {
        if (menu.id !== `chat-menu-${chatId}`) {
            menu.style.display = 'none';
        }
    });

    const menu = document.getElementById(`chat-menu-${chatId}`);
    menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
}

// Show chat welcome screen
function showChatWelcome() {
    document.getElementById('chatWelcome').style.display = 'flex';
    document.getElementById('messagesArea').style.display = 'none';
    const settingsBtn = document.getElementById('chatSettingsBtn');
    if (settingsBtn) settingsBtn.style.display = 'none';
    currentChatId = null;
}

// Select chat
async function selectChat(chatId) {
    if (chatId === currentChatId) return;
    currentChatId = chatId;

    // Keep ?chat=<uuid> in sync. Use replaceState on the very first
    // selection of a page load (no chat yet shown) to avoid leaving a
    // duplicate history entry behind the auto-pick; pushState afterwards
    // so Back navigates between previously-viewed chats.
    const params = new URLSearchParams(location.search);
    if (params.get('chat') !== chatId) {
        params.set('chat', chatId);
        const next = `${location.pathname}?${params.toString()}${location.hash}`;
        history.pushState(null, '', next);
    }

    renderChats();

    try {
        const data = await apiGet(`/api/v1/chats/${chatId}`);

        messages = data.messages || [];

        // Sync chat settings into local chats array
        const chat = chats.find(c => c.id === chatId);
        if (chat && data.chat) {
            chat.include_student_description = data.chat.include_student_description ?? true;
        }

        document.getElementById('chatWelcome').style.display = 'none';
        document.getElementById('messagesArea').style.display = 'flex';
        const settingsBtn = document.getElementById('chatSettingsBtn');
        if (settingsBtn) settingsBtn.style.display = 'flex';

        renderMessages(true, false);
    } catch (error) {
        console.error('Error loading chat:', error);
        alert('Error loading chat');
    }
}

//////////////////////////////////////////////////
////////////////////MESSAGES//////////////////////
//////////////////////////////////////////////////

// Render messages
function renderMessages(scrollToBottom = false, animate = true) {
    const container = document.getElementById('messagesArea');
    if (!animate) {
        container.classList.add('no-animate');
    }
    if (messages.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: var(--text-tertiary); padding: 40px;">No messages yet</div>';
        if (!animate) requestAnimationFrame(() => container.classList.remove('no-animate'));
        return;
    }

    container.innerHTML = messages.map((msg, index) => {
        const isUser = msg.role === 'user';
        const messageClass = isUser ? 'user-message' : 'assistant-message';

        if (messageClass === 'assistant-message') {
            const isStreaming = index === messages.length - 1 && msg.content === '';
            const thinkingHtml = (msg.thinking_blocks || []).map(thinking => `
                <details class="thought-block">
                    <summary class="thought-summary">
                        <svg class="thought-chevron" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                            <path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
                        </svg>
                        <span class="thought-label">Мысли модели</span>
                    </summary>
                    <div class="thought-content">${formatMessage(thinking)}</div>
                </details>
            `).join('');

            // Render files if present: image runs become collages, docs keep file-link cards.
            const filesHtml = msg.files && msg.files.length > 0 ? `
                <div class="message-files">
                    ${groupFilesForRender(msg.files).map(group => {
                        if (group.kind === 'images') {
                            return `<div class="cc-block">${collageHTML(filesToCollageImages(group.files))}</div>`;
                        }
                        const file = group.file;
                        const fileIcon = file.file_type === 'pdf' ? '📄' :
                                       file.file_type === 'docx' ? '📝' :
                                       file.file_type === 'audio' ? '🎵' : '🖼️';
                        const fileSize = file.file_size ? (file.file_size / 1024).toFixed(1) + ' KB' : '';
                        return `
                            <a href="/api/v1/files/download/${file.id}"
                               class="file-item"
                               download="${file.original_filename}"
                               title="Download ${file.original_filename}">
                                <span class="file-icon">${fileIcon}</span>
                                <div class="file-info">
                                    <div class="file-name">${truncateFilename(file.original_filename, 30)}</div>
                                    ${fileSize ? `<div class="file-size">${fileSize}</div>` : ''}
                                </div>
                            </a>
                        `;
                    }).join('')}
                </div>
            ` : '';

            return `
                <div class="${messageClass}" data-index="${index}">
                    <div class="message-content">
                        ${thinkingHtml}
                        <div class="message-text">${isStreaming ? '' : formatMessage(msg.content)}</div>
                        ${filesHtml}
                        ${isStreaming ? `
                            <div class="message-loading">
                                <span class="processing-text">Обработка...</span>
                            </div>
                        ` : `
                            <div class="message-actions">
                                <button class="btn-copy-message" onclick="copyAssistantMessage(this)" title="Copy">
                                    <svg width="14" height="14" viewBox="0 0 24 24"
                                        fill="none" stroke="currentColor" stroke-width="2"
                                        stroke-linecap="round" stroke-linejoin="round">
                                        <rect x="9" y="9" width="13" height="13" rx="2"></rect>
                                        <path d="M5 15H4a2 2 0 0 1-2-2V4
                                                a2 2 0 0 1 2-2h9
                                                a2 2 0 0 1 2 2v1"></path>
                                    </svg>
                                    Copy
                                </button>
                            </div>
                        `}
                    </div>
                </div>
            `;
        } else {
            // Render files if present: image runs become collages, docs keep file-link cards.
            const filesHtml = msg.files && msg.files.length > 0 ? `
                <div class="message-files">
                    ${groupFilesForRender(msg.files).map(group => {
                        if (group.kind === 'images') {
                            // Filter out pending images with no source yet — they'd render as broken tiles.
                            const ready = group.files.filter(f => f.dataUrl || f.id);
                            if (!ready.length) return '';
                            return `<div class="cc-block">${collageHTML(filesToCollageImages(ready))}</div>`;
                        }
                        const file = group.file;
                        const fileIcon = file.file_type === 'pdf' ? '📄' :
                                       file.file_type === 'docx' ? '📝' :
                                       file.file_type === 'audio' ? '🎵' : '🖼️';
                        const fileSize = (file.file_size / 1024).toFixed(1) + ' KB';
                        if (file.pending || !file.id) {
                            return `
                                <div class="file-item file-pending"
                                     title="${file.original_filename}">
                                    <span class="file-icon">${fileIcon}</span>
                                    <div class="file-info">
                                        <div class="file-name">${truncateFilename(file.original_filename, 30)}</div>
                                        <div class="file-size">${fileSize}</div>
                                    </div>
                                </div>
                            `;
                        }
                        return `
                            <a href="/api/v1/files/download/${file.id}"
                               class="file-item"
                               download="${file.original_filename}"
                               title="Download ${file.original_filename}">
                                <span class="file-icon">${fileIcon}</span>
                                <div class="file-info">
                                    <div class="file-name">${truncateFilename(file.original_filename, 30)}</div>
                                    <div class="file-size">${fileSize}</div>
                                </div>
                            </a>
                        `;
                    }).join('')}
                </div>
            ` : '';

            return `
                <div class="${messageClass}">
                    <div class="message-content">
                        ${filesHtml}
                        <div class="message-text">${formatMessage(msg.content)}</div>
                    </div>
                </div>
            `;
        }
    }).join('');

    if (!animate) {
        requestAnimationFrame(() => container.classList.remove('no-animate'));
    }

    if (scrollToBottom) {
        container.scrollTop = container.scrollHeight;
    }
}

// Update only the streaming message (prevents trembling and scroll issues)
function updateStreamingMessage(content, index) {
    const container = document.getElementById('messagesArea');
    const messageEl = container.querySelector(`[data-index="${index}"]`);
    if (!messageEl) return;

    const textEls = messageEl.querySelectorAll('.message-text');
    const textEl = textEls[textEls.length - 1];
    const loadingEl = messageEl.querySelector('.message-loading');

    // Remove loading indicator if present
    if (loadingEl) loadingEl.remove();

    // Update content
    if (textEl) {
        textEl.innerHTML = formatMessage(content);
    }

    // Add copy button if not present
    const contentEl = messageEl.querySelector('.message-content');
    if (contentEl && !contentEl.querySelector('.message-actions')) {
        const actionsHtml = `
            <div class="message-actions">
                <button class="btn-copy-message" onclick="copyAssistantMessage(this)" title="Copy">
                    <svg width="14" height="14" viewBox="0 0 24 24"
                        fill="none" stroke="currentColor" stroke-width="2"
                        stroke-linecap="round" stroke-linejoin="round">
                        <rect x="9" y="9" width="13" height="13" rx="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4
                                a2 2 0 0 1 2-2h9
                                a2 2 0 0 1 2 2v1"></path>
                    </svg>
                    Copy
                </button>
            </div>
        `;
        contentEl.insertAdjacentHTML('beforeend', actionsHtml);
    }

    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
    if (isNearBottom) {
        container.scrollTop = container.scrollHeight;
    }

    // container.scrollTop = container.scrollHeight;
}

// ===================== IMAGE COLLAGE =====================
// Smart mosaic layout (Telegram/iMessage style). Each image: {url, name, width, height, source}.
const COLLAGE_MAX_VISIBLE = 6;
const _land = (a) => a >= 1.2;
const _wide = (a) => a >= 1.5;

function _imgAspect(im) {
    return (im && im.width && im.height) ? im.width / im.height : 1.4;
}

function buildCollageLayout(images) {
    const n = Math.min(images.length, COLLAGE_MAX_VISIBLE);
    const ar = images.map(_imgAspect);
    const a0 = ar[0] ?? 1.4;

    if (n === 1) return null; // handled by single-image branch
    if (n === 2) {
        if (_land(ar[0]) && _land(ar[1]))
            return { cols: 1, rows: 2, aspect: 1.05, cells: [{c:[1,2],r:[1,2]}, {c:[1,2],r:[2,3]}] };
        return { cols: 2, rows: 1, aspect: 1.55, cells: [{c:[1,2],r:[1,2]}, {c:[2,3],r:[1,2]}] };
    }
    if (n === 3) {
        if (_land(a0))
            return { cols: 2, rows: 2, aspect: 1.02, rowTemplate: "1.32fr 1fr",
                cells: [{c:[1,3],r:[1,2]}, {c:[1,2],r:[2,3]}, {c:[2,3],r:[2,3]}] };
        return { cols: 2, rows: 2, aspect: 1.32, colTemplate: "1.42fr 1fr",
            cells: [{c:[1,2],r:[1,3]}, {c:[2,3],r:[1,2]}, {c:[2,3],r:[2,3]}] };
    }
    if (n === 4) {
        if (_wide(a0))
            return { cols: 3, rows: 2, aspect: 1.18, rowTemplate: "1.5fr 1fr",
                cells: [{c:[1,4],r:[1,2]}, {c:[1,2],r:[2,3]}, {c:[2,3],r:[2,3]}, {c:[3,4],r:[2,3]}] };
        return { cols: 2, rows: 2, aspect: 1.0,
            cells: [{c:[1,2],r:[1,2]}, {c:[2,3],r:[1,2]}, {c:[1,2],r:[2,3]}, {c:[2,3],r:[2,3]}] };
    }
    if (n === 5) {
        return { cols: 6, rows: 2, aspect: 1.42, rowTemplate: "1.16fr 1fr",
            cells: [
                {c:[1,4],r:[1,2]}, {c:[4,7],r:[1,2]},
                {c:[1,3],r:[2,3]}, {c:[3,5],r:[2,3]}, {c:[5,7],r:[2,3]},
            ]};
    }
    return { cols: 3, rows: 2, aspect: 1.5,
        cells: [
            {c:[1,2],r:[1,2]}, {c:[2,3],r:[1,2]}, {c:[3,4],r:[1,2]},
            {c:[1,2],r:[2,3]}, {c:[2,3],r:[2,3]}, {c:[3,4],r:[2,3]},
        ]};
}

function _escape(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
        '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
}

const _BADGE_AI_SVG = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/></svg>';
const _BADGE_CAM_SVG = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>';

function _tileHTML(img, gridStyle, moreCount, eager) {
    const altText = _escape(img.name || 'image');
    const url = _escape(img.url);
    let badge = '';
    if (img.source === 'generated') {
        badge = `<span class="cc-badge cc-badge-ai">${_BADGE_AI_SVG} AI</span>`;
    } else if (img.source === 'pexels') {
        badge = `<span class="cc-badge">${_BADGE_CAM_SVG} Pexels</span>`;
    }
    const more = moreCount > 0 ? `<div class="cc-more">+${moreCount}</div>` : '';
    return `
        <div class="cc-tile" style="${gridStyle}" tabindex="0" role="button"
             aria-label="${altText}" data-url="${url}">
            <div class="cc-shimmer"></div>
            <img class="cc-img" src="${url}" alt="${altText}" title="${altText}"
                 loading="${eager ? 'eager' : 'lazy'}"
                 onload="this.previousElementSibling && this.previousElementSibling.remove()">
            ${badge}
            ${more}
        </div>
    `;
}

function _singleHTML(img) {
    const altText = _escape(img.name || 'image');
    const url = _escape(img.url);
    const ar = _imgAspect(img);
    let badge = '';
    if (img.source === 'generated') {
        badge = `<span class="cc-badge cc-badge-ai">${_BADGE_AI_SVG} AI</span>`;
    } else if (img.source === 'pexels') {
        badge = `<span class="cc-badge">${_BADGE_CAM_SVG} Pexels</span>`;
    }
    return `
        <div class="cc-collage cc-single" style="aspect-ratio:${ar};max-height:460px;">
            <div class="cc-tile" style="width:100%;height:100%;" tabindex="0" role="button"
                 aria-label="${altText}" data-url="${url}">
                <div class="cc-shimmer"></div>
                <img class="cc-img" src="${url}" alt="${altText}" title="${altText}"
                     onload="this.previousElementSibling && this.previousElementSibling.remove()">
                ${badge}
            </div>
        </div>
    `;
}

function collageHTML(images) {
    if (!images || !images.length) return '';
    if (images.length === 1) return _singleHTML(images[0]);

    const layout = buildCollageLayout(images);
    const visible = images.slice(0, COLLAGE_MAX_VISIBLE);
    const overflow = images.length - COLLAGE_MAX_VISIBLE;

    const tiles = visible.map((img, i) => {
        const cell = layout.cells[i];
        const isLast = i === visible.length - 1;
        const gridStyle =
            `grid-column:${cell.c[0]}/${cell.c[1]};grid-row:${cell.r[0]}/${cell.r[1]};`;
        return _tileHTML(img, gridStyle, isLast && overflow > 0 ? overflow : 0, i < 4);
    }).join('');

    const gridStyle =
        `grid-template-columns:${layout.colTemplate || `repeat(${layout.cols}, 1fr)`};` +
        `grid-template-rows:${layout.rowTemplate || `repeat(${layout.rows}, 1fr)`};`;

    return `
        <div class="cc-collage" style="aspect-ratio:${layout.aspect};max-height:560px;">
            <div class="cc-grid" style="${gridStyle}">${tiles}</div>
        </div>
    `;
}

// Group image files into per-source consecutive runs; non-image files keep their slot.
// Used by renderMessage on history reload so collages don't blur source boundaries.
function groupFilesForRender(files) {
    const groups = [];
    let current = null;
    for (const f of files || []) {
        if (f.file_type === 'image') {
            const src = (f.meta && f.meta.source) || (f.pending ? 'pending' : 'unknown');
            if (current && current.kind === 'images' && current.source === src) {
                current.files.push(f);
            } else {
                current = { kind: 'images', source: src, files: [f] };
                groups.push(current);
            }
        } else {
            groups.push({ kind: 'file', file: f });
            current = null;
        }
    }
    return groups;
}

function filesToCollageImages(files) {
    return files.map((f) => {
        const src = f.dataUrl || (f.id ? `/api/v1/files/view/${f.id}` : '');
        return {
            url: src,
            name: f.original_filename || 'image',
            width: f.meta && f.meta.width,
            height: f.meta && f.meta.height,
            source: f.meta && f.meta.source,
        };
    });
}

// Live-stream append: render one collage block per batched 'images' event.
function appendCollageToMessage(messageIndex, images) {
    const container = document.getElementById('messagesArea');
    if (!container) return;
    const messageEl = container.querySelector(`[data-index="${messageIndex}"]`);
    if (!messageEl) return;
    const messageContent = messageEl.querySelector('.message-content');
    if (!messageContent) return;

    let filesContainer = messageContent.querySelector('.message-files');
    if (!filesContainer) {
        filesContainer = document.createElement('div');
        filesContainer.className = 'message-files';
        const textEl = messageContent.querySelector('.message-text');
        if (textEl) textEl.insertAdjacentElement('afterend', filesContainer);
        else messageContent.insertAdjacentElement('afterbegin', filesContainer);
    }

    const block = document.createElement('div');
    block.className = 'cc-block';
    block.innerHTML = collageHTML(images);
    filesContainer.appendChild(block);

    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
    if (isNearBottom) container.scrollTop = container.scrollHeight;
}

// Delegated click handler — open original (full) image on tile click.
document.addEventListener('click', (e) => {
    const tile = e.target.closest('.cc-tile');
    if (!tile) return;
    const url = tile.getAttribute('data-url');
    if (url) window.open(url, '_blank');
});
document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const tile = document.activeElement && document.activeElement.closest && document.activeElement.closest('.cc-tile');
    if (!tile) return;
    e.preventDefault();
    const url = tile.getAttribute('data-url');
    if (url) window.open(url, '_blank');
});

// Format message with markdown
function formatMessage(text) {
    // Convert bare URLs to markdown links so marked renders them as <a> tags.
    // Only fire when preceded by whitespace or start-of-string — NOT after '('
    // or ']', so existing markdown links like `[text](url)` aren't double-wrapped
    // into `[text]([url](url))` (which then breaks the parser).
    text = text.replace(/(^|\s)(https?:\/\/[^\s)]+)/g, '$1[$2]($2)');
    let html = marked.parse(text);
    html = html.replace(
        /<a\s+href="([^"]+)"(.*?)>(.*?)<\/a>/g,
        '<a href="$1"$2 target="_blank" rel="noopener noreferrer">$3</a>'
    );
    // Wrap tables in a scrollable container with a copy-as-image button
    const copyImgBtn = `<button class="btn-copy-schema-image" onclick="copySchemaAsImage(this)" title="Copy as image">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2"></rect>
            <circle cx="8.5" cy="8.5" r="1.5"></circle>
            <polyline points="21 15 16 10 5 21"></polyline>
        </svg>
        Copy image
    </button>`;
    html = html.replace(/<table>/g, `<div class="schema-wrapper">${copyImgBtn}<div class="table-wrapper"><table>`);
    html = html.replace(/<\/table>/g, '</table></div></div>');
    // Wrap pre blocks (ASCII diagrams) with same copy button
    html = html.replace(/<pre>/g, `<div class="schema-wrapper">${copyImgBtn}<pre>`);
    html = html.replace(/<\/pre>/g, '</pre></div>');
    return html;
}

async function copySchemaAsImage(btn) {
    const wrapper = btn.closest('.schema-wrapper');
    if (!wrapper) return;

    // Temporarily hide the button while capturing
    btn.style.visibility = 'hidden';
    try {
        const canvas = await html2canvas(wrapper, { backgroundColor: null, scale: 2 });
        canvas.toBlob(blob => {
            if (!blob) return;
            navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
                .then(() => {
                    btn.style.visibility = '';
                    const orig = btn.innerHTML;
                    btn.textContent = 'Copied!';
                    setTimeout(() => { btn.innerHTML = orig; }, 1500);
                })
                .catch(() => { btn.style.visibility = ''; });
        }, 'image/png');
    } catch (e) {
        btn.style.visibility = '';
        console.error('copySchemaAsImage failed:', e);
    }
}

function appendThinkingBlock(msgIndex) {
    const container = document.getElementById('messagesArea');
    const messageEl = container.querySelector(`[data-index="${msgIndex}"]`);
    if (!messageEl) return;

    const messageContent = messageEl.querySelector('.message-content');
    if (!messageContent) return;

    const detailsEl = document.createElement('details');
    detailsEl.className = 'thought-block';
    detailsEl.open = true;
    detailsEl.innerHTML = `
        <summary class="thought-summary">
            <svg class="thought-chevron" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
            </svg>
            <span class="thought-label">Мысли модели</span>
        </summary>
        <div class="thought-content"></div>
    `;

    const textEl = messageContent.querySelector('.message-text');
    if (textEl) {
        messageContent.insertBefore(detailsEl, textEl);
    } else {
        messageContent.insertAdjacentElement('afterbegin', detailsEl);
    }
}

function updateCurrentThinkingBlock(msgIndex, text) {
    const container = document.getElementById('messagesArea');
    const messageEl = container.querySelector(`[data-index="${msgIndex}"]`);
    if (!messageEl) return;

    const thoughtBlocks = messageEl.querySelectorAll('.thought-content');
    const thoughtEl = thoughtBlocks[thoughtBlocks.length - 1];
    if (!thoughtEl) return;

    thoughtEl.innerHTML = formatMessage(text);

    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
    if (isNearBottom) {
        container.scrollTop = container.scrollHeight;
    }
}

function collapseCurrentThinkingBlock(msgIndex) {
    const container = document.getElementById('messagesArea');
    const messageEl = container.querySelector(`[data-index="${msgIndex}"]`);
    if (!messageEl) return;

    const thoughtBlocks = messageEl.querySelectorAll('.thought-block');
    const thoughtBlock = thoughtBlocks[thoughtBlocks.length - 1];
    if (!thoughtBlock) return;

    thoughtBlock.open = false;
}

//////////////////////////////////////////////////
////////////////PROCESSING STATUS/////////////////
//////////////////////////////////////////////////

function updateProcessingStatus(message, isWarning = false) {
    // Update the loading indicator inside the assistant message bubble
    const container = document.getElementById('messagesArea');
    const loadingEl = container.querySelector('.message-loading');
    if (!loadingEl) return;

    const textEl = loadingEl.querySelector('.processing-text');
    const glowEl = loadingEl.querySelector('.processing-glow');

    if (textEl) {
        textEl.textContent = message;
    }

    if (isWarning && glowEl) {
        glowEl.classList.add('warning');
        if (textEl) textEl.classList.add('warning');
    }
}

function showSystemWarning(text) {
    const el = document.createElement('div');
    el.className = 'system-warning';

    const textSpan = document.createElement('span');
    textSpan.textContent = '⚠ ' + text;

    const closeBtn = document.createElement('button');
    closeBtn.className = 'system-warning-close';
    closeBtn.textContent = '×';
    closeBtn.onclick = () => el.remove();

    el.appendChild(textSpan);
    el.appendChild(closeBtn);
    document.getElementById('warningArea').appendChild(el);
}

// Feed new content into the typewriter queue
function twFeed(fullContent, msgIndex) {
    const alreadyKnown = twDisplayed.length + twBuffer.length;
    const newChars = fullContent.slice(alreadyKnown);
    if (newChars) twBuffer += newChars;
    twMsgIndex = msgIndex;
    if (!twRAF && twBuffer.length > 0) {
        twRAF = requestAnimationFrame(twTick);
    }
}

// Animation frame tick — drains the typewriter queue
function twTick() {
    if (!twBuffer.length) {
        twRAF = null;
        return;
    }
    // Adaptive speed: drain faster when queue is large to avoid lag at end of stream
    const perFrame = Math.max(2, Math.ceil(twBuffer.length / 10));
    twDisplayed += twBuffer.slice(0, perFrame);
    twBuffer = twBuffer.slice(perFrame);
    updateStreamingMessage(twDisplayed, twMsgIndex);
    twRAF = requestAnimationFrame(twTick);
}

// Flush remaining queued chars immediately (called on stream end / abort)
function twFlush() {
    if (twRAF) { cancelAnimationFrame(twRAF); twRAF = null; }
    if (twBuffer.length) {
        twDisplayed += twBuffer;
        twBuffer = '';
        if (twMsgIndex !== null) {
            updateStreamingMessage(twDisplayed, twMsgIndex);
        }
    }
}

// Reset typewriter state for a new message
function twReset() {
    if (twRAF) { cancelAnimationFrame(twRAF); twRAF = null; }
    twBuffer = '';
    twDisplayed = '';
    twMsgIndex = null;
}

function showStreamError(message) {
    const container = document.getElementById('messagesArea');
    const loadingEl = container.querySelector('.message-loading');
    if (loadingEl) {
        loadingEl.innerHTML = `
            <span style="font-size:14px; color:#e57373;">
                Ошибка: ${escapeHtml(message)}
            </span>`;
    }
}

// Send message with streaming
async function sendMessage() {
    if (!currentChatId) {
        await createNewChat();
        if (!currentChatId) return;
    }

    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    if (!message && attachedFiles.length === 0) return;

    const sendBtn = document.getElementById('sendBtn');

    currentAbortController = new AbortController();
    sendBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <rect x="5" y="5" width="14" height="14" rx="3"></rect>
        </svg>`;
    sendBtn.onclick = stopGeneration;
    sendBtn.classList.add('generating');

    messages.push({
        role: 'user',
        content: message,
        timestamp: new Date().toISOString(),
        images: attachedFiles.map(img => ({
            dataUrl: img.dataUrl,
            name: img.name
        })),
        files: attachedFiles.map(file => ({
            id: null, // Will be set after reload
            original_filename: file.name,
            file_type: file.type || 'image',
            file_size: file.dataUrl ? Math.round(file.dataUrl.length * 0.75) : 0, // Approximate size
            dataUrl: file.dataUrl, // Include dataUrl for immediate image preview
            pending: true // Mark as pending upload
        }))
    });

    input.value = '';
    autoResize(input);

    const filesToSend = [...attachedFiles];
    clearAttachedFiles();

    // Render user message
    renderMessages(true);

    const assistantMessageIndex = messages.length;
    messages.push({
        role: 'assistant',
        content: '',
        thinking_blocks: [],
        timestamp: new Date().toISOString()
    });

    // Render with loading indicator in assistant bubble, scroll to bottom
    renderMessages(true);

    // Update processing status based on file types
    const hasDocuments = filesToSend.some(f => f.type === 'pdf' || f.type === 'docx');
    const hasImages = filesToSend.some(f => f.type === 'image');
    const hasAudio = filesToSend.some(f => f.type === 'audio');

    if (hasAudio) {
        updateProcessingStatus('Транскрибация аудио...');
    } else if (hasDocuments) {
        updateProcessingStatus('Извлечение текста из документа...');
    } else if (hasImages) {
        updateProcessingStatus('Анализ изображения...');
    }

    twReset();

    let doneReceived = false;

    try {
        const requestBody = {
            message: message,
            attachments: filesToSend.map(f => ({
                dataUrl: f.dataUrl,
                name: f.name
            }))
        };

        const response = await fetch(`/api/v1/chats/${currentChatId}/messages/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(requestBody),
            signal: currentAbortController.signal
        });

        if (response.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = '/login';
            return;
        }

        if (!response.ok) {
            let errorMsg = 'Network response was not ok';
            try {
                const errBody = await response.json();
                if (errBody.detail) errorMsg = errBody.detail;
            } catch (_) {}
            throw new Error(errorMsg);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let assistantMessage = '';
        let currentThinkingText = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);

                    try {
                        const parsed = JSON.parse(data);

                        // Resolve event type — prefer explicit 'type' field,
                        // fall back to key-based detection for backward compatibility
                        const eventType = parsed.type || (
                            parsed.status         ? 'status'         :
                            parsed.warning        ? 'warning'        :
                            parsed.content        ? 'content'        :
                            parsed.images         ? 'images'         :
                            parsed.vocabulary     ? 'vocabulary'     :
                            parsed.error          ? 'error'          : null
                        );

                        if (eventType === 'done') {
                            doneReceived = true;
                            twFlush();
                            await refreshVocabularyAndTopics(currentProjectId);
                            continue;
                        }

                        if (eventType === 'status') {
                            updateProcessingStatus(parsed.status);
                        }

                        if (eventType === 'warning') {
                            showSystemWarning(parsed.warning);
                        }

                        if (eventType === 'error') {
                            showStreamError(parsed.error);
                        }

                        if (eventType === 'images') {
                            const incoming = parsed.images || [];
                            if (incoming.length) {
                                if (!messages[assistantMessageIndex].files) {
                                    messages[assistantMessageIndex].files = [];
                                }
                                for (const img of incoming) {
                                    messages[assistantMessageIndex].files.push({
                                        id: null,
                                        original_filename: img.name || 'image',
                                        file_type: 'image',
                                        file_size: 0,
                                        dataUrl: img.url,
                                        meta: {
                                            width: img.width,
                                            height: img.height,
                                            source: img.source,
                                        },
                                    });
                                }
                                appendCollageToMessage(assistantMessageIndex, incoming);
                            }
                        }

                        if (eventType === 'thinking_start') {
                            currentThinkingText = '';
                            twFlush();
                            appendThinkingBlock(assistantMessageIndex);
                        }

                        if (eventType === 'thinking') {
                            currentThinkingText += parsed.content;
                            updateCurrentThinkingBlock(assistantMessageIndex, currentThinkingText);
                        }

                        if (eventType === 'thinking_done') {
                            if (currentThinkingText) {
                                messages[assistantMessageIndex].thinking_blocks.push(currentThinkingText);
                            }
                            collapseCurrentThinkingBlock(assistantMessageIndex);
                            currentThinkingText = '';
                            twReset();
                        }

                        if (eventType === 'thought_wrap') {
                            // Wrap pre-tool visible text into a persisted thinking block.
                            twFlush();
                            const container = document.getElementById('messagesArea');
                            const messageEl = container.querySelector(`[data-index="${assistantMessageIndex}"]`);
                            if (messageEl) {
                                const textEls = messageEl.querySelectorAll('.message-text');
                                const textEl = textEls[textEls.length - 1];
                                if (textEl && assistantMessage.trim()) {
                                    messages[assistantMessageIndex].thinking_blocks.push(assistantMessage);
                                    appendThinkingBlock(assistantMessageIndex);
                                    updateCurrentThinkingBlock(assistantMessageIndex, assistantMessage);
                                    collapseCurrentThinkingBlock(assistantMessageIndex);
                                    textEl.innerHTML = '';
                                }
                            }
                            twReset();
                            assistantMessage = '';
                            messages[assistantMessageIndex].content = '';
                        }

                        if (eventType === 'content') {
                            assistantMessage += parsed.content;
                            messages[assistantMessageIndex].content = assistantMessage;
                            twFeed(assistantMessage, assistantMessageIndex);
                        }
                    } catch (e) {
                        // Skip invalid JSON
                    }
                }
            }
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Stream stopped by user');
            twFlush();
            renderMessages();
        } else {
            console.error('Error sending message:', error);
            showStreamError(error.message);
        }
    } finally {
        twFlush();
        await generateChatName(currentChatId);
        currentAbortController = null;
        sendBtn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 2L11 13"></path>
                <path d="M22 2L15 22L11 13L2 9L22 2Z"></path>
            </svg>`;
        sendBtn.onclick = sendMessage;
        sendBtn.classList.remove('generating');
        sendBtn.disabled = false;

        if (!doneReceived) {
            await refreshVocabularyAndTopics(currentProjectId);
        }
    }
}

function stopGeneration() {
    if (currentAbortController) {
        currentAbortController.abort();
    }
}

function copyAssistantMessage(button) {
    const messageEl = button.closest('.assistant-message');
    const textEl = messageEl?.querySelector('.message-text');

    if (!textEl) return;

    const text = textEl.innerText;

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(() => showCopiedState(button))
            .catch(() => fallbackCopy(text, button));
    } else {
        fallbackCopy(text, button);
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
    if (button.dataset.copying) return;
    button.dataset.copying = '1';

    const original = button.innerHTML;
    button.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        Copied
    `;
    button.classList.add('copied');

    setTimeout(() => {
        button.innerHTML = original;
        button.classList.remove('copied');
        delete button.dataset.copying;
    }, 1500);
}

//////////////////////////////////////////////////
//////////////VOCABULARY AND TOPICS///////////////
//////////////////////////////////////////////////

async function refreshVocabularyAndTopics(projectId) {
    try {
        const oldVocabIds = new Set((vocabulary || []).map(w => w.id));
        vocabulary = await refreshVocabulary(projectId);
        const newVocabIds = new Set(vocabulary.filter(w => !oldVocabIds.has(w.id)).map(w => w.id));
        renderVocabulary(vocabulary, 'vocabularyList', true, newVocabIds);

    } catch (error) {
        console.error('Error updating vocabulary:', error);
    }
}

function addVocabulary() {
    currentAddItemType = 'vocabulary';
    document.getElementById('addItemTitle').textContent = 'Add Word';
    document.getElementById('addItemInput').placeholder = 'Enter word or phrase...';
    openModal('addItemModal');
    setTimeout(() => document.getElementById('addItemInput').focus(), 100);
}

async function submitAddItem(event) {
    event.preventDefault();

    const input = document.getElementById('addItemInput');
    const value = input.value.trim();
    if (!value) return;

    try {
        if (currentAddItemType === 'vocabulary') {
            const oldIds = new Set((vocabulary || []).map(w => w.id));
            vocabulary = await addVocabularyItem(currentProjectId, value);
            const newIds = new Set(vocabulary.filter(w => !oldIds.has(w.id)).map(w => w.id));
            renderVocabulary(vocabulary, 'vocabularyList', true, newIds);
        }
    } catch (error) {
        console.error('Error adding:', error);
        alert('Error adding item');
    }

    closeAddItemModal();
    input.value = '';
}

async function removeVocabulary(wordId) {
    try {
        vocabulary = await removeVocabularyItem(currentProjectId, wordId);
        renderVocabulary(vocabulary, 'vocabularyList', true);
    } catch (error) {
        console.error('Error removing:', error);
        alert('Error removing word');
    }
}

function closeAddItemModal() {
    closeModal('addItemModal');
    document.getElementById('addItemInput').value = '';
}

//////////////////////////////////////////////////
///////////////////FILE UPLOAD////////////////////
//////////////////////////////////////////////////

const ALLOWED_FILE_TYPES = [
    'image/',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'audio/'
];
const AUDIO_EXTENSIONS = ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.webm'];
const MAX_FILE_SIZE_MB = 10;

function triggerFileUpload() {
    document.getElementById('fileInput').click();
}

function getFileType(file) {
    if (file.type.startsWith('image/')) return 'image';
    if (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')) return 'pdf';
    if (file.type.includes('wordprocessingml') || file.name.toLowerCase().endsWith('.docx')) return 'docx';
    if (file.type.startsWith('audio/') || AUDIO_EXTENSIONS.some(ext => file.name.toLowerCase().endsWith(ext))) return 'audio';
    return 'unknown';
}

function truncateFilename(name, maxLength = 15) {
    if (name.length <= maxLength) return name;
    const ext = name.split('.').pop();
    const base = name.slice(0, -(ext.length + 1));
    return base.slice(0, maxLength - ext.length - 4) + '...' + '.' + ext;
}

function addFilesToAttachments(fileList) {
    Array.from(fileList).forEach(file => {
        const isAllowed = ALLOWED_FILE_TYPES.some(type =>
            file.type.startsWith(type) || file.type === type
        );

        const isAudioByExtension = AUDIO_EXTENSIONS.some(ext => file.name.toLowerCase().endsWith(ext));
        if (!isAllowed && !file.name.toLowerCase().endsWith('.pdf') && !file.name.toLowerCase().endsWith('.docx') && !isAudioByExtension) {
            alert(`Unsupported file type: ${file.name}\nSupported: images, PDF, DOCX, audio (mp3, wav, m4a, ogg, flac)`);
            return;
        }

        if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
            alert(`File too large (max ${MAX_FILE_SIZE_MB}MB): ${file.name}`);
            return;
        }

        const reader = new FileReader();

        reader.onload = (e) => {
            attachedFiles.push({
                file: file,
                dataUrl: e.target.result,
                name: file.name,
                type: getFileType(file)
            });
            renderFilePreviews();
        };

        reader.readAsDataURL(file);
    });
}

function handleFileSelect(event) {
    addFilesToAttachments(event.target.files);
    event.target.value = '';
}

function initDragDrop() {
    const chatArea = document.querySelector('.main-chat-area');
    let dragCounter = 0;

    chatArea.addEventListener('dragenter', (e) => {
        e.preventDefault();
        dragCounter++;
        chatArea.classList.add('drag-over');
    });

    chatArea.addEventListener('dragleave', () => {
        dragCounter--;
        if (dragCounter === 0) chatArea.classList.remove('drag-over');
    });

    chatArea.addEventListener('dragover', (e) => {
        e.preventDefault();
    });

    chatArea.addEventListener('drop', (e) => {
        e.preventDefault();
        dragCounter = 0;
        chatArea.classList.remove('drag-over');
        if (e.dataTransfer.files.length) addFilesToAttachments(e.dataTransfer.files);
    });
}

function renderFilePreviews() {
    const container = document.getElementById('imagePreviewContainer');

    if (attachedFiles.length === 0) {
        container.classList.remove('has-images');
        container.innerHTML = '';
        return;
    }

    container.classList.add('has-images');
    container.innerHTML = attachedFiles.map((file, index) => {
        let preview;

        if (file.type === 'image') {
            preview = `<img src="${file.dataUrl}" alt="${escapeHtml(file.name)}">`;
        } else if (file.type === 'pdf') {
            preview = `
                <div class="file-icon pdf-icon">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                    </svg>
                    <span class="file-type-label">PDF</span>
                </div>`;
        } else if (file.type === 'audio') {
            preview = `
                <div class="file-icon audio-icon">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                        <path d="M9 18V5l12-2v13"></path>
                        <circle cx="6" cy="18" r="3"></circle>
                        <circle cx="18" cy="16" r="3"></circle>
                    </svg>
                    <span class="file-type-label">AUDIO</span>
                </div>`;
        } else {
            preview = `
                <div class="file-icon doc-icon">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                        <line x1="16" y1="13" x2="8" y2="13"></line>
                        <line x1="16" y1="17" x2="8" y2="17"></line>
                    </svg>
                    <span class="file-type-label">DOCX</span>
                </div>`;
        }

        return `
            <div class="file-preview-item" title="${escapeHtml(file.name)}">
                ${preview}
                <span class="file-name">${escapeHtml(truncateFilename(file.name))}</span>
                <button class="file-preview-remove" onclick="removeAttachedFile(${index})" title="Remove">×</button>
            </div>
        `;
    }).join('');
}

function removeAttachedFile(index) {
    attachedFiles.splice(index, 1);
    renderFilePreviews();
}

function clearAttachedFiles() {
    attachedFiles = [];
    renderFilePreviews();
}

function viewImageModal(imageUrl) {
    const modal = document.createElement('div');
    modal.className = 'image-modal active';
    modal.innerHTML = `<img src="${imageUrl}" alt="Full size image">`;
    modal.onclick = () => modal.remove();
    document.body.appendChild(modal);
}

function handlePasteFiles(event) {
    const items = event.clipboardData?.items;
    if (!items) return;

    let foundFile = false;

    for (const item of items) {
        if (item.type.startsWith('image/') || item.type === 'application/pdf') {
            foundFile = true;

            const blob = item.getAsFile();
            if (!blob) continue;

            if (blob.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
                alert(`File too large (max ${MAX_FILE_SIZE_MB}MB)`);
                continue;
            }

            const file = new File(
                [blob],
                `pasted-${item.type.startsWith('image/') ? 'image' : 'file'}-${Date.now()}.${item.type.split('/')[1]}`,
                { type: blob.type }
            );

            const reader = new FileReader();

            reader.onload = (e) => {
                attachedFiles.push({
                    file,
                    dataUrl: e.target.result,
                    name: file.name,
                    type: getFileType(file)
                });
                renderFilePreviews();
            };

            reader.readAsDataURL(file);
        }
    }

    if (foundFile) {
        event.preventDefault();
    }
}

//////////////////////////////////////////////////
///////////////////INPUT HANDLERS/////////////////
//////////////////////////////////////////////////

function handleInputKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

//////////////////////////////////////////////////
////////////////EVENT LISTENERS///////////////////
//////////////////////////////////////////////////

// Update send button style based on input content
function updateSendButton() {
    const input = document.getElementById('messageInput');
    const btn = document.getElementById('sendBtn');
    if (input && btn) {
        if (input.value.trim()) {
            btn.classList.add('has-content');
        } else {
            btn.classList.remove('has-content');
        }
    }
}

function setupEventListeners() {
    // Close menus on outside click
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.chat-item-menu')) {
            document.querySelectorAll('.menu-dropdown').forEach(menu => {
                menu.style.display = 'none';
            });
        }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeAddItemModal();
        }
    });

    // Close modals on outside click
    setupModalCloseOnOutsideClick();

    // Setup paste handler for files
    const messageInput = document.getElementById('messageInput');
    if (messageInput) {
        messageInput.addEventListener('paste', handlePasteFiles);
    }

    // Scroll-to-bottom button visibility
    const messagesArea = document.getElementById('messagesArea');
    const scrollBtn = document.getElementById('scrollToBottomBtn');
    if (messagesArea && scrollBtn) {
        messagesArea.addEventListener('scroll', () => {
            const distanceFromBottom = messagesArea.scrollHeight - messagesArea.scrollTop - messagesArea.clientHeight;
            scrollBtn.style.display = distanceFromBottom > 150 ? 'flex' : 'none';
        });
    }
}

function scrollToBottomClick() {
    const container = document.getElementById('messagesArea');
    if (container) {
        container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
    }
    const scrollBtn = document.getElementById('scrollToBottomBtn');
    if (scrollBtn) scrollBtn.style.display = 'none';
}

//////////////////////////////////////////////////
///////////////SELECTION TOOLBAR//////////////////
//////////////////////////////////////////////////

function createSelectionToolbar() {
    const toolbar = document.createElement('div');
    toolbar.id = 'selectionToolbar';

    const askBtn = document.createElement('button');
    askBtn.id = 'selectionAskAbout';
    askBtn.className = 'selection-toolbar-btn';
    askBtn.textContent = 'Ask about this';
    askBtn.addEventListener('mousedown', (e) => {
        e.preventDefault(); // prevent losing selection before we read it
        const selectedText = window.getSelection().toString().trim();
        if (!selectedText) return;
        const input = document.getElementById('messageInput');
        if (input) {
            input.value = `Tell me more about this:\n\n${selectedText}`;
            autoResize(input);
            updateSendButton();
            input.focus();
        }
        hideSelectionToolbar();
    });

    toolbar.appendChild(askBtn);
    document.body.appendChild(toolbar);
}

function hideSelectionToolbar() {
    const toolbar = document.getElementById('selectionToolbar');
    if (toolbar) toolbar.classList.remove('visible');
}

function handleTextSelection() {
    const selection = window.getSelection();
    const selectedText = selection.toString().trim();
    if (!selectedText || selection.rangeCount === 0) {
        hideSelectionToolbar();
        return;
    }

    const anchorNode = selection.anchorNode;
    const messagesArea = document.getElementById('messagesArea');
    if (!messagesArea || !messagesArea.contains(anchorNode)) {
        hideSelectionToolbar();
        return;
    }

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    const toolbar = document.getElementById('selectionToolbar');
    if (!toolbar) return;

    toolbar.classList.add('visible');
    const toolbarRect = toolbar.getBoundingClientRect();
    const top = rect.top - toolbarRect.height - 8;
    const left = rect.left + (rect.width / 2) - (toolbarRect.width / 2);

    toolbar.style.top = `${Math.max(8, top)}px`;
    toolbar.style.left = `${Math.max(8, Math.min(left, window.innerWidth - toolbarRect.width - 8))}px`;
}

function setupSelectionToolbar() {
    createSelectionToolbar();
    document.addEventListener('mouseup', handleTextSelection);
    document.addEventListener('mousedown', (e) => {
        if (!e.target.closest('#selectionToolbar')) {
            hideSelectionToolbar();
        }
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') hideSelectionToolbar();
    });
    const messagesArea = document.getElementById('messagesArea');
    if (messagesArea) {
        messagesArea.addEventListener('scroll', hideSelectionToolbar);
    }
}

// Initialize page
initChatPage();
setupSelectionToolbar();
initDragDrop();
