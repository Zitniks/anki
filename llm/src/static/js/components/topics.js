/**
 * Topics Component
 * Shared topics rendering and management across pages
 * Dependencies: utils/dom.js (escapeHtml), utils/api.js (apiGet, apiPost, apiDelete, apiPatch)
 */

/**
 * Render topics list (for sidebar display)
 * @param {Array} topics - Array of topic items
 * @param {string} containerId - ID of container element (default: 'topicsList')
 * @param {boolean} showRemoveButton - Whether to show remove buttons (default: true)
 */
function renderTopics(topics, containerId = 'topicsList', showRemoveButton = true, highlightIds = null) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Topics container '${containerId}' not found`);
        return;
    }

    if (!topics || topics.length === 0) {
        container.innerHTML = '<div class="info-item empty">No topics yet</div>';
        return;
    }

    // Check if any topics have status "DONE"
    // console.log('Rendering topics:', topics);
    const isSomethingDone = topics.some(item => item.status === 'DONE');
    if (!isSomethingDone) {
        container.innerHTML = '<div class="info-item empty">No topics yet</div>';
        return;
    }

    // Sort by extraction date (newest first)
    const sortedTopics = [...topics].sort((a, b) => {
        return new Date(b.extracted_at) - new Date(a.extracted_at);
    });

    // Filter only DONE topics
    const doneTopics = sortedTopics.filter(topic => topic.status === 'DONE');

    container.innerHTML = doneTopics.map(topic => {
        if (showRemoveButton) {
            return `
                <div class="info-item" data-id="${escapeHtml(topic.id)}">
                    <span>${escapeHtml(topic.topic)}</span>
                    <button class="btn-remove" onclick="removeTopic('${escapeHtml(topic.id)}')" title="Remove">×</button>
                </div>
            `;
        } else {
            return `
                <div class="info-item" data-id="${escapeHtml(topic.id)}">${escapeHtml(topic.topic)}</div>
            `;
        }
    }).join('');

    if (highlightIds && highlightIds.size > 0) {
        container.querySelectorAll('.info-item[data-id]').forEach(el => {
            if (highlightIds.has(el.dataset.id)) {
                el.classList.add('is-new');
                el.addEventListener('animationend', () => el.classList.remove('is-new'), { once: true });
            }
        });
    }
}

/**
 * Refresh topics from API
 * @param {string} projectId - Project ID
 * @returns {Promise<Array>} - Updated topics array
 */
async function refreshTopics(projectId) {
    try {
        const data = await apiGet(`/api/v1/projects/${projectId}/topics`);
        // console.log('Refreshed topics data:', data.topics || []);
        return data.topics || [];
    } catch (error) {
        console.error('Error refreshing topics:', error);
        return [];
    }
}

/**
 * Add topic item
 * @param {string} projectId - Project ID
 * @param {object} topicData - Topic data {topic, status, level, color}
 * @returns {Promise<object>} - Added topic
 */
async function addTopicItem(projectId, topicData) {
    try {
        const data = await apiPost(`/api/v1/projects/${projectId}/topics`, topicData);
        return data.topics || [];
    } catch (error) {
        console.error('Error adding topic:', error);
        throw error;
    }
}

/**
 * Remove topic item
 * @param {string} projectId - Project ID
 * @param {string} topicId - Topic ID to remove
 * @returns {Promise<Array>} - Updated topics array
 */
async function removeTopicItem(projectId, topicId) {
    try {
        const data = await apiDelete(`/api/v1/projects/${projectId}/topics/${topicId}`);
        return data.topics || [];
    } catch (error) {
        console.error('Error removing topic:', error);
        throw error;
    }
}

/**
 * Update topic item
 * @param {string} projectId - Project ID
 * @param {string} topicId - Topic ID to update
 * @param {object} topicData - Updated topic data
 * @returns {Promise<object>} - Updated topic
 */
async function updateTopicItem(projectId, topicId, topicData) {
    try {
        const data = await apiPatch(`/api/v1/projects/${projectId}/topics/${topicId}`, topicData);
        return data.topics || [];
    } catch (error) {
        console.error('Error updating topic:', error);
        throw error;
    }
}

/**
 * Refresh both vocabulary and topics together
 * Useful for pages that display both
 * @param {string} projectId - Project ID
 * @returns {Promise<object>} - Object with {vocabulary, topics}
 */
async function refreshVocabularyAndTopics(projectId) {
    try {
        const [vocabData, topicsData] = await Promise.all([
            apiGet(`/api/v1/projects/${projectId}/vocabulary`),
            apiGet(`/api/v1/projects/${projectId}/topics`)
        ]);

        return {
            vocabulary: vocabData.vocabulary || [],
            topics: topicsData.topics || []
        };
    } catch (error) {
        console.error('Error refreshing vocabulary and topics:', error);
        return {
            vocabulary: [],
            topics: []
        };
    }
}
