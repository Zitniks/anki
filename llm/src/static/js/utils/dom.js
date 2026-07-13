/**
 * DOM Utilities
 * Common DOM manipulation functions used across pages
 */

/**
 * Escape HTML to prevent XSS attacks
 * @param {string} text - Text to escape
 * @returns {string} - Escaped HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Auto-resize textarea based on content
 * @param {HTMLTextAreaElement} textarea - Textarea element to resize
 */
function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
}

/**
 * Custom select dropdowns
 * Works with .custom-select elements that have data-target pointing to a hidden input
 */
function setCustomSelectValue(targetId, value) {
    const hiddenInput = document.getElementById(targetId);
    if (!hiddenInput) return;
    hiddenInput.value = value;
    const select = document.querySelector(`.custom-select[data-target="${targetId}"]`);
    if (!select) return;
    const trigger = select.querySelector('.custom-select-trigger');
    select.querySelectorAll('.custom-select-option').forEach(o => {
        const isMatch = o.dataset.value === value;
        o.classList.toggle('selected', isMatch);
        if (isMatch) trigger.textContent = o.textContent;
    });
}

document.addEventListener('click', function(e) {
    const trigger = e.target.closest('.custom-select-trigger');
    if (trigger) {
        const select = trigger.closest('.custom-select');
        // Close all other open selects
        document.querySelectorAll('.custom-select.open').forEach(s => {
            if (s !== select) s.classList.remove('open');
        });
        select.classList.toggle('open');
        return;
    }

    const option = e.target.closest('.custom-select-option');
    if (option) {
        const select = option.closest('.custom-select');
        const targetId = select.dataset.target;
        const hiddenInput = document.getElementById(targetId);
        const trigger = select.querySelector('.custom-select-trigger');

        // Update value
        hiddenInput.value = option.dataset.value;
        hiddenInput.dispatchEvent(new Event('change'));
        trigger.textContent = option.textContent;

        // Update selected state
        select.querySelectorAll('.custom-select-option').forEach(o => o.classList.remove('selected'));
        option.classList.add('selected');

        select.classList.remove('open');
        return;
    }

    // Close all selects when clicking outside
    document.querySelectorAll('.custom-select.open').forEach(s => s.classList.remove('open'));
});
