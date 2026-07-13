// Lesson Page - Lesson Management
// Dependencies: utils/dom.js, utils/api.js, utils/helpers.js, components/sidebar.js, components/vocabulary.js, components/topics.js

// State
let currentProjectId = null;
let lessons = [];
let vocabulary = [];
let currentAddItemType = null;
let currentEditingLessonId = null;
let lessonDatePicker = null;
let collapsedSections = { vocabulary: false };

// Get project ID from URL
const pathParts = window.location.pathname.split('/');
currentProjectId = pathParts[pathParts.length - 1];

//////////////////////////////////////////////////
///////////////////INITIALIZATION/////////////////
//////////////////////////////////////////////////

function initLessonPage() {
    getLessons();
    loadVocabulary();
    loadProjectData();
    setupEventListeners();
    initRichTextEditor();
}

//////////////////////////////////////////////////
////////////////////LESSONS///////////////////////
//////////////////////////////////////////////////

async function getLessons() {
    try {
        const data = await apiGet(`/api/v1/lessons?project_id=${currentProjectId}`);
        lessons = data.lessons;
        renderLessons();
    } catch (error) {
        console.error('Ошибка загрузки занятий:', error);
        lessons = [];
        renderLessons();
    }

    // Bind ?lesson=<int> to the view modal. onOpen guards against missing ids
    // so a stale URL doesn't pop an empty modal.
    registerModalUrl({
        key: 'lesson',
        idType: 'int',
        onOpen: (id) => {
            if (lessons.some(l => l.id === id)) {
                viewLesson(id);
            }
        },
        onClose: closeViewLessonModal,
    });
}

async function loadVocabulary() {
    try {
        vocabulary = await refreshVocabulary(currentProjectId);
        renderVocabulary(vocabulary, 'vocabularyList', false);
    } catch (error) {
        console.error('Ошибка загрузки vocabulary:', error);
    }
}

function renderLessons() {
    const container = document.getElementById('lessonsRowsContainer');

    if (lessons.length === 0) {
        container.innerHTML = `
            <div class="lesson-row" style="cursor: default;">
                <div class="lesson-row-content" style="text-align: center; color: var(--text-tertiary); font-style: italic;">
                    Занятий пока нет. Добавьте первое занятие!
                </div>
            </div>
        `;
        return;
    }

    // Sort lessons by date (newest first)
    const sortedLessons = [...lessons].sort((a, b) =>
        new Date(b.date) - new Date(a.date)
    );

    container.innerHTML = sortedLessons.map((lesson, index) => `
        <div class="lesson-row" onclick="openModalUrl('lesson', ${lesson.id})" style="animation-delay: ${index * 0.03}s">
            <div class="lesson-row-date">${formatDate(lesson.date)}</div>
            <div class="lesson-row-content">
                ${renderLessonContent(lesson.description)}
            </div>
            <button class="btn-delete-lesson" onclick="event.stopPropagation(); deleteLesson(${lesson.id})" title="Удалить">
                🗑️
            </button>
        </div>
    `).join('');
}

function viewLesson(lessonId) {
    const lesson = lessons.find(l => l.id === lessonId);
    if (!lesson) return;

    currentEditingLessonId = lessonId;

    // Create and show view modal
    const viewModal = document.createElement('div');
    viewModal.id = 'viewLessonModal';
    viewModal.className = 'modal active';
    viewModal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3>${formatDate(lesson.date)}</h3>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <button class="btn-secondary" onclick="editLesson(${lessonId})" style="padding: 8px 16px; display: flex; align-items: center; gap: 6px;">
                        <span>✏️</span> Редактировать
                    </button>
                    <button class="btn-secondary" onclick="deleteLessonFromModal(${lessonId})" style="padding: 8px 16px; background: var(--red); border-color: var(--red); display: flex; align-items: center; gap: 6px;">
                        <span>🗑️</span> Удалить
                    </button>
                    <button class="btn-close" onclick="closeModalUrl('lesson')">×</button>
                </div>
            </div>
            <div class="lesson-view-content">
                ${lesson.description}
            </div>
        </div>
    `;

    document.body.appendChild(viewModal);
}

async function deleteLessonFromModal(lessonId) {
    closeModalUrl('lesson');
    await deleteLesson(lessonId);
}

function closeViewLessonModal() {
    const modal = document.getElementById('viewLessonModal');
    if (modal) {
        modal.remove();
    }
    currentEditingLessonId = null;
}

function editLesson(lessonId) {
    const lesson = lessons.find(l => l.id === lessonId);
    if (!lesson) return;

    // Close view modal if open
    closeModalUrl('lesson');

    currentEditingLessonId = lessonId;

    // Set the date
    lessonDatePicker.setDate(lesson.date.split('T')[0], true);

    // Set the content
    const editor = document.getElementById('lessonContentInput');
    editor.innerHTML = lesson.description;
    updatePlaceholder(editor);

    // Change modal title
    const modalHeader = document.querySelector('#addLessonModal .modal-header span');
    if (modalHeader) {
        modalHeader.textContent = 'Редактировать занятие';
    }

    // Show modal
    openModal('addLessonModal');
    editor.focus();
}

function isSameDay(d1, d2) {
    const date1 = new Date(d1);
    const date2 = new Date(d2);
    return date1.getFullYear() === date2.getFullYear() &&
        date1.getMonth() === date2.getMonth() &&
        date1.getDate() === date2.getDate();
}

async function syncDescriptionToCalendar(date, description) {
    try {
        const data = await apiGet(`/api/v1/calendar-events?project_id=${currentProjectId}`);
        const matchingEvent = data.events.find(e => isSameDay(e.start_time, date));
        if (!matchingEvent) {
            console.log('No calendar event found for this date, skipping calendar sync');
            return;
        }
        await apiPatch(`/api/v1/calendar-events/${matchingEvent.id}`, {
            project_id: matchingEvent.project_id,
            start_time: matchingEvent.start_time,
            end_time: matchingEvent.end_time,
            notes: description,
            color: matchingEvent.color,
            is_recurring: matchingEvent.is_recurring,
            recurrence_type: matchingEvent.recurrence_type,
            recurrence_group_id: matchingEvent.recurrence_group_id
        });
    } catch (error) {
        console.error('Ошибка синхронизации с календарём:', error);
    }
}

async function addLesson(event) {
    event.preventDefault();

    const date = document.getElementById('lessonDateInput').value;
    const editor = document.getElementById('lessonContentInput');

    // Clean up editor content before getting HTML
    validateEditorContent();

    // Get HTML content, but clean it up
    let description = editor.innerHTML.trim();

    // Remove empty paragraphs and br tags at the end
    description = description.replace(/^(<br\s*\/?>|\s)*/i, '');
    description = description.replace(/(<br\s*\/?>|\s)*$/i, '');

    // Check if editor has actual content
    const textContent = editor.textContent.trim();
    if (!date || !textContent) {
        if (!textContent) {
            alert('Пожалуйста, введите описание занятия');
            editor.focus();
        }
        return;
    }

    try {
        if (currentEditingLessonId) {
            // Update existing lesson
            const data = await apiPatch(`/api/v1/lessons/${currentEditingLessonId}`, {
                project_id: currentProjectId,
                date: date,
                description: description
            });
            const index = lessons.findIndex(l => l.id === currentEditingLessonId);
            if (index !== -1) {
                lessons[index] = data.lesson;
            }
            await syncDescriptionToCalendar(date, description);
            renderLessons();
            closeAddLessonModal();
        } else {
            // Create new lesson
            const data = await apiPost(`/api/v1/lessons/`, {
                project_id: currentProjectId,
                date: date,
                description: description
            });
            lessons.push(data.lesson);
            await syncDescriptionToCalendar(date, description);
            renderLessons();
            closeAddLessonModal();
        }
    } catch (error) {
        console.error('Ошибка сохранения занятия:', error);
        alert('Ошибка сохранения занятия');
    }
}

async function deleteLesson(lessonId) {
    if (confirm('Удалить это занятие?')) {
        try {
            await apiDelete(`/api/v1/lessons/${lessonId}`);
            await getLessons();
        } catch (error) {
            console.error('Ошибка удаления занятия:', error);
            alert('Ошибка удаления занятия');
        }
    }
}

function renderLessonContent(content) {
    return content;
}

//////////////////////////////////////////////////
////////////////RICH TEXT EDITOR//////////////////
//////////////////////////////////////////////////

function formatText(command, value = null) {
    const editor = document.getElementById('lessonContentInput');
    editor.focus();

    const selection = window.getSelection();
    if (selection.rangeCount === 0) {
        const range = document.createRange();
        range.selectNodeContents(editor);
        selection.removeAllRanges();
        selection.addRange(range);
        return;
    }

    if (command === 'removeFormat') {
        document.execCommand('removeFormat', false, null);
        document.execCommand('removeFormat', false, 'span');
        const range = selection.getRangeAt(0);
        if (!range.collapsed) {
            const selectedContent = range.extractContents();
            const textNode = document.createTextNode(selectedContent.textContent);
            range.insertNode(textNode);
            selection.removeAllRanges();
            const newRange = document.createRange();
            newRange.setStartAfter(textNode);
            newRange.collapse(true);
            selection.addRange(newRange);
        }
        return;
    }

    if (command === 'highlight' && value) {
        const range = selection.getRangeAt(0);
        if (range.collapsed) return;

        const selectedText = range.toString();
        if (!selectedText.trim()) return;

        let parentSpan = range.commonAncestorContainer;
        if (parentSpan.nodeType !== Node.ELEMENT_NODE) {
            parentSpan = parentSpan.parentElement;
        }
        while (parentSpan && parentSpan !== editor) {
            if (parentSpan.classList) {
                const hasHighlight = Array.from(parentSpan.classList).some(cls => cls.startsWith('highlight-'));
                if (hasHighlight) {
                    if (parentSpan.classList.contains('highlight-' + value)) {
                        const text = parentSpan.textContent;
                        parentSpan.outerHTML = text;
                        return;
                    } else {
                        break;
                    }
                }
            }
            parentSpan = parentSpan.parentElement;
        }

        const span = document.createElement('span');
        span.className = `highlight-${value}`;

        const contents = range.extractContents();
        span.appendChild(contents);
        range.insertNode(span);

        selection.removeAllRanges();
        const newRange = document.createRange();
        newRange.setStartAfter(span);
        newRange.collapse(true);
        selection.addRange(newRange);
    } else {
        document.execCommand(command, false, value);
    }

    validateEditorContent();
}

function validateEditorContent() {
    const editor = document.getElementById('lessonContentInput');
    const emptyTags = editor.querySelectorAll('span:empty, strong:empty, em:empty, u:empty, b:empty, i:empty');
    emptyTags.forEach(tag => {
        const parent = tag.parentNode;
        if (parent) {
            parent.removeChild(tag);
            parent.normalize();
        }
    });

    if (editor.innerHTML.trim() === '' || editor.innerHTML === '<br>') {
        editor.innerHTML = '';
    }

    updatePlaceholder(editor);
}

function updatePlaceholder(editor) {
    const hasContent = editor.textContent.trim().length > 0;
    if (hasContent) {
        editor.removeAttribute('data-placeholder');
    } else {
        editor.setAttribute('data-placeholder', editor.getAttribute('placeholder') || 'Что изучали на занятии...');
    }
}

//////////////////////////////////////////////////
/////////////////////MODALS///////////////////////
//////////////////////////////////////////////////

function openAddLessonModal() {
    openModal('addLessonModal');
    const today = new Date().toISOString().split('T')[0];
    lessonDatePicker.setDate(today, true);
    const editor = document.getElementById('lessonContentInput');
    editor.innerHTML = '';
    updatePlaceholder(editor);
    editor.focus();
}

function closeAddLessonModal() {
    closeModal('addLessonModal');
    lessonDatePicker.clear();
    const editor = document.getElementById('lessonContentInput');
    editor.innerHTML = '';
    updatePlaceholder(editor);

    currentEditingLessonId = null;

    const modalHeader = document.querySelector('#addLessonModal .modal-header span');
    if (modalHeader) {
        modalHeader.textContent = 'Добавить новое занятие';
    }
}

function addVocabulary() {
    currentAddItemType = 'vocabulary';
    document.getElementById('addItemTitle').textContent = 'Add Word';
    document.getElementById('addItemInput').placeholder = 'Enter word or phrase...';
    document.getElementById('addItemInput').value = '';
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
            vocabulary = await addVocabularyItem(currentProjectId, value);
            renderVocabulary(vocabulary, 'vocabularyList', false);
            closeAddItemModal();
        }
    } catch (error) {
        console.error('Ошибка добавления элемента:', error);
        alert('Ошибка добавления элемента');
    }
}

function closeAddItemModal() {
    closeModal('addItemModal');
    document.getElementById('addItemInput').value = '';
    currentAddItemType = null;
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

        if (data.project.vocabulary) {
            vocabulary = data.project.vocabulary;
        }

        // Pre-load notes into sidebar popup
        if (data.project.notes) {
            const textarea = document.getElementById('notesTextarea');
            if (textarea) textarea.value = data.project.notes;
            _sidebarNotesLoaded = true;
        }
    } catch (error) {
        console.error('Ошибка загрузки данных проекта:', error);
    }
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
            closeAddLessonModal();
            closeNotesPopup();
        }

        // Rich text editor shortcuts
        const editor = document.getElementById('lessonContentInput');
        if (editor && document.activeElement === editor) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
                e.preventDefault();
                formatText('bold');
            } else if ((e.ctrlKey || e.metaKey) && e.key === 'i') {
                e.preventDefault();
                formatText('italic');
            } else if ((e.ctrlKey || e.metaKey) && e.key === 'u') {
                e.preventDefault();
                formatText('underline');
            }
        }
    });

    // Close view lesson modal on click outside
    document.addEventListener('click', (e) => {
        if (e.target.id === 'viewLessonModal') {
            closeModalUrl('lesson');
        }
    });
}

function initRichTextEditor() {
    const editor = document.getElementById('lessonContentInput');
    if (editor) {
        editor.addEventListener('input', () => {
            updatePlaceholder(editor);
        });
        editor.addEventListener('blur', () => {
            updatePlaceholder(editor);
        });
        editor.addEventListener('focus', () => {
            updatePlaceholder(editor);
        });
        updatePlaceholder(editor);
    }
}

// Initialize page
lessonDatePicker = flatpickr("#lessonDateInput", {
    dateFormat: "Y-m-d",
    disableMobile: true,
    locale: { firstDayOfWeek: 1 }
});

initLessonPage();
