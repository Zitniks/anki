// Calendar Page - Google Calendar-like View
// Dependencies: utils/dom.js, utils/api.js, utils/helpers.js, components/modal.js

//////////////////////////////////////////////////
////////////////////// STATE /////////////////////
//////////////////////////////////////////////////

let currentView = 'week';
let currentDate = new Date();
let calendarLessons = [];
let students = []; // Projects (students) from API
let nowLineInterval = null;
let bookDatePicker = null;
let bookTimePicker = null;

let dragState = null;       // drag-to-create state
let rescheduleState = null; // drag-to-reschedule state
let _dragMoveHandler = null;
let _dragUpHandler = null;

const START_HOUR = 7;
const END_HOUR = 22;
const HOUR_HEIGHT = 60;

const repeatConfig = { k: 3 };

//////////////////////////////////////////////////
///////////////// API DATA LOADING ////////////////
//////////////////////////////////////////////////

const CALENDAR_COLORS = ['blue', 'green', 'pink'];

// Transform backend event to frontend lesson format
function eventToLesson(event, studentsMap) {
    const student = studentsMap[event.project_id];
    const startTime = new Date(event.start_time);
    const endTime = new Date(event.end_time);
    const duration = Math.round((endTime - startTime) / 60000); // milliseconds to minutes

    return {
        id: event.id,
        studentId: event.project_id,
        studentName: student ? student.student_name : 'Unknown',
        color: event.color || 'blue',
        date: startTime,
        startHour: startTime.getHours(),
        startMinute: startTime.getMinutes(),
        duration: duration,
        notes: event.notes || '',
        isRecurring: event.is_recurring || false,
        recurrenceType: event.recurrence_type || 'none',
        recurrenceGroupId: event.recurrence_group_id || null,
        isRepeatLesson: false, // Will be computed by applyRepeatLabels
    };
}

// Helper: Format datetime as ISO string without timezone (for naive datetime columns)
function toLocalISOString(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
}

// Transform frontend lesson to backend event format
function lessonToEvent(lesson) {
    const startTime = new Date(lesson.date);
    const endTime = new Date(startTime);
    endTime.setMinutes(endTime.getMinutes() + lesson.duration);

    return {
        project_id: lesson.studentId,
        start_time: toLocalISOString(startTime),
        end_time: toLocalISOString(endTime),
        notes: lesson.notes || '',
        color: lesson.color || 'blue',
        is_recurring: lesson.isRecurring || false,
        recurrence_type: lesson.recurrenceType !== 'none' ? lesson.recurrenceType : null,
        recurrence_group_id: lesson.recurrenceGroupId || null,
    };
}

// Load students (projects) from API
async function loadStudents() {
    try {
        const response = await apiGet('/api/v1/projects/');
        students = response.projects || [];
        console.log('Loaded students:', students.length);
    } catch (error) {
        console.error('Failed to load students:', error);
        students = [];
    }
}

// Load lessons (calendar events) from API
async function loadLessons() {
    try {
        const response = await apiGet('/api/v1/calendar-events');
        const events = response.events || [];

        // Create students map for quick lookup
        const studentsMap = {};
        students.forEach(s => studentsMap[s.id] = s);

        // Transform backend events to frontend lessons
        calendarLessons = events.map(event => eventToLesson(event, studentsMap));

        console.log('Loaded lessons:', calendarLessons.length);
    } catch (error) {
        console.error('Failed to load lessons:', error);
        calendarLessons = [];
    }

    // Bind ?event=<int> to the lesson-detail modal. Registered after data
    // is in memory so the initial sweep can resolve the id against
    // calendarLessons. Idempotent: re-registering replaces the prior entry.
    registerModalUrl({
        key: 'event',
        idType: 'int',
        onOpen: openLessonDetail,
        onClose: closeLessonDetailModal,
    });
}

//////////////////////////////////////////////////
///////////////// REPEAT LABELS //////////////////
//////////////////////////////////////////////////

function applyRepeatLabels(studentId) {
    const studentLessons = calendarLessons
        .filter(l => l.studentId === studentId)
        .sort((a, b) => a.date - b.date);

    studentLessons.forEach((lesson, index) => {
        lesson.isRepeatLesson = ((index + 1) % repeatConfig.k === 0);
    });
}

function applyAllRepeatLabels() {
    const studentIds = [...new Set(calendarLessons.map(l => l.studentId))];
    studentIds.forEach(id => applyRepeatLabels(id));
}

//////////////////////////////////////////////////
//////////////// INITIALIZATION //////////////////
//////////////////////////////////////////////////

async function initCalendarPage() {
    // Show loading state
    const calendarBody = document.getElementById('calendarBody');
    calendarBody.innerHTML = '<div style="display: flex; align-items: center; justify-content: center; height: 400px; color: var(--text-secondary);">Loading calendar...</div>';

    // Load data from API
    await loadStudents();
    await loadLessons();
    applyAllRepeatLabels();

    // Render calendar
    renderCalendar();
    startNowLineUpdater();
    setupCalendarEventListeners();
}

//////////////////////////////////////////////////
////////////////// NAVIGATION ////////////////////
//////////////////////////////////////////////////

function goToToday() {
    currentDate = new Date();
    renderCalendar();
}

function navigatePrev() {
    if (currentView === 'week') {
        currentDate.setDate(currentDate.getDate() - 7);
    } else {
        currentDate.setMonth(currentDate.getMonth() - 1);
    }
    renderCalendar();
}

function navigateNext() {
    if (currentView === 'week') {
        currentDate.setDate(currentDate.getDate() + 7);
    } else {
        currentDate.setMonth(currentDate.getMonth() + 1);
    }
    renderCalendar();
}

function switchView(view) {
    currentView = view;
    document.getElementById('weekViewBtn').classList.toggle('active', view === 'week');
    document.getElementById('monthViewBtn').classList.toggle('active', view === 'month');
    renderCalendar();
}

//////////////////////////////////////////////////
////////////// CALENDAR RENDERING ////////////////
//////////////////////////////////////////////////

function renderCalendar() {
    updatePeriodLabel();
    if (currentView === 'week') {
        renderWeekView();
    } else {
        renderMonthView();
    }
}

function updatePeriodLabel() {
    const periodEl = document.getElementById('currentPeriod');
    if (currentView === 'week') {
        const weekStart = getWeekStart(currentDate);
        const weekEnd = new Date(weekStart);
        weekEnd.setDate(weekEnd.getDate() + 6);
        periodEl.textContent = formatWeekRange(weekStart, weekEnd);
    } else {
        periodEl.textContent = currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    }
}

//////////////////////////////////////////////////
////////////////// WEEK VIEW /////////////////////
//////////////////////////////////////////////////

function renderWeekView() {
    const calendarBody = document.getElementById('calendarBody');
    const weekStart = getWeekStart(currentDate);
    const today = new Date();
    const totalHeight = (END_HOUR - START_HOUR) * HOUR_HEIGHT;

    let html = '';

    // Day headers row
    html += '<div class="calendar-week-header">';
    html += '<div class="calendar-time-header"></div>';
    const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    for (let i = 0; i < 7; i++) {
        const day = new Date(weekStart);
        day.setDate(day.getDate() + i);
        const isToday = isSameDay(day, today);
        html += `<div class="calendar-day-header ${isToday ? 'today' : ''}">
            <span class="day-name">${dayNames[i]}</span>
            <span class="day-number ${isToday ? 'today-number' : ''}">${day.getDate()}</span>
        </div>`;
    }
    html += '</div>';

    // Scrollable grid
    html += '<div class="calendar-grid-scroll">';
    html += `<div class="calendar-grid" style="height: ${totalHeight}px;">`;

    // Time column
    html += '<div class="calendar-time-column">';
    for (let h = START_HOUR; h <= END_HOUR; h++) {
        html += `<div class="calendar-time-label" style="top: ${(h - START_HOUR) * HOUR_HEIGHT}px">${String(h).padStart(2, '0')}:00</div>`;
    }
    html += '</div>';

    // Day columns
    for (let i = 0; i < 7; i++) {
        const day = new Date(weekStart);
        day.setDate(day.getDate() + i);
        const isToday = isSameDay(day, today);
        const dateStr = toDateString(day);
        const dayLessons = getLessonsForDay(day);

        html += `<div class="calendar-day-column ${isToday ? 'today-column' : ''}" data-date="${dateStr}">`;

        // Hour grid lines
        for (let h = START_HOUR; h <= END_HOUR; h++) {
            html += `<div class="calendar-hour-line" style="top: ${(h - START_HOUR) * HOUR_HEIGHT}px"></div>`;
        }

        // Current time line
        if (isToday) {
            const nowMinutes = today.getHours() * 60 + today.getMinutes();
            const topPx = ((nowMinutes / 60) - START_HOUR) * HOUR_HEIGHT;
            if (topPx >= 0 && topPx <= totalHeight) {
                html += `<div class="calendar-now-line" id="nowLine" style="top: ${topPx}px"></div>`;
            }
        }

        // Lesson event tiles
        dayLessons.forEach(lesson => {
            const topPx = ((lesson.startHour + lesson.startMinute / 60) - START_HOUR) * HOUR_HEIGHT;
            const heightPx = lesson.duration;
            html += renderEventTile(lesson, topPx, heightPx);
        });

        html += '</div>';
    }

    html += '</div>'; // .calendar-grid
    html += '</div>'; // .calendar-grid-scroll

    calendarBody.innerHTML = html;

    // Remove old window drag handlers before attaching new ones
    if (_dragMoveHandler) window.removeEventListener('mousemove', _dragMoveHandler);
    if (_dragUpHandler) window.removeEventListener('mouseup', _dragUpHandler);

    // Drag-to-create: mousedown on day column background
    document.querySelectorAll('.calendar-day-column').forEach(col => {
        col.addEventListener('mousedown', function (e) {
            if (e.target.closest('.calendar-event')) return;
            e.preventDefault();
            const dateStr = this.dataset.date;
            const rect = this.getBoundingClientRect();
            const y = e.clientY - rect.top;
            const startH = START_HOUR + y / HOUR_HEIGHT;
            const snappedH = Math.round(startH * 2) / 2;
            dragState = { col: this, dateStr, startH: snappedH, curH: snappedH + 1 };
        });
    });

    _dragMoveHandler = (e) => {
        if (dragState) {
            const rect = dragState.col.getBoundingClientRect();
            const y = e.clientY - rect.top;
            const h = START_HOUR + Math.max(0, Math.min(END_HOUR - START_HOUR, y / HOUR_HEIGHT));
            const snapped = Math.round(h * 2) / 2;
            dragState.curH = Math.max(dragState.startH + 0.5, snapped);

            // Update or create ghost rect
            let ghost = dragState.col.querySelector('.cal-drag-ghost');
            if (!ghost) {
                ghost = document.createElement('div');
                ghost.className = 'cal-drag-ghost';
                ghost.innerHTML = '<span class="dur-label"></span>';
                dragState.col.appendChild(ghost);
            }
            const top = (dragState.startH - START_HOUR) * HOUR_HEIGHT;
            const height = (dragState.curH - dragState.startH) * HOUR_HEIGHT;
            ghost.style.top = top + 'px';
            ghost.style.height = height + 'px';
            ghost.querySelector('.dur-label').textContent =
                Math.round((dragState.curH - dragState.startH) * 60) + ' min';
        }

        if (rescheduleState) {
            const clone = document.getElementById('cal-event-clone');
            if (clone) {
                clone.style.left = (e.clientX + 10) + 'px';
                clone.style.top = (e.clientY - rescheduleState.offsetY) + 'px';
            }

            // Show drop-target placeholder in the hovered column
            const cols = Array.from(document.querySelectorAll('.calendar-day-column'));
            const targetCol = cols.find(col => {
                const r = col.getBoundingClientRect();
                return e.clientX >= r.left && e.clientX <= r.right;
            });

            // Remove placeholder from any column it's not needed in
            cols.forEach(col => {
                if (col !== targetCol) {
                    const ph = col.querySelector('.cal-drop-placeholder');
                    if (ph) ph.remove();
                }
            });

            if (targetCol) {
                const lesson = calendarLessons.find(l => l.id === rescheduleState.lessonId);
                const colRect = targetCol.getBoundingClientRect();
                const y = e.clientY - colRect.top - rescheduleState.offsetY;
                const rawH = START_HOUR + y / HOUR_HEIGHT;
                const snappedH = Math.round(Math.max(START_HOUR, Math.min(END_HOUR - lesson.duration / 60, rawH)) * 2) / 2;
                const top = (snappedH - START_HOUR) * HOUR_HEIGHT;
                const height = (lesson.duration / 60) * HOUR_HEIGHT;

                let ph = targetCol.querySelector('.cal-drop-placeholder');
                if (!ph) {
                    ph = document.createElement('div');
                    ph.className = 'cal-drop-placeholder';
                    targetCol.appendChild(ph);
                }
                ph.style.top = top + 'px';
                ph.style.height = height + 'px';
            }
        }
    };

    _dragUpHandler = (e) => {
        if (dragState) {
            const durMins = Math.round((dragState.curH - dragState.startH) * 60);
            const ghost = dragState.col.querySelector('.cal-drag-ghost');
            if (ghost) ghost.remove();

            const startH = dragState.startH;
            const hour = Math.floor(startH);
            const minute = Math.round((startH % 1) * 60);
            const dateStr = dragState.dateStr;
            dragState = null;
            openBookLessonModal(dateStr, hour, minute, durMins);
        }

        if (rescheduleState) {
            const clone = document.getElementById('cal-event-clone');
            if (clone) clone.remove();

            const origTile = document.querySelector(`.calendar-event[data-lesson-id="${rescheduleState.lessonId}"]`);
            if (origTile) origTile.classList.remove('cal-event-dragging');

            // Read drop position from the placeholder (which already snapped to grid)
            const cols = Array.from(document.querySelectorAll('.calendar-day-column'));
            cols.forEach(col => { const ph = col.querySelector('.cal-drop-placeholder'); if (ph) ph.remove(); });

            const targetCol = cols.find(col => {
                const r = col.getBoundingClientRect();
                return e.clientX >= r.left && e.clientX <= r.right;
            });

            if (targetCol) {
                const lesson = calendarLessons.find(l => l.id === rescheduleState.lessonId);
                const colRect = targetCol.getBoundingClientRect();
                const y = e.clientY - colRect.top - rescheduleState.offsetY;
                const rawH = START_HOUR + y / HOUR_HEIGHT;
                const snappedH = Math.round(Math.max(START_HOUR, Math.min(END_HOUR - lesson.duration / 60, rawH)) * 2) / 2;
                const newDateStr = targetCol.dataset.date;

                const origDateStr = lesson ? toDateString(lesson.date) : null;
                const origH = lesson ? lesson.startHour + lesson.startMinute / 60 : null;
                const moved = newDateStr !== origDateStr || Math.abs(snappedH - origH) >= 0.25;

                if (!moved) {
                    // Treat as click
                    openModalUrl('event', rescheduleState.lessonId);
                } else {
                    finishReschedule(rescheduleState.lessonId, newDateStr, snappedH, rescheduleState.isRecurring, rescheduleState.groupId);
                }
            }
            rescheduleState = null;
        }
    };

    window.addEventListener('mousemove', _dragMoveHandler);
    window.addEventListener('mouseup', _dragUpHandler);

    // Hover preview + drag-to-reschedule on event tiles
    document.querySelectorAll('.calendar-event').forEach(el => {
        const lessonId = parseInt(el.dataset.lessonId);
        el.addEventListener('mouseenter', () => showEventPreview(lessonId, el));
        el.addEventListener('mouseleave', hideEventPreview);
        el.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            const lesson = calendarLessons.find(l => l.id === lessonId);
            if (!lesson) return;
            const rect = el.getBoundingClientRect();
            const offsetY = e.clientY - rect.top;

            rescheduleState = {
                lessonId,
                offsetY,
                isRecurring: lesson.isRecurring,
                groupId: lesson.recurrenceGroupId,
            };

            el.classList.add('cal-event-dragging');
            hideEventPreview();

            // Create floating clone
            const clone = document.createElement('div');
            clone.id = 'cal-event-clone';
            clone.className = `cal-event-clone event-color-${lesson.color}`;
            clone.style.width = rect.width + 'px';
            clone.style.height = rect.height + 'px';
            clone.style.left = (e.clientX + 10) + 'px';
            clone.style.top = (e.clientY - offsetY) + 'px';
            clone.innerHTML = el.innerHTML;
            document.body.appendChild(clone);
        });
    });

    scrollToRelevantTime();
}

function renderEventTile(lesson, topPx, heightPx) {
    const recurringIcon = lesson.isRecurring ? '<span class="recurring-icon" title="Recurring">&#x21BB;</span>' : '';
    const repeatLabel = lesson.isRepeatLesson ? '<span class="repeat-label">Repeat</span>' : '';

    return `<div class="calendar-event event-color-${lesson.color}"
                 style="top: ${topPx}px; height: ${heightPx}px;"
                 data-lesson-id="${lesson.id}"
                 title="${escapeHtml(lesson.studentName)}">
        <div class="calendar-event-title">${recurringIcon}${repeatLabel}${escapeHtml(lesson.studentName)}</div>
        <div class="calendar-event-time">${formatTime(lesson.startHour, lesson.startMinute)} – ${formatEndTime(lesson.startHour, lesson.startMinute, lesson.duration)}</div>
    </div>`;
}

//////////////////////////////////////////////////
////////////////// MONTH VIEW ////////////////////
//////////////////////////////////////////////////

function renderMonthView() {
    const calendarBody = document.getElementById('calendarBody');
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const firstDay = new Date(year, month, 1);
    const today = new Date();

    const startDate = getWeekStart(firstDay);

    let html = '<div class="calendar-month-grid">';

    // Day name headers
    const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    dayNames.forEach(name => {
        html += `<div class="calendar-month-header-cell">${name}</div>`;
    });

    // Day cells (up to 6 rows)
    const current = new Date(startDate);
    for (let row = 0; row < 6; row++) {
        for (let col = 0; col < 7; col++) {
            const isCurrentMonth = current.getMonth() === month;
            const isToday = isSameDay(current, today);
            const dayLessons = getLessonsForDay(current);
            const dateStr = toDateString(current);

            html += `<div class="calendar-month-cell ${!isCurrentMonth ? 'other-month' : ''} ${isToday ? 'today' : ''}" data-date="${dateStr}">
                <div class="calendar-month-date ${isToday ? 'today-date' : ''}">${current.getDate()}</div>
                <div class="calendar-month-events">`;

            const maxShow = 3;
            dayLessons.slice(0, maxShow).forEach(lesson => {
                const recurringIcon = lesson.isRecurring ? '&#x21BB; ' : '';
                html += `<div class="calendar-month-event event-color-${lesson.color}" data-lesson-id="${lesson.id}">
                    ${recurringIcon}${formatTime(lesson.startHour, lesson.startMinute)} ${escapeHtml(lesson.studentName)}
                </div>`;
            });

            if (dayLessons.length > maxShow) {
                html += `<div class="calendar-month-more">+${dayLessons.length - maxShow} more</div>`;
            }

            html += '</div></div>';
            current.setDate(current.getDate() + 1);
        }
        // Stop if we've gone past the month
        if (current.getMonth() > month || (current.getMonth() === 0 && month === 11)) break;
    }

    html += '</div>';
    calendarBody.innerHTML = html;

    // Attach click handlers for month events
    document.querySelectorAll('.calendar-month-event').forEach(el => {
        el.addEventListener('click', function (e) {
            e.stopPropagation();
            const lessonId = parseInt(this.dataset.lessonId);
            openModalUrl('event', lessonId);
        });
    });

    // Attach click handlers for month cells (switch to week view)
    document.querySelectorAll('.calendar-month-cell').forEach(cell => {
        cell.addEventListener('click', function (e) {
            if (e.target.closest('.calendar-month-event')) return;
            const dateStr = this.dataset.date;
            currentDate = new Date(dateStr + 'T12:00:00');
            switchView('week');
        });
    });
}

//////////////////////////////////////////////////
/////////////// CURRENT TIME LINE ////////////////
//////////////////////////////////////////////////

function startNowLineUpdater() {
    nowLineInterval = setInterval(() => {
        const nowLine = document.getElementById('nowLine');
        if (nowLine) {
            const now = new Date();
            const topPx = ((now.getHours() + now.getMinutes() / 60) - START_HOUR) * HOUR_HEIGHT;
            nowLine.style.top = topPx + 'px';
        }
    }, 60000);
}

function scrollToRelevantTime() {
    const scrollContainer = document.querySelector('.calendar-grid-scroll');
    if (!scrollContainer) return;
    const now = new Date();
    const targetHour = Math.max(START_HOUR, now.getHours() - 1);
    scrollContainer.scrollTop = (targetHour - START_HOUR) * HOUR_HEIGHT;
}

//////////////////////////////////////////////////
//////////////////// MODALS //////////////////////
//////////////////////////////////////////////////

function openLessonDetail(lessonId) {
    const lesson = calendarLessons.find(l => l.id === lessonId);
    if (!lesson) return;

    document.getElementById('lessonDetailTitle').textContent =
        `${lesson.studentName} — ${formatDate(lesson.date.toISOString())}`;

    const detailContent = document.getElementById('lessonDetailContent');
    detailContent.innerHTML = `
        <div class="lesson-detail-info">
            <div class="lesson-detail-row">
                <span class="detail-label">Student</span>
                <span class="detail-value">${escapeHtml(lesson.studentName)}</span>
            </div>
            <div class="lesson-detail-row">
                <span class="detail-label">Time</span>
                <span class="detail-value">${formatTime(lesson.startHour, lesson.startMinute)} – ${formatEndTime(lesson.startHour, lesson.startMinute, lesson.duration)} (${lesson.duration} min)</span>
            </div>
            <div class="lesson-detail-row">
                <span class="detail-label">Type</span>
                <span class="detail-value">${lesson.isRecurring ? 'Recurring (' + lesson.recurrenceType + ')' : 'One-time'}</span>
            </div>
            ${lesson.isRepeatLesson ? '<div class="lesson-detail-row"><span class="detail-label">Note</span><span class="detail-value repeat-notice">This is a review/repeat lesson</span></div>' : ''}
        </div>
        <div class="form-group" style="margin-top: 16px;">
            <label class="form-label">Lesson Notes</label>
            <div class="rich-text-editor-wrapper">
                <div class="rich-text-toolbar">
                    <button type="button" class="toolbar-btn" onclick="formatText('bold')" title="Bold (Ctrl+B)">
                        <strong>B</strong>
                    </button>
                    <button type="button" class="toolbar-btn" onclick="formatText('italic')" title="Italic (Ctrl+I)">
                        <em>I</em>
                    </button>
                    <button type="button" class="toolbar-btn" onclick="formatText('underline')" title="Underline (Ctrl+U)">
                        <u>U</u>
                    </button>
                    <div class="toolbar-separator"></div>
                    <button type="button" class="toolbar-btn" onclick="formatText('highlight', 'green')" title="Successfully learned">
                        <span class="highlight-green">✓</span>
                    </button>
                    <button type="button" class="toolbar-btn" onclick="formatText('highlight', 'red')" title="Needs work">
                        <span class="highlight-red">✗</span>
                    </button>
                    <button type="button" class="toolbar-btn" onclick="formatText('highlight', 'orange')" title="Needs review">
                        <span class="highlight-orange">↻</span>
                    </button>
                    <button type="button" class="toolbar-btn" onclick="formatText('highlight', 'blue')" title="Note">
                        <span class="highlight-blue">ℹ</span>
                    </button>
                    <div class="toolbar-separator"></div>
                    <button type="button" class="toolbar-btn" onclick="formatText('removeFormat')" title="Remove formatting">
                        🗑️
                    </button>
                </div>
                <div class="rich-text-editor"
                     id="lessonNotesInput"
                     contenteditable="true"
                     placeholder="What happened during this lesson..."
                     oninput="validateEditorContent()">${lesson.notes || ''}</div>
            </div>
        </div>
        <div class="modal-actions">
            <button type="button" class="btn-secondary" onclick="deleteLessonFromCalendar(${lesson.id})">Delete</button>
            ${lesson.isRecurring && lesson.recurrenceGroupId ? `<button type="button" class="btn-secondary" onclick="deleteRecurringFromLesson(${lesson.id})">Delete this and all following</button>` : ''}
            <button type="button" class="btn-secondary" onclick="window.location.href='/${lesson.studentId}'">Go to Chat</button>
            <button type="button" class="btn-primary" onclick="saveLessonNotes(${lesson.id})">Save Notes</button>
        </div>
    `;

    // Initialize placeholder for the editor
    updatePlaceholder(document.getElementById('lessonNotesInput'));

    openModal('lessonDetailModal');
}

function closeLessonDetailModal() {
    closeModal('lessonDetailModal');
}

async function saveLessonNotes(lessonId) {
    const editor = document.getElementById('lessonNotesInput');
    const notes = editor.innerHTML;
    const lesson = calendarLessons.find(l => l.id === lessonId);
    if (!lesson) return;

    // Don't allow empty notes for syncing
    if (!notes || notes.trim() === '' || editor.textContent.trim() === '') {
        alert('Please enter notes before saving.');
        return;
    }

    try {
        // Update calendar event notes
        const eventData = lessonToEvent(lesson);
        eventData.notes = notes;
        await apiPatch(`/api/v1/calendar-events/${lessonId}`, eventData);

        // Create or update corresponding lesson entry (this marks lesson as "conducted")
        // Only lessons with notes appear on Lessons page
        try {
            const lessonsResponse = await apiGet(`/api/v1/lessons?project_id=${lesson.studentId}`);
            const existingLesson = lessonsResponse.lessons.find(l => {
                const lessonDate = new Date(l.date);
                return isSameDay(lessonDate, lesson.date);
            });

            const lessonData = {
                project_id: lesson.studentId,
                description: notes,
                date: toLocalISOString(lesson.date)
            };

            if (existingLesson) {
                // Update existing lesson
                await apiPatch(`/api/v1/lessons/${existingLesson.id}`, lessonData);
            } else {
                // Create new lesson entry (marks it as conducted)
                await apiPost('/api/v1/lessons', lessonData);
            }
        } catch (lessonError) {
            console.warn('Failed to sync with lessons:', lessonError);
            // Continue anyway - calendar event was saved
        }

        // Update in local state
        lesson.notes = notes;
        console.log('Notes saved and synced for lesson:', lessonId);
    } catch (error) {
        console.error('Failed to save notes:', error);
        alert('Failed to save notes. Please try again.');
        return;
    }

    closeModalUrl('event');
}

async function deleteRecurringFromLesson(lessonId) {
    if (!confirm('Delete this lesson and all following recurring lessons in this series?')) return;

    try {
        const response = await apiDelete(`/api/v1/calendar-events/${lessonId}/recurring-from`);
        const deletedCount = response.count || 1;

        // Remove all deleted lessons from local state
        const lesson = calendarLessons.find(l => l.id === lessonId);
        if (lesson && lesson.recurrenceGroupId) {
            calendarLessons = calendarLessons.filter(l => {
                if (l.recurrenceGroupId !== lesson.recurrenceGroupId) return true;
                return l.date < lesson.date;
            });
        }

        applyAllRepeatLabels();
        closeModalUrl('event');
        renderCalendar();

        console.log('Deleted recurring lessons from:', lessonId, 'count:', deletedCount);
    } catch (error) {
        console.error('Failed to delete recurring lessons:', error);
        alert('Failed to delete recurring lessons. Please try again.');
    }
}

async function deleteLessonFromCalendar(lessonId) {
    if (!confirm('Delete this lesson?')) return;

    const lesson = calendarLessons.find(l => l.id === lessonId);
    if (!lesson) return;

    try {
        // Delete calendar event
        await apiDelete(`/api/v1/calendar-events/${lessonId}`);

        // Find and delete corresponding lesson entry
        try {
            const lessonsResponse = await apiGet(`/api/v1/lessons?project_id=${lesson.studentId}`);
            const existingLesson = lessonsResponse.lessons.find(l => {
                const lessonDate = new Date(l.date);
                return isSameDay(lessonDate, lesson.date);
            });

            if (existingLesson) {
                await apiDelete(`/api/v1/lessons/${existingLesson.id}`);
            }
        } catch (lessonError) {
            console.warn('Failed to delete from lessons:', lessonError);
            // Continue anyway - calendar event was deleted
        }

        // Remove from local state
        calendarLessons = calendarLessons.filter(l => l.id !== lessonId);
        applyAllRepeatLabels();
        closeModalUrl('event');
        renderCalendar();

        console.log('Lesson deleted:', lessonId);
    } catch (error) {
        console.error('Failed to delete lesson:', error);
        alert('Failed to delete lesson. Please try again.');
    }
}

let selectedBookingColor = 'blue';

function selectBookingColor(color) {
    selectedBookingColor = color;
    document.querySelectorAll('.color-pick-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.color === color);
    });
}

function openBookLessonModal(dateStr, hour, minute, durationMinutes = 60) {
    const optionsContainer = document.querySelector('.custom-select[data-target="bookStudentSelect"] .custom-select-options');
    optionsContainer.innerHTML = students.map((s, i) =>
        `<div class="custom-select-option${i === 0 ? ' selected' : ''}" data-value="${s.id}">${s.student_name}</div>`
    ).join('');
    if (students.length > 0) {
        document.getElementById('bookStudentSelect').value = students[0].id;
        document.querySelector('.custom-select[data-target="bookStudentSelect"] .custom-select-trigger').textContent = students[0].student_name;
    }

    bookDatePicker.setDate(dateStr, true);
    bookTimePicker.setDate(`${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`, true);
    setCustomSelectValue('bookRecurrenceSelect', 'none');
    setCustomSelectValue('bookDurationSelect', String(closestDuration(durationMinutes)));

    selectedBookingColor = 'blue';
    selectBookingColor('blue');

    openModal('bookLessonModal');
}

function closeBookLessonModal() {
    closeModal('bookLessonModal');
}

async function bookLesson(event) {
    event.preventDefault();

    const studentId = document.getElementById('bookStudentSelect').value;
    const student = students.find(s => s.id === studentId);
    if (!student) {
        alert('Please select a student');
        return;
    }

    const date = document.getElementById('bookDateInput').value;
    const time = document.getElementById('bookStartTimeInput').value;
    const duration = parseInt(document.getElementById('bookDurationSelect').value);
    const recurrence = document.getElementById('bookRecurrenceSelect').value;

    const [hour, minute] = time.split(':').map(Number);
    const lessonDate = new Date(date + 'T00:00:00');
    lessonDate.setHours(hour, minute, 0, 0);

    const isRecurring = recurrence !== 'none';
    const groupId = isRecurring ? `group-${Date.now()}` : null;
    const repeatCount = isRecurring ? 12 : 1;

    try {
        // Fetch existing lessons for this student to sync descriptions on creation
        const lessonsData = await apiGet(`/api/v1/lessons?project_id=${studentId}`);
        const existingLessons = lessonsData?.lessons ?? [];

        // Create calendar events (NOT lesson entries - those are created when notes are added)
        for (let i = 0; i < repeatCount; i++) {
            const instanceDate = new Date(lessonDate);

            if (recurrence === 'weekly') {
                instanceDate.setDate(instanceDate.getDate() + i * 7);
            } else if (recurrence === 'biweekly') {
                instanceDate.setDate(instanceDate.getDate() + i * 14);
            } else if (recurrence === 'monthly') {
                instanceDate.setMonth(instanceDate.getMonth() + i);
            }

            const endTime = new Date(instanceDate);
            endTime.setMinutes(endTime.getMinutes() + duration);

            // Sync lesson description if one already exists for this date
            const matchingLesson = existingLessons.find(l => isSameDay(new Date(l.date), instanceDate));
            const notes = matchingLesson?.description ?? '';

            // Create calendar event
            const eventData = {
                project_id: studentId,
                start_time: toLocalISOString(instanceDate),
                end_time: toLocalISOString(endTime),
                notes: notes,
                color: selectedBookingColor,
                is_recurring: isRecurring,
                recurrence_type: recurrence !== 'none' ? recurrence : null,
                recurrence_group_id: groupId,
            };

            const calendarResponse = await apiPost('/api/v1/calendar-events', eventData);
            const createdEvent = calendarResponse.event;

            // Add to local state
            const studentsMap = {};
            students.forEach(s => studentsMap[s.id] = s);
            const newLesson = eventToLesson(createdEvent, studentsMap);
            calendarLessons.push(newLesson);
        }

        applyRepeatLabels(studentId);
        closeBookLessonModal();
        renderCalendar();

        console.log('Booked calendar events:', repeatCount);
    } catch (error) {
        console.error('Failed to book lesson:', error);
        alert('Failed to book lesson. Please try again.');
    }
}

//////////////////////////////////////////////////
//////////////// EVENT PREVIEW ///////////////////
//////////////////////////////////////////////////

function showEventPreview(lessonId, anchorEl) {
    const lesson = calendarLessons.find(l => l.id === lessonId);
    if (!lesson) return;

    hideEventPreview();

    const rect = anchorEl.getBoundingClientRect();
    const endTimeStr = formatEndTime(lesson.startHour, lesson.startMinute, lesson.duration);
    const timeStr = `${formatTime(lesson.startHour, lesson.startMinute)} – ${endTimeStr}`;
    const recurrenceHtml = lesson.isRecurring
        ? `<div class="ev-preview-row">↻ Recurring ${lesson.recurrenceType}</div>` : '';

    const preview = document.createElement('div');
    preview.id = 'ev-preview';
    preview.innerHTML = `
        <div class="ev-preview-name">${escapeHtml(lesson.studentName)}</div>
        <div class="ev-preview-row">🕐 ${timeStr} (${lesson.duration} min)</div>
        ${recurrenceHtml}
        <div class="ev-preview-hint">Click to open · drag to reschedule</div>
    `;

    // Position to the right, or left if near screen edge
    const leftPos = rect.right + 10 + 220 > window.innerWidth
        ? rect.left - 230
        : rect.right + 10;
    preview.style.left = leftPos + 'px';
    preview.style.top = rect.top + 'px';

    document.body.appendChild(preview);
}

function hideEventPreview() {
    const el = document.getElementById('ev-preview');
    if (el) el.remove();
}

//////////////////////////////////////////////////
////////////// RESCHEDULE LESSON /////////////////
//////////////////////////////////////////////////

async function finishReschedule(lessonId, newDateStr, newStartH, isRecurring, groupId) {
    const lesson = calendarLessons.find(l => l.id === lessonId);
    if (!lesson) return;

    const newHour = Math.floor(newStartH);
    const newMinute = Math.round((newStartH % 1) * 60);

    if (isRecurring && groupId) {
        // Show inline confirmation
        showRescheduleConfirm(lessonId, newDateStr, newHour, newMinute, groupId, lesson);
    } else {
        await applyReschedule([lesson], newDateStr, newHour, newMinute, 0);
    }
}

function showRescheduleConfirm(lessonId, newDateStr, newHour, newMinute, groupId, lesson) {
    const existing = document.getElementById('reschedule-confirm');
    if (existing) existing.remove();

    const div = document.createElement('div');
    div.id = 'reschedule-confirm';
    div.className = 'reschedule-confirm';
    div.innerHTML = `
        <span>Move recurring event?</span>
        <button class="btn-sm-primary" id="rescheduleThis">This only</button>
        <button class="btn-sm-primary" id="rescheduleFollowing">This &amp; following</button>
        <button class="btn-sm-ghost" id="rescheduleCancel">Cancel</button>
    `;
    document.querySelector('.calendar-wrapper').appendChild(div);

    document.getElementById('rescheduleThis').onclick = async () => {
        div.remove();
        await applyReschedule([lesson], newDateStr, newHour, newMinute, 0);
    };
    document.getElementById('rescheduleFollowing').onclick = async () => {
        div.remove();
        const origDate = lesson.date;
        const following = calendarLessons.filter(l =>
            l.recurrenceGroupId === groupId && l.date >= origDate
        ).sort((a, b) => a.date - b.date);
        // Compute day/time delta relative to the dragged event
        const dayDelta = (new Date(newDateStr + 'T00:00:00') - new Date(toDateString(lesson.date) + 'T00:00:00')) / 86400000;
        const minDelta = (newHour * 60 + newMinute) - (lesson.startHour * 60 + lesson.startMinute);
        await applyReschedule(following, null, null, null, 0, dayDelta, minDelta);
    };
    document.getElementById('rescheduleCancel').onclick = () => {
        div.remove();
        renderCalendar();
    };
}

async function applyReschedule(lessons, newDateStr, newHour, newMinute, _unused, dayDelta = 0, minDelta = 0) {
    try {
        for (const lesson of lessons) {
            let targetDate, targetHour, targetMinute;
            if (newDateStr !== null) {
                // Single event move
                targetDate = new Date(newDateStr + 'T00:00:00');
                targetHour = newHour;
                targetMinute = newMinute;
            } else {
                // Apply deltas for recurring
                targetDate = new Date(lesson.date);
                targetDate.setDate(targetDate.getDate() + dayDelta);
                const totalMin = lesson.startHour * 60 + lesson.startMinute + minDelta;
                targetHour = Math.floor(totalMin / 60);
                targetMinute = totalMin % 60;
            }
            targetDate.setHours(targetHour, targetMinute, 0, 0);
            const endDate = new Date(targetDate);
            endDate.setMinutes(endDate.getMinutes() + lesson.duration);

            await apiPatch(`/api/v1/calendar-events/${lesson.id}`, {
                project_id: lesson.studentId,
                start_time: toLocalISOString(targetDate),
                end_time: toLocalISOString(endDate),
                notes: lesson.notes,
                color: lesson.color,
                is_recurring: lesson.isRecurring,
                recurrence_type: lesson.recurrenceType !== 'none' ? lesson.recurrenceType : null,
                recurrence_group_id: lesson.recurrenceGroupId,
            });

            // Update local state
            lesson.date = targetDate;
            lesson.startHour = targetHour;
            lesson.startMinute = targetMinute;
        }
        renderCalendar();
    } catch (err) {
        console.error('Failed to reschedule:', err);
        alert('Failed to reschedule lesson. Please try again.');
        renderCalendar();
    }
}

//////////////////////////////////////////////////
/////////////// HELPER FUNCTIONS /////////////////
//////////////////////////////////////////////////

function getWeekStart(date) {
    const d = new Date(date);
    const day = d.getDay();
    const diff = d.getDate() - day + (day === 0 ? -6 : 1);
    d.setDate(diff);
    d.setHours(0, 0, 0, 0);
    return d;
}

function isSameDay(d1, d2) {
    return d1.getFullYear() === d2.getFullYear() &&
        d1.getMonth() === d2.getMonth() &&
        d1.getDate() === d2.getDate();
}

function toDateString(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function getLessonsForDay(date) {
    return calendarLessons
        .filter(l => isSameDay(l.date, date))
        .sort((a, b) => (a.startHour * 60 + a.startMinute) - (b.startHour * 60 + b.startMinute));
}

function formatTime(hour, minute) {
    return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

function formatEndTime(startHour, startMinute, duration) {
    const endMinutes = startHour * 60 + startMinute + duration;
    return formatTime(Math.floor(endMinutes / 60), endMinutes % 60);
}

function closestDuration(mins) {
    const options = [30, 45, 60, 90];
    return options.reduce((best, opt) => Math.abs(opt - mins) < Math.abs(best - mins) ? opt : best);
}

function formatWeekRange(start, end) {
    const opts = { month: 'long' };
    if (start.getMonth() === end.getMonth()) {
        return `${start.toLocaleDateString('en-US', opts)} ${start.getDate()} – ${end.getDate()}, ${start.getFullYear()}`;
    }
    return `${start.toLocaleDateString('en-US', opts)} ${start.getDate()} – ${end.toLocaleDateString('en-US', opts)} ${end.getDate()}, ${end.getFullYear()}`;
}

//////////////////////////////////////////////////
/////////// RICH TEXT EDITOR FUNCTIONS ///////////
//////////////////////////////////////////////////

function formatText(command, value = null) {
    const editor = document.getElementById('lessonNotesInput');
    if (!editor) return;
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
    const editor = document.getElementById('lessonNotesInput');
    if (!editor) return;

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
    if (!editor) return;
    const hasContent = editor.textContent.trim().length > 0;
    if (hasContent) {
        editor.removeAttribute('data-placeholder');
    } else {
        editor.setAttribute('data-placeholder', editor.getAttribute('placeholder') || 'What happened during this lesson...');
    }
}

//////////////////////////////////////////////////
/////////////// EVENT LISTENERS //////////////////
//////////////////////////////////////////////////

function setupCalendarEventListeners() {
    // Click on event tiles (delegated) — skip if a reschedule drag just completed
    document.addEventListener('click', (e) => {
        const eventTile = e.target.closest('.calendar-event');
        if (eventTile) {
            e.stopPropagation();
            // If a reschedule drag just fired, the mouseup handler already handled it
            if (rescheduleState !== null) return;
            const lessonId = parseInt(eventTile.dataset.lessonId);
            openModalUrl('event', lessonId);
        }
    });

    // Modal close on outside click
    document.addEventListener('click', (e) => {
        if (e.target.id === 'lessonDetailModal') closeModalUrl('event');
        if (e.target.id === 'bookLessonModal') closeBookLessonModal();
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Don't handle when modal is open or input is focused
        const activeModal = document.querySelector('.modal.active');
        if (activeModal) {
            if (e.key === 'Escape') {
                closeModalUrl('event');
                closeBookLessonModal();
            }
            return;
        }

        const tag = document.activeElement.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

        if (e.key === 'ArrowLeft') { e.preventDefault(); navigatePrev(); }
        if (e.key === 'ArrowRight') { e.preventDefault(); navigateNext(); }
        if (e.key === 't' || e.key === 'T') { e.preventDefault(); goToToday(); }
    });
}

//////////////////////////////////////////////////
//////////////////// INIT ////////////////////////
//////////////////////////////////////////////////

bookDatePicker = flatpickr("#bookDateInput", {
    dateFormat: "Y-m-d",
    disableMobile: true,
    locale: { firstDayOfWeek: 1 }
});

bookTimePicker = flatpickr("#bookStartTimeInput", {
    enableTime: true,
    noCalendar: true,
    dateFormat: "H:i",
    time_24hr: true,
    minuteIncrement: 5,
    disableMobile: true
});

initCalendarPage();
