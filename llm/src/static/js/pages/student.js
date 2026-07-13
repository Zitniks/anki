// Student Profile Page - Topic and Vocabulary Management
// Dependencies: utils/dom.js, utils/api.js, utils/helpers.js, components/sidebar.js, components/vocabulary.js, components/topics.js

// State
let currentProjectId = null;
let vocabulary = [];
let topics = [];
let currentAddItemType = null;
let currentLevelFilter = 'all';
let currentStatusFilter = null;
let collapsedSections = { vocabulary: false };

// Get project ID from URL
const pathParts = window.location.pathname.split('/');
currentProjectId = pathParts[pathParts.length - 1];

//////////////////////////////////////////////////
///////////////////INITIALIZATION/////////////////
//////////////////////////////////////////////////

function initStudentPage() {
    loadProjectData();
    setupEventListeners();
}

//////////////////////////////////////////////////
////////////////PROJECT DATA//////////////////////
//////////////////////////////////////////////////

async function loadProjectData() {
    try {
        const data = await apiGet(`/api/v1/projects/${currentProjectId}`);

        // Initialize shared sidebar
        initSidebar(currentProjectId, {
            student_name: data.project.student_name || data.project.name,
            student_level: data.project.student_level,
            description: data.project.description,
            chats: data.chats,
        });

        // Set default level filter to student's level
        if (data.project.student_level) {
            currentLevelFilter = data.project.student_level;

            document.querySelectorAll('.level-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            const studentLevelBtn = document.querySelector(`[data-level="${data.project.student_level}"]`);
            if (studentLevelBtn) {
                studentLevelBtn.classList.add('active');
            }
        }

        if (data.project.topics) {
            topics = data.project.topics;
        }

        if (data.project.vocabulary) {
            vocabulary = data.project.vocabulary;
        }

        // Notes are now handled by sidebar popup
        if (data.project.notes) {
            const textarea = document.getElementById('notesTextarea');
            if (textarea) textarea.value = data.project.notes;
            _sidebarNotesLoaded = true;
        }

        await fullUpdate();
    } catch (error) {
        console.error('Ошибка загрузки данных проекта:', error);
        await fullUpdate();
    }
}

//////////////////////////////////////////////////
////////////////TOPICS MANAGEMENT/////////////////
//////////////////////////////////////////////////

function renderTopicsOnMainPage() {
    const grid = document.getElementById('topicsGrid');

    if (topics.length === 0) {
        return;
    }

    // Filter topics by level
    let filteredTopics = topics;
    if (currentLevelFilter !== 'all') {
        filteredTopics = filteredTopics.filter(topic => topic.level === currentLevelFilter);
    }

    // Filter topics by status
    if (currentStatusFilter) {
        filteredTopics = filteredTopics.filter(topic => topic.status === currentStatusFilter);
    }

    // Check if filtered list is empty
    if (filteredTopics.length === 0) {
        let message = 'Нет тем';
        if (currentLevelFilter !== 'all' && currentStatusFilter) {
            message = `Нет тем уровня ${currentLevelFilter} со статусом ${getStatusName(currentStatusFilter)}`;
        } else if (currentLevelFilter !== 'all') {
            message = `Нет тем уровня ${currentLevelFilter}`;
        } else if (currentStatusFilter) {
            message = `Нет тем со статусом ${getStatusName(currentStatusFilter)}`;
        }

        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">
                    <svg width="48" height="48" fill="none" viewBox="0 0 48 48">
                        <rect x="6" y="10" width="36" height="28" rx="4" stroke="currentColor" stroke-width="1.5" opacity="0.5"/>
                        <path d="M6 18h36" stroke="currentColor" stroke-width="1.5" opacity="0.3"/>
                        <path d="M16 26h16M16 32h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity="0.35"/>
                        <circle cx="38" cy="34" r="8" fill="var(--bg-primary)" stroke="currentColor" stroke-width="1.5" opacity="0.5"/>
                        <path d="M35.5 34h5M38 31.5v5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
                    </svg>
                </div>
                <div class="empty-state-text">${message}</div>
                <div class="empty-state-hint">Нажмите «Добавить тему» чтобы начать</div>
            </div>
        `;
        return;
    }

    // Sort by updated_at if it exists, otherwise fall back to created_at
    filteredTopics.sort((a, b) => {
        const dateA = a.extracted_at ?? a.created_at;
        const dateB = b.extracted_at ?? b.created_at;
        return new Date(dateB) - new Date(dateA);
    });

    grid.innerHTML = filteredTopics.map(topic => `
        <div class="topic-card ${topic.status}" data-id="${topic.id}">
            <div class="topic-header">
                <div class="topic-level">${topic.level}</div>
                <button class="btn-delete-topic" onclick="deleteTopic(${topic.id})" title="Удалить">
                    <svg width="14" height="14" fill="none" viewBox="0 0 16 16"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
                </button>
            </div>
            <div class="topic-name">${topic.topic}</div>
            <div class="topic-actions">
                <button class="status-btn DONE" onclick="changeStatus(${topic.id}, 'DONE')" title="Пройдено">
                    ✓
                </button>
                <button class="status-btn REPEAT" onclick="changeStatus(${topic.id}, 'REPEAT')" title="Повторить">
                    ↻
                </button>
                <button class="status-btn KNOWN" onclick="changeStatus(${topic.id}, 'KNOWN')" title="Уже знает">
                    ★
                </button>
                <button class="status-btn NOT_STARTED" onclick="changeStatus(${topic.id}, 'NOT_STARTED')" title="Не пройдено">
                    ○
                </button>
            </div>
        </div>
    `).join('');
}

function getStatusName(status) {
    const statusNames = {
        'DONE': 'Пройдено',
        'REPEAT': 'Повторить',
        'KNOWN': 'Знает',
        'NOT_STARTED': 'Не начата'
    };
    return statusNames[status] || status;
}

function filterByLevel(level) {
    currentLevelFilter = level;

    document.querySelectorAll('.level-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-level="${level}"]`).classList.add('active');

    renderTopicsOnMainPage();
}

function filterByStatus(status) {
    if (currentStatusFilter === status) {
        currentStatusFilter = null;
        document.querySelectorAll('.stat-card, .sidebar-stat-item').forEach(card => {
            card.classList.remove('active');
        });
    } else {
        currentStatusFilter = status;
        document.querySelectorAll('.stat-card, .sidebar-stat-item').forEach(card => {
            card.classList.remove('active');
        });
        const statCard = document.querySelector(`[data-status="${status}"]`);
        if (statCard) {
            statCard.classList.add('active', status);
        }
    }

    renderTopicsOnMainPage();
}

function updateStats() {
    const completed = topics.filter(t => t.status === 'DONE').length;
    const review = topics.filter(t => t.status === 'REPEAT').length;
    const known = topics.filter(t => t.status === 'KNOWN').length;
    const notStarted = topics.filter(t => t.status === 'NOT_STARTED').length;

    if (completed) {
        document.getElementById('completedCount').textContent = completed;
    }

    if (review) {
        document.getElementById('reviewCount').textContent = review;
    }

    if (known) {
        document.getElementById('knownCount').textContent = known;
    }

    if (notStarted) {
        document.getElementById('notStartedCount').textContent = notStarted;
    }
}

async function changeStatus(topicId, newStatus) {
    const topic = topics.find(t => t.id === topicId);

    const topicData = {
        topic: topic.topic,
        status: newStatus,
        level: topic.level,
        color: "gray"
    };

    if (topic) {
        await updateTopicItem(currentProjectId, topicId, topicData);
        await fullUpdate();
    }
}

async function deleteTopic(topicId) {
    if (confirm('Удалить эту тему?')) {
        topics = topics.filter(t => t.id !== topicId);

        try {
            topics = await removeTopicItem(currentProjectId, topicId);
            await fullUpdate();
        } catch (error) {
            console.error('Ошибка удаления:', error);
            alert('Error removing topic');
        }
    }
}

async function addTopicOnMainPage(event) {
    event.preventDefault();

    const name = document.getElementById('topicNameInput').value.trim();
    const level = document.getElementById('topicLevelInput').value.trim();

    if (name) {
        const newTopic = {
            topic: name,
            level: level,
            status: 'NOT_STARTED',
            color: 'gray'
        };

        topics = await addTopicItem(currentProjectId, newTopic);

        closeAddTopicModal();
        await fullUpdate();
    }
}

//////////////////////////////////////////////////
////////VOCABULARY AND TOPICS IN SIDEBAR/////////
//////////////////////////////////////////////////

function addVocabulary() {
    openModal('addVocabularyModal');
    setTimeout(() => document.getElementById('addVocabularyInput').focus(), 100);
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
        console.error('Ошибка добавления:', error);
        alert('Error adding word');
    }

    closeAddVocabularyModal();
    input.value = '';
}

async function refreshVocabularyAndTopics() {
    if (!currentProjectId) return;

    try {
        vocabulary = await refreshVocabulary(currentProjectId);
        renderVocabulary(vocabulary, 'vocabularyList', true);

        topics = await refreshTopics(currentProjectId);
    } catch (error) {
        console.error('Ошибка обновления vocabulary/topics:', error);
    }
}

async function removeVocabulary(wordId) {
    try {
        vocabulary = await removeVocabularyItem(currentProjectId, wordId);
        renderVocabulary(vocabulary, 'vocabularyList', true);
    } catch (error) {
        console.error('Ошибка удаления:', error);
        alert('Error removing word');
    }
}

async function removeTopic(topicId) {
    try {
        topics = await removeTopicItem(currentProjectId, topicId);

        await fullUpdate();
    } catch (error) {
        console.error('Ошибка удаления:', error);
        alert('Error removing topic');
    }
}

//////////////////////////////////////////////////
/////////////////////MODALS///////////////////////
//////////////////////////////////////////////////

function openAddTopicModal() {
    openModal('addTopicModal');
    document.getElementById('topicNameInput').focus();
}

function closeAddTopicModal() {
    closeModal('addTopicModal');
    document.getElementById('topicNameInput').value = '';
}

function closeAddVocabularyModal() {
    closeModal('addVocabularyModal');
    document.getElementById('addVocabularyInput').value = '';
}

//////////////////////////////////////////////////
////////////////HELPER FUNCTIONS//////////////////
//////////////////////////////////////////////////

async function fullUpdate() {
    await refreshVocabularyAndTopics();
    renderTopicsOnMainPage();
    renderVocabulary(vocabulary, 'vocabularyList', true);
    updateStats();
}

//////////////////////////////////////////////////
////////////////EVENT LISTENERS///////////////////
//////////////////////////////////////////////////

function setupEventListeners() {
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            const btn = document.getElementById('saveNotesBtn');
            if (btn && btn.classList.contains('visible')) {
                saveNotesFromSidebar();
            }
        }

        if (e.key === 'Escape') {
            closeAddTopicModal();
            closeAddVocabularyModal();
            closeNotesPopup();
        }
    });
}

// Initialize page
initStudentPage();
