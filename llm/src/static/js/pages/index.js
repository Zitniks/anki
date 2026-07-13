// Home Page - Student Grid Management
// Dependencies: utils/dom.js, utils/api.js, utils/helpers.js, components/modal.js

// State
let currentProjectId = null;
let currentChatId = null;
let projects = [];
let chats = [];
let messages = [];
let vocabulary = [];
let topics = [];
let currentAddItemType = null;
let currentEditingProjectId = null;
let collapsedSections = { vocabulary: false, topics: false };

// Configure marked
marked.setOptions({
    breaks: true,
    gfm: true,
    headerIds: false,
    mangle: false
});

//////////////////////////////////////////////////
///////////////////INITIALIZATION/////////////////
//////////////////////////////////////////////////

function initIndexPage() {
    loadProjects();
    loadRandomCatGif();
    setupEventListeners();
}

// Load random cat gif
function loadRandomCatGif() {
    const catImage = document.getElementById('catGif');
    if (catImage) {
        catImage.src = `https://cataas.com/cat?timestamp=${Date.now()}`;
    }
}

//////////////////////////////////////////////////
///////////////////STUDENT CRUD///////////////////
//////////////////////////////////////////////////

// Load projects
async function loadProjects() {
    try {
        const data = await apiGet('/api/v1/projects/');
        projects = data.projects;
        renderStudentsGrid();
    } catch (error) {
        console.error('Ошибка загрузки проектов:', error);
    }
}

// Render students grid on main page
function renderStudentsGrid() {
    const container = document.getElementById('studentsGrid');
    if (projects.length === 0) {
        container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-tertiary); padding: 40px;">No students yet</div>';
        return;
    }

    const hues = [0, 25, 45, 120, 180, 210, 260, 320];
    container.innerHTML = projects.map((project, i) => `
        <div class="student-tile" style="--student-hue: ${hues[i % hues.length]}" onclick="selectStudent('${project.id}')">
            <span class="student-name">${escapeHtml(project.student_name)}</span>
            <div class="student-menu" style="margin-left: auto; flex-shrink: 0;">
                <button class="menu-btn" onclick="event.stopPropagation(); toggleStudentMenu('${project.id}')">⋮</button>
                <div class="menu-dropdown" id="student-menu-${project.id}">
                    <div class="menu-item" onclick="event.stopPropagation(); openEditStudentModal('${project.id}')">Edit</div>
                    <div class="menu-item" onclick="event.stopPropagation(); deleteStudent('${project.id}')">Delete</div>
                </div>
            </div>
        </div>
    `).join('');
}

// Create student
async function createStudent(event) {
    event.preventDefault();

    const projectData = {
        name: document.getElementById('projectName').value,
        student_name: document.getElementById('studentName').value,
        student_level: document.getElementById('studentLevel').value,
        description: document.getElementById('projectDescription').value,
        notes: document.getElementById('projectNotes').value,
    };

    try {
        const data = await apiPost('/api/v1/projects/', projectData);
        projects.push(data.project);
        renderStudentsGrid();
        closeNewStudentModal();

        document.getElementById('projectName').value = '';
        document.getElementById('studentName').value = '';
        document.getElementById('studentLevel').value = '';
        document.getElementById('projectDescription').value = '';
        document.getElementById('projectNotes').value = '';
    } catch (error) {
        console.error('Ошибка создания проекта:', error);
        alert(error.message);
    }
}

// Select student and go to their page
async function selectStudent(projectId) {
    window.location.href = `/${projectId}`;
}

// Update student
async function updateStudent(event) {
    event.preventDefault();

    const projectData = {
        name: document.getElementById('editProjectName').value,
        student_name: document.getElementById('editStudentName').value,
        student_level: document.getElementById('editStudentLevel').value,
        description: document.getElementById('editProjectDescription').value,
        notes: document.getElementById('editProjectNotes').value
    };

    try {
        await apiPatch(`/api/v1/projects/${currentEditingProjectId}`, projectData);
        await loadProjects();
        closeEditStudentModal();
    } catch (error) {
        console.error('Ошибка обновления проекта:', error);
        alert('Error updating student');
    }
}

// Delete student
async function deleteStudent(id) {
    event.stopPropagation();

    if (!confirm('Delete this student? All data will be lost.')) return;

    try {
        await apiDelete(`/api/v1/projects/${id}`);
        projects = projects.filter(p => p.id !== id);
        renderStudentsGrid();

        // Close the menu after deletion
        const menu = document.getElementById(`student-menu-${id}`);
        if (menu) menu.style.display = 'none';
    } catch (error) {
        console.error('Ошибка удаления:', error);
        alert('Error deleting student');
    }
}

// Toggle student menu
function toggleStudentMenu(id) {
    document.querySelectorAll('.menu-dropdown').forEach(menu => {
        if (menu.id !== `student-menu-${id}`) {
            menu.style.display = 'none';
        }
    });

    const menu = document.getElementById(`student-menu-${id}`);
    menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
}

//////////////////////////////////////////////////
/////////////////////MODALS///////////////////////
//////////////////////////////////////////////////

// Modal functions
function openNewStudentModal() {
    document.getElementById('newStudentModal').classList.add('active');
    setTimeout(() => document.getElementById('projectName').focus(), 100);
}

function closeNewStudentModal() {
    document.getElementById('newStudentModal').classList.remove('active');
}

function openEditStudentModal(projectId) {
    event.stopPropagation();

    currentEditingProjectId = projectId;
    const project = projects.find(p => p.id === projectId);

    document.getElementById('editProjectName').value = project.name;
    document.getElementById('editStudentName').value = project.student_name;
    setCustomSelectValue('editStudentLevel', project.student_level);
    document.getElementById('editProjectDescription').value = project.description || '';
    document.getElementById('editProjectNotes').value = project.notes || '';

    document.getElementById('editStudentModal').classList.add('active');
    setTimeout(() => document.getElementById('editProjectName').focus(), 100);

    // Close all menus
    document.querySelectorAll('.menu-dropdown').forEach(menu => {
        menu.style.display = 'none';
    });
}

function closeEditStudentModal() {
    document.getElementById('editStudentModal').classList.remove('active');
    currentEditingProjectId = null;
}

//////////////////////////////////////////////////
////////////////EVENT LISTENERS///////////////////
//////////////////////////////////////////////////

function setupEventListeners() {
    // Close menus on outside click
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.student-menu') && !e.target.closest('.chat-item-menu')) {
            document.querySelectorAll('.menu-dropdown').forEach(menu => {
                menu.style.display = 'none';
            });
        }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeNewStudentModal();
            closeEditStudentModal();
        }
    });

    // Close modals on outside click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeNewStudentModal();
                closeEditStudentModal();
            }
        });
    });
}

// Initialize page
initIndexPage();
