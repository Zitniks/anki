/**
 * Vocabulary Component
 * Shared vocabulary rendering and management across pages
 * Dependencies: utils/dom.js (escapeHtml), utils/api.js (apiGet, apiPost, apiDelete)
 */

/**
 * Render vocabulary list
 * @param {Array} vocabulary - Array of vocabulary items
 * @param {string} containerId - ID of container element (default: 'vocabularyList')
 * @param {boolean} showRemoveButton - Whether to show remove buttons (default: true)
 */
function renderVocabulary(vocabulary, containerId = 'vocabularyList', showRemoveButton = true, highlightIds = null) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Vocabulary container '${containerId}' not found`);
        return;
    }

    // console.log('Rendering vocabulary:', vocabulary);

    if (!vocabulary || vocabulary.length === 0) {
        container.innerHTML = '<div class="info-item empty">No words yet</div>';
        return;
    }

    // Sort by extraction date (newest first)
    const sortedVocabulary = [...vocabulary].sort((a, b) => {
        return new Date(b.extracted_at) - new Date(a.extracted_at);
    });

    container.innerHTML = sortedVocabulary.map(word => {
        if (showRemoveButton) {
            return `
                <div class="info-item" data-id="${word.id}">
                    <span>${escapeHtml(word.word)}</span>
                    <button class="btn-remove" onclick="removeVocabulary(${word.id})" title="Remove">×</button>
                </div>
            `;
        } else {
            return `
                <div class="info-item" data-id="${word.id}">${escapeHtml(word.word)}</div>
            `;
        }
    }).join('');

    if (highlightIds && highlightIds.size > 0) {
        container.querySelectorAll('.info-item[data-id]').forEach(el => {
            if (highlightIds.has(Number(el.dataset.id))) {
                el.classList.add('is-new');
                el.addEventListener('animationend', () => el.classList.remove('is-new'), { once: true });
            }
        });
    }
}

/**
 * Refresh vocabulary from API
 * @param {string} projectId - Project ID
 * @returns {Promise<Array>} - Updated vocabulary array
 */
async function refreshVocabulary(projectId) {
    try {
        const data = await apiGet(`/api/v1/projects/${projectId}/vocabulary`);
        // console.log('Vocabulary refreshed:', data.vocabulary);
        return data.vocabulary || [];
    } catch (error) {
        console.error('Error refreshing vocabulary:', error);
        return [];
    }
}

/**
 * Add vocabulary item
 * @param {string} projectId - Project ID
 * @param {string} word - Word or phrase to add
 * @returns {Promise<Array>} - Updated vocabulary array
 */
async function addVocabularyItem(projectId, word) {
    try {
        const data = await apiPost(`/api/v1/projects/${projectId}/vocabulary`, { items: [word] });
        return data.vocabulary || [];
    } catch (error) {
        console.error('Error adding vocabulary:', error);
        throw error;
    }
}

/**
 * Remove vocabulary item
 * @param {string} projectId - Project ID
 * @param {string} word - Word to remove
 * @returns {Promise<Array>} - Updated vocabulary array
 */
async function removeVocabularyItem(projectId, wordId) {
    try {
        const data = await apiDelete(`/api/v1/projects/${projectId}/vocabulary/${wordId}`);
        return data.vocabulary || [];
    } catch (error) {
        console.error('Error removing vocabulary:', error);
        throw error;
    }
}
