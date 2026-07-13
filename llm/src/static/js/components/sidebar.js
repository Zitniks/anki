/**
 * Sidebar Component
 * Handles left and right sidebar toggle, navigation, chat list, notes popup
 */

// Sidebar state
let _sidebarProjectId = null;
let _sidebarChats = [];
let _sidebarNotesLoaded = false;

//////////////////////////////////////////////////
///////////////// CORE TOGGLES ///////////////////
//////////////////////////////////////////////////

async function logout() {
    await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'same-origin' });
    window.location.href = '/login';
}

function toggleLeftSidebar() {
    const sidebar = document.getElementById('leftSidebar');
    if (sidebar) {
        sidebar.classList.toggle('collapsed');
    }
}

function toggleRightSidebar() {
    const sidebar = document.getElementById('rightSidebar');
    if (sidebar) {
        sidebar.classList.toggle('collapsed');
    }
}

/**
 * Toggle collapsible section (vocabulary, topics, etc.)
 */
function toggleSection(sectionName, collapsedSections) {
    if (!collapsedSections) {
        console.error('collapsedSections object not provided');
        return;
    }

    collapsedSections[sectionName] = !collapsedSections[sectionName];

    const list = document.getElementById(`${sectionName}List`);
    if (list) {
        if (collapsedSections[sectionName]) {
            list.classList.add('collapsed');
        } else {
            list.classList.remove('collapsed');
        }
    }
}

//////////////////////////////////////////////////
/////////////// SIDEBAR INIT /////////////////////
//////////////////////////////////////////////////

function getSidebarProjectId() {
    return _sidebarProjectId;
}

/**
 * Initialize the shared sidebar. Call from each page's init function.
 * @param {string} projectId
 * @param {object} [projectData] - optional pre-loaded project data {student_name, student_level, chats}
 */
function toggleSidebarNav() {
    const collapse = document.getElementById('sidebarNavCollapse');
    const info = document.getElementById('sidebarStudentInfo');
    if (!collapse) return;
    const isOpen = collapse.classList.toggle('open');
    if (info) info.classList.toggle('nav-open', isOpen);
    localStorage.setItem('sidebarNavOpen', isOpen ? '1' : '0');
}

function _restoreSidebarNavState() {
    const saved = localStorage.getItem('sidebarNavOpen');
    if (saved === '1') {
        const collapse = document.getElementById('sidebarNavCollapse');
        const info = document.getElementById('sidebarStudentInfo');
        if (collapse) collapse.classList.add('open');
        if (info) info.classList.add('nav-open');
    }
}

async function initSidebar(projectId, projectData) {
    _sidebarProjectId = projectId;
    _restoreSidebarNavState();
    highlightActiveNav();

    if (projectData) {
        _updateStudentCard(projectData.student_name, projectData.student_level, projectData.description);
        if (projectData.chats) {
            _sidebarChats = projectData.chats;
            renderSidebarChats();
        }
    } else {
        await _loadSidebarData();
    }
}

async function _loadSidebarData() {
    try {
        const data = await apiGet(`/api/v1/projects/${_sidebarProjectId}`);
        _updateStudentCard(data.project.student_name || data.project.name, data.project.student_level, data.project.description);
        _sidebarChats = data.chats || [];
        renderSidebarChats();
    } catch (error) {
        console.error('Error loading sidebar data:', error);
    }
}

function _updateStudentCard(name, level, description) {
    const nameEl = document.getElementById('sidebarStudentName');
    const levelEl = document.getElementById('sidebarStudentLevel');
    const descEl = document.getElementById('sidebarStudentDescription');
    const avatarEl = document.getElementById('sidebarStudentAvatar');

    if (nameEl) nameEl.textContent = name || '';
    if (levelEl) levelEl.textContent = level || '';
    if (descEl) descEl.textContent = description || '';

    // Generate avatar initials
    if (avatarEl && name) {
        const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toLowerCase();
        avatarEl.textContent = initials;
    }
}

//////////////////////////////////////////////////
/////////////// NAVIGATION ///////////////////////
//////////////////////////////////////////////////

function highlightActiveNav() {
    const path = window.location.pathname;
    let activeNav = 'chat';

    if (path.startsWith('/student/')) {
        activeNav = 'topics';
    } else if (path.startsWith('/lesson/')) {
        activeNav = 'lesson';
    } else if (path.startsWith('/repeat/')) {
        activeNav = 'repeat';
    } else if (path.startsWith('/calendar')) {
        activeNav = 'calendar';
    } else if (path.startsWith('/materials')) {
        activeNav = 'materials';
    } else if (path.startsWith('/attachments')) {
        activeNav = 'attachments';
    }

    document.querySelectorAll('.sidebar-nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.nav === activeNav);
    });
}

function goToChat() {
    if (_sidebarProjectId) {
        window.location.href = `/${_sidebarProjectId}`;
    }
}

//////////////////////////////////////////////////
/////////////// SIDEBAR CHATS ////////////////////
//////////////////////////////////////////////////

function renderSidebarChats() {
    const container = document.getElementById('sidebarChatsList');
    if (!container) return;

    _sidebarChats.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));

    if (_sidebarChats.length === 0) {
        container.innerHTML = '<div class="sidebar-chat-empty">No chats</div>';
        return;
    }

    // Determine current chat ID if on chat page
    const activeChatId = typeof currentChatId !== 'undefined' ? currentChatId : null;
    // Show context menus only on chat page
    const onChatPage = typeof selectChat === 'function';

    container.innerHTML = _sidebarChats.map(chat => `
        <div class="sidebar-chat-item ${chat.id === activeChatId ? 'active' : ''}"
             onclick="navigateToChat('${chat.id}')">
            <span class="sidebar-chat-name">${escapeHtml(chat.name)}</span>
            ${onChatPage ? `
                <div class="sidebar-chat-menu">
                    <button class="sidebar-chat-menu-btn"
                            onclick="event.stopPropagation(); toggleSidebarChatMenu('${chat.id}')">&#8942;</button>
                    <div class="sidebar-chat-dropdown" id="sidebar-chat-menu-${chat.id}">
                        <div class="sidebar-chat-dropdown-item" onclick="event.stopPropagation(); renameChat('${chat.id}')">Rename</div>
                        <div class="sidebar-chat-dropdown-item danger" onclick="event.stopPropagation(); deleteChat('${chat.id}')">Delete</div>
                    </div>
                </div>
            ` : ''}
        </div>
    `).join('');
}

function toggleSidebarChatMenu(chatId) {
    // Close all other menus first
    document.querySelectorAll('.sidebar-chat-dropdown.open').forEach(el => {
        el.classList.remove('open');
    });
    const menu = document.getElementById(`sidebar-chat-menu-${chatId}`);
    if (menu) menu.classList.toggle('open');
}

// Close chat menus on outside click
document.addEventListener('click', (e) => {
    if (!e.target.closest('.sidebar-chat-menu')) {
        document.querySelectorAll('.sidebar-chat-dropdown.open').forEach(el => {
            el.classList.remove('open');
        });
    }
});

function navigateToChat(chatId) {
    // On the chat page, selectChat owns the URL sync (?chat=<uuid>).
    if (typeof selectChat === 'function' && window.location.pathname === `/${_sidebarProjectId}`) {
        selectChat(chatId);
        renderSidebarChats();
        return;
    }
    // Otherwise full-page nav using the same convention.
    window.location.href = `/${_sidebarProjectId}?chat=${chatId}`;
}

function toggleChatsSection() {
    const list = document.getElementById('sidebarChatsList');
    const chevron = document.getElementById('chatsSectionChevron');
    if (!list) return;

    const isCollapsed = list.classList.toggle('collapsed');
    if (chevron) {
        chevron.style.transform = isCollapsed ? 'rotate(90deg)' : 'rotate(0deg)';
    }
}

async function createNewChatFromSidebar() {
    // If on chat page, use the page's createNewChat
    if (typeof createNewChat === 'function') {
        await createNewChat();
        return;
    }

    try {
        const data = await apiPost(`/api/v1/projects/${_sidebarProjectId}/chats`, { name: 'Untitled' });
        window.location.href = `/${_sidebarProjectId}?chat=${data.chat.id}`;
    } catch (error) {
        console.error('Error creating chat:', error);
    }
}

//////////////////////////////////////////////////
///////////////// NOTES POPUP ////////////////////
//////////////////////////////////////////////////

async function openNotesPopup() {
    const modal = document.getElementById('notesModal');
    if (!modal) return;

    modal.classList.add('active');

    if (!_sidebarNotesLoaded) {
        try {
            const data = await apiGet(`/api/v1/projects/${_sidebarProjectId}`);
            const textarea = document.getElementById('notesTextarea');
            if (textarea && data.project.notes) {
                textarea.value = data.project.notes;
            }
            _sidebarNotesLoaded = true;
        } catch (error) {
            console.error('Error loading notes:', error);
        }
    }
}

function closeNotesPopup() {
    const modal = document.getElementById('notesModal');
    if (modal) modal.classList.remove('active');
}

function onNotesInput() {
    const btn = document.getElementById('saveNotesBtn');
    if (btn) btn.classList.add('visible');
}

async function saveNotesFromSidebar() {
    const notes = document.getElementById('notesTextarea').value;

    try {
        await apiPost(`/api/v1/projects/${_sidebarProjectId}/notes`, { notes });
        const btn = document.getElementById('saveNotesBtn');
        btn.classList.remove('visible');
        btn.textContent = 'Saved';
        setTimeout(() => { btn.textContent = 'Save'; }, 2000);
    } catch (error) {
        console.error('Error saving notes:', error);
    }
}

//////////////////////////////////////////////////
///////////////// THEME TOGGLE ///////////////////
//////////////////////////////////////////////////

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

function initTheme() {
    const saved = localStorage.getItem('theme') || 'dark';
    if (saved === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    }
    updateThemeIcon(saved);
}

initTheme();
