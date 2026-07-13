/**
 * Helper Utilities
 * General purpose helper functions
 */

/**
 * Format date to localized string
 * @param {string} dateString - ISO date string
 * @param {string} locale - Locale code (default: 'ru-RU')
 * @returns {string} - Formatted date
 */
function formatDate(dateString, locale = 'ru-RU') {
    const date = new Date(dateString);
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return date.toLocaleDateString(locale, options);
}

/**
 * Navigation helper - go to home page
 */
function goHome() {
    window.location.href = '/';
}

/**
 * Navigation helper - go to topics page
 * @param {string} projectId - Project ID
 */
function goTopics(projectId) {
    if (!projectId) {
        console.error('No project ID provided');
        return;
    }
    window.location.href = `/student/${projectId}`;
}

/**
 * Navigation helper - go to lessons page
 * @param {string} projectId - Project ID
 */
function goToLessons(projectId) {
    if (!projectId) {
        console.error('No project ID provided');
        return;
    }
    window.location.href = `/lesson/${projectId}`;
}

/**
 * Navigation helper - go to repeat page
 * @param {string} projectId - Project ID
 */
function goRepeat(projectId) {
    if (!projectId) {
        console.error('No project ID provided');
        return;
    }
    window.location.href = `/repeat/${projectId}`;
}

/**
 * Navigation helper - go to materials page
 */
function goMaterials() {
    window.location.href = '/materials';
}

/**
 * Navigation helper - go to calendar page
 */
function goCalendar() {
    window.location.href = '/calendar';
}

/**
 * Navigation helper - go to attachments page
 */
function goAttachments() {
    window.location.href = '/attachments';
}
