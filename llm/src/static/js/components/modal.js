/**
 * Modal Component
 * Common modal management functions
 */

/**
 * Open a modal by ID
 * @param {string} modalId - ID of the modal element
 */
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
}

/**
 * Animate a modal closed, then remove active class
 * @param {HTMLElement} modal - The modal element
 */
function _animateModalClose(modal) {
    if (!modal || modal.classList.contains('is-closing')) return;
    modal.classList.add('is-closing');
    modal.addEventListener('animationend', () => {
        modal.classList.remove('active', 'is-closing');
    }, { once: true });
}

/**
 * Close a modal by ID
 * @param {string} modalId - ID of the modal element
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        _animateModalClose(modal);
    }
}

/**
 * Setup modal close on outside click
 * Call this function once on page load to setup all modals
 */
function setupModalCloseOnOutsideClick() {
    document.addEventListener('click', (e) => {
        const modals = document.querySelectorAll('.modal.active');
        modals.forEach(modal => {
            if (e.target === modal) {
                _animateModalClose(modal);
            }
        });
    });
}

/**
 * Setup Escape key to close modals
 * Call this function once on page load
 * @param {Function} customHandler - Optional custom handler for escape key
 */
function setupModalEscapeKey(customHandler) {
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (customHandler) {
                customHandler();
            } else {
                // Close all active modals
                document.querySelectorAll('.modal.active').forEach(modal => {
                    _animateModalClose(modal);
                });
            }
        }
    });
}
