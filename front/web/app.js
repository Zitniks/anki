let API_BASE = "/api/v1";
const AUTOPLAY_KEY = "anki_autoplay_audio";
const AUTH_TOKEN_KEY = "anki_token";
const THEORY_SOURCE_URL = "/theory_tenses.json";
const TOPIC_WORDS_URL = "/word_topics.json";
const READING_PROGRESS_KEY = "anki_reading_progress";
const READING_LAST_BOOK_KEY = "anki_reading_last_book";
const READING_CHARS_PER_PAGE = 1500;
const THEME_KEY = "anki_theme";

// Library of available books — add another entry (with its own generated JSON,
// see scripts/gen_book_json.py) to grow this beyond one title.
const BOOKS = [
  {
    id: "norwood-builder",
    title: "The Adventure of the Norwood Builder",
    subtitle: "A2 · по мотивам Артура Конан Дойля",
    url: "/book_norwood_builder.json",
  },
];

const SUN_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"></path></svg>';
const MOON_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>';

function getTheme() {
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(THEME_KEY, theme);
  $("theme-toggle").innerHTML = theme === "dark" ? SUN_ICON : MOON_ICON;
}

function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

function setAuthToken(token) {
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  }
}

// Centralizes API_BASE-joining, Authorization header injection, and 401 handling
// for every call into our own backend. `path` starts with "/", e.g. "/words".
async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    setAuthToken(null);
    showLoginScreen();
  }
  return res;
}

const state = {
  words: [],
  sessionWord: null,
  currentRound: 1,
  roundWordIds: { 1: [], 2: [], 3: [], 4: [] },
  roundIndex: { 1: 0, 2: 0, 3: 0, 4: 0 },
  roundTargets: { 1: 0, 2: 0, 3: 0, 4: 0 },
  roundDone: { 1: 0, 2: 0, 3: 0, 4: 0 },
  typingCorrect: false,
  typingChecked: false,
  typingFeedbackVisible: false,
  pendingCorrect: null,
  trainingStarted: false,
  trainingCompleted: false,
  autoPlayAudio: localStorage.getItem(AUTOPLAY_KEY) !== "false",
  chatMessages: [],
  chatStreaming: false,
  aiReady: false,
  theoryData: null,
  theoryLoaded: false,
  theoryCurrentCategory: null,
  theoryCurrentTopic: null,
  readingBooksCache: {},
  readingCurrentBookId: null,
  readingCurrentPageIndex: 0,
  readingLookupWord: null,
  user: null,
  topicWordsData: null,
  topicWordsLoaded: false,
  topicCurrentTopic: null,
  topicSelectedWords: new Set(),
};

const $ = (id) => document.getElementById(id);

disableInputSuggestions();
updateTypingFeedbackVisibility();
applyTheme(getTheme());
$("theme-toggle").addEventListener("click", () => applyTheme(getTheme() === "dark" ? "light" : "dark"));

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    switchScreen(btn.dataset.screen);
  });
});

$("profile-toggle").addEventListener("click", (e) => {
  e.stopPropagation();
  $("profile-menu").classList.toggle("hidden");
});
document.addEventListener("click", (e) => {
  if (!$("profile-menu").contains(e.target) && e.target !== $("profile-toggle")) {
    $("profile-menu").classList.add("hidden");
  }
});
$("profile-stats-link").addEventListener("click", () => {
  $("profile-menu").classList.add("hidden");
  switchScreen("stats");
});
$("profile-open-modal").addEventListener("click", () => {
  $("profile-menu").classList.add("hidden");
  openProfileModal();
});
$("profile-modal-close").addEventListener("click", closeProfileModal);
$("profile-modal").addEventListener("click", (e) => {
  if (e.target === $("profile-modal")) {
    closeProfileModal();
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("profile-modal").classList.contains("hidden")) {
    closeProfileModal();
  }
});
$("profile-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = $("profile-save-status");
  const submitBtn = $("profile-form").querySelector("button[type=submit]");
  const name = $("profile-name").value.trim();
  const email = $("profile-email-input").value.trim();
  submitBtn.disabled = true;
  status.textContent = "";
  status.classList.remove("is-error");
  const res = await apiFetch(`/auth/me`, {
    method: "PATCH",
    body: JSON.stringify({ name, email }),
  });
  submitBtn.disabled = false;
  if (!res.ok) {
    status.textContent = await readError(res);
    status.classList.add("is-error");
    return;
  }
  status.textContent = "Сохранено ✓";
  state.user = { ...(state.user || {}), name, email };
});

$("go-train").addEventListener("click", () => switchScreen("training"));
$("train-start").addEventListener("click", () => initTrainingSession($("train-count").value));
$("train-restart").addEventListener("click", showTrainingSetup);
$("search").addEventListener("input", renderWordsTable);
$("speak-btn").addEventListener("click", () => speakText(state.sessionWord?.word));
$("typing-check").addEventListener("click", onTypingSubmit);
$("typing-next").addEventListener("click", onTypingNext);
$("explain-error-btn").addEventListener("click", onExplainErrorClick);
$("typing-feedback-toggle").addEventListener("click", toggleTypingFeedback);
$("typing-input").addEventListener("input", renderTypingFeedback);
$("typing-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    onTypingSubmit();
  }
});
$("autoplay-audio").checked = state.autoPlayAudio;
$("autoplay-audio").addEventListener("change", (e) => {
  state.autoPlayAudio = e.target.checked;
  localStorage.setItem(AUTOPLAY_KEY, String(state.autoPlayAudio));
});

$("theory-back-to-categories").addEventListener("click", renderTheoryCategories);
$("theory-back-to-topics").addEventListener("click", () => {
  if (state.theoryCurrentCategory) {
    renderTheoryTopicList(state.theoryCurrentCategory);
  }
});
$("theory-reinforce").addEventListener("click", () => {
  if (state.theoryCurrentTopic) {
    reinforceTheoryTopic(state.theoryCurrentTopic);
  }
});

$("reading-back-to-library").addEventListener("click", showReadingLibrary);
$("reading-prev-page").addEventListener("click", goToPrevPage);
$("reading-next-page").addEventListener("click", goToNextPage);

document.querySelectorAll(".add-mode-tab").forEach((btn) => {
  btn.addEventListener("click", () => switchAddMode(btn.dataset.addMode));
});
$("topic-back").addEventListener("click", showTopicList);
$("topic-select-all").addEventListener("click", selectAllTopicWords);
$("topic-select-none").addEventListener("click", clearTopicWordSelection);
$("topic-add-selected").addEventListener("click", addSelectedTopicWords);

$("chat-launcher").addEventListener("click", () => {
  const opening = $("chat-widget").classList.contains("hidden");
  $("chat-widget").classList.toggle("hidden");
  if (opening) {
    loadAIStatus();
    renderChatMessages();
    autoResizeChatInput();
  }
});
$("chat-form").addEventListener("submit", onChatSubmit);
$("chat-input").addEventListener("input", autoResizeChatInput);

$("tips-launcher").addEventListener("click", () => {
  const opening = $("tips-widget").classList.contains("hidden");
  $("tips-widget").classList.toggle("hidden");
  if (opening) {
    loadDailyTips();
  }
});
$("tips-go-to-training").addEventListener("click", () => {
  $("tips-widget").classList.add("hidden");
  switchScreen("training");
});

$("enrich-btn").addEventListener("click", async () => {
  const form = $("add-form");
  const word = form.word.value.trim();
  if (!word) {
    showError("Сначала введите слово");
    return;
  }
  const btn = $("enrich-btn");
  btn.disabled = true;
  btn.textContent = "…";
  try {
    const res = await apiFetch(`/words/enrich`, {
      method: "POST",
      body: JSON.stringify({ word }),
    });
    if (!res.ok) {
      showError(await readError(res));
      return;
    }
    const draft = await res.json();
    form.translation.value = draft.translation || "";
    form.example.value = draft.example || "";
    form.transcription.value = draft.transcription || "";
  } finally {
    btn.disabled = false;
    btn.textContent = "Заполнить";
  }
});

$("add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  const payload = Object.fromEntries(formData.entries());
  const res = await apiFetch(`/words`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    showError(await readError(res));
    return;
  }
  e.target.reset();
  showInfo("Слово добавлено");
  await Promise.all([loadWords(), loadStats()]);
  switchScreen("dictionary");
});

function switchScreen(name) {
  const wasOnPractice = $("screen-practice").classList.contains("active");
  if (wasOnPractice && name !== "practice") {
    undockPracticeChat();
  }

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.screen === name);
  });
  document.querySelectorAll(".screen").forEach((screen) => {
    screen.classList.toggle("active", screen.id === `screen-${name}`);
  });
  if (name === "dictionary") {
    loadWords();
  }
  if (name === "stats" || name === "home") {
    loadStats();
    if (name === "stats") {
      loadActivity();
    }
  }
  if (name === "training") {
    if (!state.trainingStarted || state.trainingCompleted) {
      showTrainingSetup();
    } else {
      renderRound();
    }
  }
  if (name === "theory") {
    loadTheoryData();
  }
  if (name === "reading") {
    initReadingScreen();
  }
  if (name === "practice") {
    dockPracticeChat();
  }
}

// The practice screen's chat is the same shared chat-widget node used by the
// floating launcher elsewhere — docking just relocates it into the screen's
// layout instead of duplicating the conversation state.
function dockPracticeChat() {
  $("practice-chat-slot").appendChild($("chat-widget"));
  $("chat-widget").classList.remove("hidden");
  $("chat-launcher").classList.add("hidden");
  loadAIStatus();
  renderChatMessages();
  autoResizeChatInput();
}

function undockPracticeChat() {
  document.body.appendChild($("chat-widget"));
  $("chat-widget").classList.add("hidden");
  $("chat-launcher").classList.remove("hidden");
}

// Moving #chat-input between the docked (full-width) and floating (narrow)
// layouts changes how many lines its content wraps to, so a height computed
// under one layout goes stale under the other — recompute on every transition,
// not just on keystrokes.
function autoResizeChatInput() {
  const el = $("chat-input");
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

async function loadTheoryData() {
  if (!state.theoryLoaded) {
    const res = await fetch(THEORY_SOURCE_URL);
    if (!res.ok) {
      showError("Не удалось загрузить теорию");
      return;
    }
    state.theoryData = await res.json();
    state.theoryLoaded = true;
  }
  renderTheoryCategories();
}

function renderTheoryCategories() {
  $("theory-topics").classList.add("hidden");
  $("theory-detail").classList.add("hidden");
  const container = $("theory-categories");
  container.classList.remove("hidden");
  container.innerHTML = "";
  for (const category of state.theoryData.categories) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "theory-category-card";
    btn.textContent = category.title;
    btn.addEventListener("click", () => renderTheoryTopicList(category));
    container.appendChild(btn);
  }
}

function renderTheoryTopicList(category) {
  state.theoryCurrentCategory = category;
  $("theory-categories").classList.add("hidden");
  $("theory-detail").classList.add("hidden");
  $("theory-topics").classList.remove("hidden");
  $("theory-category-title").textContent = category.title;

  const list = $("theory-topic-list");
  list.innerHTML = "";
  let lastGroup = null;
  for (const topic of category.topics) {
    if (topic.group && topic.group !== lastGroup) {
      const groupHeading = document.createElement("div");
      groupHeading.className = "theory-topic-group";
      groupHeading.textContent = topic.group;
      list.appendChild(groupHeading);
      lastGroup = topic.group;
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "theory-topic-item";
    const levelBadge = topic.level ? `<span class="theory-level-badge">${escapeHtml(topic.level)}</span>` : "";
    btn.innerHTML = `<span>${escapeHtml(topic.title)}</span>${levelBadge}`;
    btn.addEventListener("click", () => renderTheoryTopic(topic));
    list.appendChild(btn);
  }
}

function renderTheoryTopic(topic) {
  state.theoryCurrentTopic = topic;
  $("theory-topics").classList.add("hidden");
  $("theory-detail").classList.remove("hidden");
  $("theory-topic-title").textContent = topic.title;
  $("theory-topic-content").innerHTML = topic.html;
}

// Topic titles are mostly Russian ("⭐ Present Perfect vs Past Simple — главная
// развилка"), but /practice/generate rejects anything but English letters/
// space/hyphen/apostrophe — so pull out the longest ASCII run that actually
// looks like a grammar term (most alphabetic chars wins over stray "B1"/"12").
function extractGrammarTermFromTitle(title) {
  const runs = title.match(/[A-Za-z0-9 ,'-]+/g) || [];
  let best = "";
  let bestAlpha = 0;
  for (const run of runs) {
    const trimmed = run.trim();
    const alphaCount = (trimmed.match(/[A-Za-z]/g) || []).length;
    if (alphaCount > bestAlpha) {
      bestAlpha = alphaCount;
      best = trimmed;
    }
  }
  return bestAlpha >= 3 ? best : null;
}

// "Закрепить тему": drops the topic's own examples into the practice chat as
// a message, then immediately follows up with a generated quiz — so leaving
// theory for practice doesn't lose the thing the user just read.
async function reinforceTheoryTopic(topic) {
  const level = topic.level?.match(/[ABC][12]/)?.[0] || "B1";
  state.chatMessages.push({ role: "user", text: `Закрепить тему: ${topic.title}` });
  state.chatMessages.push({
    role: "assistant",
    text: `📖 Примеры и объяснение по теме «${topic.title}»:`,
    html: topic.html,
  });
  switchScreen("practice");
  renderChatMessages();
  const grammarTerm = extractGrammarTermFromTitle(topic.title);
  // Reference topics ("Топ-5 ошибок русскоговорящих", "Порядок изучения")
  // have no extractable English term — fall back to the user's own
  // due/random words, same as a generic "дай мне практику" chat request.
  const words = grammarTerm ? [grammarTerm] : await pickPracticeWords();
  await renderPractice(words, level, `Квиз для закрепления темы «${topic.title}»:`);
}

function initReadingScreen() {
  if (state.readingCurrentBookId && state.readingBooksCache[state.readingCurrentBookId]) {
    showReadingBookView();
    renderCurrentPage();
    return;
  }
  const lastBookId = localStorage.getItem(READING_LAST_BOOK_KEY);
  const lastBook = lastBookId && BOOKS.find((b) => b.id === lastBookId);
  if (lastBook) {
    openReadingBook(lastBook);
    return;
  }
  showReadingLibrary();
}

function showReadingLibrary() {
  state.readingCurrentBookId = null;
  localStorage.removeItem(READING_LAST_BOOK_KEY);
  $("reading-library").classList.remove("hidden");
  $("reading-book").classList.add("hidden");
  renderReadingLibrary();
}

function showReadingBookView() {
  $("reading-library").classList.add("hidden");
  $("reading-book").classList.remove("hidden");
}

function renderReadingLibrary() {
  const container = $("reading-library");
  container.innerHTML = "";
  for (const book of BOOKS) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "reading-book-card";
    card.innerHTML = `
      <div class="reading-book-card-title">${escapeHtml(book.title)}</div>
      <div class="reading-book-card-subtitle">${escapeHtml(book.subtitle)}</div>
    `;
    card.addEventListener("click", () => openReadingBook(book));
    container.appendChild(card);
  }
}

function loadReadingProgress() {
  try {
    return JSON.parse(localStorage.getItem(READING_PROGRESS_KEY)) || {};
  } catch {
    return {};
  }
}

function saveReadingProgress(bookId, pageIndex) {
  const all = loadReadingProgress();
  all[bookId] = pageIndex;
  localStorage.setItem(READING_PROGRESS_KEY, JSON.stringify(all));
}

function getCurrentBook() {
  return state.readingBooksCache[state.readingCurrentBookId] || null;
}

// Flattens the whole book into book-sized pages (~READING_CHARS_PER_PAGE each,
// never splitting a paragraph) instead of per-chapter pill navigation — every
// chapter always starts a fresh page, and paging is a single continuous flow
// across the whole book, the way flipping through an actual book works.
function buildBookPages(book) {
  const pages = [];
  for (const part of book.parts) {
    let current = { chapterTitle: `${part.id}. ${part.title}`, paragraphs: [] };
    let charCount = 0;
    for (const paragraph of part.paragraphs) {
      if (charCount > 0 && charCount + paragraph.length > READING_CHARS_PER_PAGE) {
        pages.push(current);
        current = { chapterTitle: null, paragraphs: [] };
        charCount = 0;
      }
      current.paragraphs.push(paragraph);
      charCount += paragraph.length;
    }
    pages.push(current);
  }
  return pages;
}

async function openReadingBook(bookMeta) {
  let book = state.readingBooksCache[bookMeta.id];
  if (!book) {
    const res = await fetch(bookMeta.url);
    if (!res.ok) {
      showError("Не удалось загрузить книгу");
      return;
    }
    book = await res.json();
    book._pages = buildBookPages(book);
    state.readingBooksCache[bookMeta.id] = book;
  }
  state.readingCurrentBookId = bookMeta.id;
  localStorage.setItem(READING_LAST_BOOK_KEY, bookMeta.id);
  $("reading-title").textContent = book.title;
  $("reading-subtitle").textContent = `${book.subtitle} — ${book.source}`;
  showReadingBookView();

  const savedPage = loadReadingProgress()[bookMeta.id];
  state.readingCurrentPageIndex = typeof savedPage === "number" && Number.isFinite(savedPage) ? savedPage : 0;
  renderCurrentPage();
}

function renderCurrentPage() {
  const book = getCurrentBook();
  if (!book) return;
  const pages = book._pages;
  const requested = Number.isFinite(state.readingCurrentPageIndex) ? state.readingCurrentPageIndex : 0;
  const pageIndex = Math.min(Math.max(0, requested), pages.length - 1);
  state.readingCurrentPageIndex = pageIndex;
  const page = pages[pageIndex];

  const container = $("reading-paragraphs");
  container.innerHTML = "";
  container.classList.toggle("reading-chapter-start", Boolean(page.chapterTitle));
  if (page.chapterTitle) {
    const heading = document.createElement("h3");
    heading.className = "reading-chapter-heading";
    heading.textContent = page.chapterTitle;
    container.appendChild(heading);
  }
  for (const paragraph of page.paragraphs) {
    container.appendChild(renderBookParagraph(paragraph));
  }
  clearReadingLookup();

  $("reading-prev-page").disabled = pageIndex === 0;
  $("reading-next-page").disabled = pageIndex === pages.length - 1;
  $("reading-page-indicator").textContent = `Страница ${pageIndex + 1} из ${pages.length}`;

  saveReadingProgress(state.readingCurrentBookId, pageIndex);
}

function goToNextPage() {
  const book = getCurrentBook();
  if (!book || state.readingCurrentPageIndex >= book._pages.length - 1) return;
  state.readingCurrentPageIndex += 1;
  renderCurrentPage();
}

function goToPrevPage() {
  if (state.readingCurrentPageIndex <= 0) return;
  state.readingCurrentPageIndex -= 1;
  renderCurrentPage();
}

function renderBookParagraph(paragraph) {
  const p = document.createElement("p");
  const tokens = paragraph.split(/(\s+)/);
  for (const token of tokens) {
    if (token === "" || /^\s+$/.test(token)) {
      p.appendChild(document.createTextNode(token));
      continue;
    }
    const cleanWord = token.replace(/^[^A-Za-z']+|[^A-Za-z']+$/g, "").toLowerCase();
    if (!cleanWord) {
      p.appendChild(document.createTextNode(token));
      continue;
    }
    const span = document.createElement("span");
    span.className = "book-word";
    span.textContent = token;
    span.dataset.word = cleanWord;
    span.addEventListener("click", () => lookupBookWord(cleanWord, span));
    p.appendChild(span);
  }
  return p;
}

function clearReadingLookup() {
  state.readingLookupWord = null;
  $("reading-lookup").innerHTML =
    '<p class="reading-lookup-empty">Нажмите на слово в тексте, чтобы увидеть перевод.</p>';
}

async function lookupBookWord(word, spanEl) {
  document.querySelectorAll(".book-word.active").forEach((el) => el.classList.remove("active"));
  spanEl.classList.add("active");
  state.readingLookupWord = word;

  const panel = $("reading-lookup");
  panel.innerHTML = `<p class="reading-lookup-loading">Ищу «${escapeHtml(word)}»…</p>`;

  const res = await apiFetch(`/words/enrich`, {
    method: "POST",
    body: JSON.stringify({ word }),
  });
  if (state.readingLookupWord !== word) {
    return; // a newer click already superseded this lookup
  }
  if (!res.ok) {
    panel.innerHTML = `<p class="reading-lookup-error">${escapeHtml(await readError(res))}</p>`;
    return;
  }
  const draft = await res.json();
  renderReadingLookup(word, draft);
}

function renderReadingLookup(word, draft) {
  const sourceLabel = draft.source === "rag" ? "готовый пример" : "пример";
  const transcriptionHtml = draft.transcription
    ? `<div class="reading-lookup-transcription">${escapeHtml(draft.transcription)}</div>`
    : "";
  const exampleHtml = draft.example
    ? `<div class="reading-lookup-example">${escapeHtml(draft.example)}</div>`
    : "";
  $("reading-lookup").innerHTML = `
    <div class="reading-lookup-card">
      <div class="reading-lookup-word">${escapeHtml(word)}</div>
      ${transcriptionHtml}
      <div class="reading-lookup-translation">${escapeHtml(draft.translation || "")}</div>
      ${exampleHtml}
      <div class="reading-lookup-source">${escapeHtml(sourceLabel)}</div>
      <button id="reading-add-word" type="button" class="primary">Добавить в словарь</button>
    </div>
  `;
  $("reading-add-word").addEventListener("click", () => addWordFromReading(word, draft));
}

async function addWordFromReading(word, draft) {
  const btn = $("reading-add-word");
  btn.disabled = true;
  btn.textContent = "…";
  const res = await apiFetch(`/words`, {
    method: "POST",
    body: JSON.stringify({
      word,
      translation: draft.translation || "",
      example: draft.example || "",
      transcription: draft.transcription || "",
    }),
  });
  if (!res.ok) {
    showError(await readError(res));
    btn.disabled = false;
    btn.textContent = "Добавить в словарь";
    return;
  }
  showInfo(`«${word}» добавлено в словарь`);
  btn.textContent = "Добавлено ✓";
}

function disableInputSuggestions() {
  const nodes = document.querySelectorAll("input, textarea");
  for (const node of nodes) {
    const tag = node.tagName.toLowerCase();
    const type = String(node.getAttribute("type") || "").toLowerCase();
    const isTextarea = tag === "textarea";
    const isTextInput =
      tag === "input" &&
      (type === "" ||
        type === "text" ||
        type === "search" ||
        type === "email" ||
        type === "password" ||
        type === "tel" ||
        type === "url" ||
        type === "number");

    if (!isTextarea && !isTextInput) {
      continue;
    }

    node.setAttribute("autocomplete", "off");
    node.setAttribute("autocorrect", "off");
    node.setAttribute("autocapitalize", "off");
    if (node.id !== "typing-input") {
      node.setAttribute("spellcheck", "false");
    }
  }
}

async function loadWords() {
  const res = await apiFetch(`/words`);
  if (!res.ok) {
    showError(await readError(res));
    return;
  }
  state.words = await res.json();
  renderWordsTable();
}

function renderWordsTable() {
  const query = $("search").value.trim().toLowerCase();
  const rows = state.words.filter((w) => w.word.toLowerCase().includes(query));
  const tbody = $("words-table");
  tbody.innerHTML = "";
  for (const word of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(word.word)}</td>
      <td>${escapeHtml(word.translation)}</td>
      <td>${escapeHtml(word.transcription || "")}</td>
      <td>${new Date(word.created_at).toLocaleDateString()}</td>
      <td><button data-id="${word.id}">Удалить</button></td>
    `;
    tr.querySelector("button").addEventListener("click", async () => {
      const res = await apiFetch(`/words/${word.id}`, { method: "DELETE" });
      if (!res.ok) {
        showError(await readError(res));
        return;
      }
      showInfo("Слово удалено");
      await Promise.all([loadWords(), loadStats()]);
    });
    tbody.appendChild(tr);
  }
}

function switchAddMode(mode) {
  document.querySelectorAll(".add-mode-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.addMode === mode);
  });
  $("add-mode-single").classList.toggle("hidden", mode !== "single");
  $("add-mode-topics").classList.toggle("hidden", mode !== "topics");
  if (mode === "topics") {
    loadTopicWords();
  }
}

function ownedWordSet() {
  return new Set(state.words.map((w) => w.word.toLowerCase()));
}

async function loadTopicWords() {
  if (!state.topicWordsLoaded) {
    const res = await fetch(TOPIC_WORDS_URL);
    if (!res.ok) {
      showError("Не удалось загрузить темы");
      return;
    }
    state.topicWordsData = await res.json();
    state.topicWordsLoaded = true;
  }
  showTopicList();
}

function showTopicList() {
  state.topicCurrentTopic = null;
  state.topicSelectedWords = new Set();
  $("topic-list").classList.remove("hidden");
  $("topic-detail").classList.add("hidden");
  renderTopicList();
}

function renderTopicList() {
  const owned = ownedWordSet();
  const container = $("topic-list");
  container.innerHTML = "";
  for (const topic of state.topicWordsData.topics) {
    const ownedCount = topic.words.filter((w) => owned.has(w.word.toLowerCase())).length;
    const card = document.createElement("button");
    card.type = "button";
    card.className = "topic-card";
    card.innerHTML = `
      <span class="topic-card-icon">${topic.icon || "📚"}</span>
      <div class="topic-card-title">${escapeHtml(topic.title)}</div>
      <div class="topic-card-meta">${topic.words.length} слов${ownedCount ? ` · ${ownedCount} уже в словаре` : ""}</div>
    `;
    card.addEventListener("click", () => openTopic(topic));
    container.appendChild(card);
  }
}

function openTopic(topic) {
  state.topicCurrentTopic = topic;
  state.topicSelectedWords = new Set();
  $("topic-list").classList.add("hidden");
  $("topic-detail").classList.remove("hidden");
  $("topic-detail-title").textContent = topic.title;
  renderTopicWordsGrid();
}

function renderTopicWordsGrid() {
  const topic = state.topicCurrentTopic;
  const owned = ownedWordSet();
  const container = $("topic-words-grid");
  container.innerHTML = "";
  for (const w of topic.words) {
    const isOwned = owned.has(w.word.toLowerCase());
    const isSelected = state.topicSelectedWords.has(w.word);
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `topic-word-chip${isSelected ? " selected" : ""}`;
    chip.disabled = isOwned;
    chip.innerHTML = `
      <div class="topic-word-chip-word">${escapeHtml(w.word)}</div>
      <div class="topic-word-chip-translation">${escapeHtml(w.translation)}</div>
      <span class="topic-word-chip-badge">${isOwned ? "✓ в словаре" : isSelected ? "✓" : ""}</span>
    `;
    if (!isOwned) {
      chip.addEventListener("click", () => toggleTopicWordSelection(w.word));
    }
    container.appendChild(chip);
  }
  updateTopicSelectionBar();
}

function toggleTopicWordSelection(word) {
  if (state.topicSelectedWords.has(word)) {
    state.topicSelectedWords.delete(word);
  } else {
    state.topicSelectedWords.add(word);
  }
  renderTopicWordsGrid();
}

function selectAllTopicWords() {
  const owned = ownedWordSet();
  state.topicSelectedWords = new Set(
    state.topicCurrentTopic.words.filter((w) => !owned.has(w.word.toLowerCase())).map((w) => w.word)
  );
  renderTopicWordsGrid();
}

function clearTopicWordSelection() {
  state.topicSelectedWords = new Set();
  renderTopicWordsGrid();
}

function updateTopicSelectionBar() {
  const count = state.topicSelectedWords.size;
  $("topic-selected-count").textContent = `Выбрано: ${count}`;
  $("topic-add-selected").disabled = count === 0;
}

async function addSelectedTopicWords() {
  const topic = state.topicCurrentTopic;
  const words = topic.words.filter((w) => state.topicSelectedWords.has(w.word));
  if (words.length === 0) return;

  const btn = $("topic-add-selected");
  btn.disabled = true;
  btn.textContent = "Добавляю…";

  const res = await apiFetch(`/words/batch`, {
    method: "POST",
    body: JSON.stringify({ words }),
  });
  btn.textContent = "Добавить выбранные";

  if (!res.ok) {
    showError(await readError(res));
    btn.disabled = false;
    return;
  }

  const result = await res.json();
  await Promise.all([loadWords(), loadStats()]);
  state.topicSelectedWords = new Set();
  renderTopicWordsGrid();
  renderTopicList();

  const parts = [`добавлено: ${result.added.length}`];
  if (result.skipped.length) parts.push(`уже было: ${result.skipped.length}`);
  if (result.failed.length) parts.push(`не удалось: ${result.failed.length}`);
  showInfo(parts.join(", "));
}

function showTrainingSetup() {
  state.trainingStarted = false;
  $("train-restart").classList.add("hidden");
  $("training-card").classList.add("hidden");
  $("train-setup").classList.remove("hidden");
}

async function initTrainingSession(wordsPerRound) {
  const limit = Number.parseInt(wordsPerRound, 10) || 15;
  const res = await apiFetch(`/review/session?limit=${limit}`);
  if (!res.ok) {
    showError(await readError(res));
    return;
  }
  const data = await res.json();
  const sessionWords = data.words || [];
  const allIds = sessionWords.map((w) => w.word_id);
  const clozeIds = allIds;
  state.roundWordIds = { 1: allIds, 2: allIds, 3: allIds, 4: clozeIds };
  state.roundIndex = { 1: 0, 2: 0, 3: 0, 4: 0 };
  state.roundTargets = {
    1: allIds.length,
    2: allIds.length,
    3: allIds.length,
    4: clozeIds.length,
  };
  state.roundDone = { 1: 0, 2: 0, 3: 0, 4: 0 };
  state.typingChecked = false;
  state.typingCorrect = false;
  state.pendingCorrect = null;
  state.currentRound = 1;
  state.trainingStarted = true;
  state.trainingCompleted = false;
  $("train-setup").classList.add("hidden");
  $("training-card").classList.remove("hidden");
  $("train-restart").classList.add("hidden");
  if (!advanceRoundIfNeeded()) {
    renderNoTrainingWords();
    return;
  }
  await loadNextTrainingWord();
}

async function loadNextTrainingWord() {
  if (!advanceRoundIfNeeded()) {
    state.trainingCompleted = true;
    renderTrainingComplete();
    await loadStats();
    return;
  }
  const wordId = state.roundWordIds[state.currentRound][state.roundIndex[state.currentRound]];
  const res = await apiFetch(`/review/card?word_id=${wordId}&round=${state.currentRound}`);
  if (!res.ok) {
    showError(await readError(res));
    return;
  }
  const card = await res.json();
  if (card.skip) {
    state.roundIndex[state.currentRound] += 1;
    await loadNextTrainingWord();
    return;
  }
  state.sessionWord = card;
  renderRound();
}

function renderRound() {
  if (!state.sessionWord) {
    return;
  }
  $("typing-block").classList.add("hidden");
  $("typing-answer").classList.add("hidden");
  $("typing-answer").textContent = "";
  resetExplainError();
  $("typing-next-wrap").classList.add("hidden");
  $("typing-tools").classList.add("hidden");
  $("typing-hint").classList.add("hidden");
  $("typing-hint").innerHTML = "";
  $("typing-feedback").classList.add("hidden");
  $("typing-feedback").innerHTML = "";
  $("typing-check").textContent = "Проверить";
  state.typingChecked = false;
  state.pendingCorrect = null;
  $("train-options").innerHTML = "";
  $("train-example").textContent = state.sessionWord.example
    ? fillClozeBlank(state.sessionWord.example, state.sessionWord.word)
    : "";
  $("speak-btn").classList.remove("hidden");

  const current = state.currentRound;
  const done = state.roundDone[current] + 1;
  const target = state.roundTargets[current];
  $("train-session").textContent = `Раунд ${current}: ${Math.min(done, target)}/${target}`;
  $("training-card").classList.toggle("round2-mode", current === 2);

  if (current === 1) {
    $("train-stage").textContent = "Раунд 1 из 4: Аудирование + узнавание";
    $("train-word").textContent = state.sessionWord.word;
    $("train-prompt").classList.remove("hidden");
    $("train-prompt").textContent = "Выберите правильный перевод на русском";
    $("speak-btn").classList.remove("hidden");
    renderRussianOptions();
    if (state.autoPlayAudio) {
      speakText(state.sessionWord.word);
    }
    return;
  }

  if (current === 2) {
    $("train-stage").textContent = "Раунд 2 из 4: Воспроизведение";
    $("train-word").textContent = state.sessionWord.translation;
    $("train-prompt").classList.add("hidden");
    $("train-prompt").textContent = "";
    $("train-example").textContent = state.sessionWord.example || "";
    $("speak-btn").classList.add("hidden");
    $("typing-hint").classList.remove("hidden");
    $("typing-hint").innerHTML = buildScrambledHint(state.sessionWord.word)
      .map((w) => `<span class="hint-chip">${escapeHtml(w)}</span>`)
      .join("");
    $("typing-input").value = "";
    $("typing-input").disabled = false;
    $("typing-check").disabled = false;
    $("typing-block").classList.remove("hidden");
    $("typing-tools").classList.remove("hidden");
    updateTypingFeedbackVisibility();
    renderTypingFeedback();
    $("typing-input").focus();
    return;
  }

  if (current === 3) {
    $("train-stage").textContent = "Раунд 3 из 4: Аудирование";
    $("train-word").textContent = "🔊 Слушайте фразу и выберите перевод";
    $("train-prompt").classList.remove("hidden");
    $("train-prompt").textContent = "На экране нет английского текста";
    $("train-example").textContent = "";
    $("speak-btn").classList.remove("hidden");
    renderRussianOptions();
    if (state.autoPlayAudio) {
      speakText(state.sessionWord.word);
    }
    return;
  }

  $("train-stage").textContent = "Раунд 4 из 4: Продакшн в контексте";
  $("train-word").textContent = state.sessionWord.example || state.sessionWord.translation;
  $("train-prompt").classList.remove("hidden");
  $("train-prompt").textContent = state.sessionWord.translation;
  $("train-example").textContent = "";
  $("speak-btn").classList.add("hidden");
  $("typing-input").value = "";
  $("typing-input").disabled = false;
  $("typing-check").disabled = false;
  $("typing-block").classList.remove("hidden");
  $("typing-tools").classList.remove("hidden");
  updateTypingFeedbackVisibility();
  renderTypingFeedback();
  $("typing-input").focus();
}

function renderRussianOptions() {
  const options = buildUniqueOptions(
    state.sessionWord.translation,
    state.words.map((w) => w.translation),
    5
  );
  renderOptionButtons(options, (value) => {
    const correct = normalize(value) === normalize(state.sessionWord.translation);
    onRoundAnswered(correct);
  });
}

function renderOptionButtons(options, onClick) {
  const container = $("train-options");
  container.innerHTML = "";
  for (const option of options) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "option-btn";
    btn.textContent = option;
    btn.addEventListener("click", () => onClick(option));
    container.appendChild(btn);
  }
}

function setOptionButtonsDisabled(disabled) {
  document.querySelectorAll("#train-options .option-btn").forEach((btn) => {
    btn.disabled = disabled;
  });
}

function onTypingSubmit() {
  if (!state.sessionWord || (state.currentRound !== 2 && state.currentRound !== 4)) {
    return;
  }
  if (state.typingChecked) {
    const correct = Boolean(state.typingCorrect);
    state.typingCorrect = false;
    state.typingChecked = false;
    $("typing-check").textContent = "Проверить";
    finalizeRound(correct);
    return;
  }
  const value = $("typing-input").value;
  const correct = normalizeTypingPhrase(value) === normalizeTypingPhrase(state.sessionWord.word);
  $("typing-input").disabled = true;
  $("typing-answer").innerHTML = `
    <span class="answer-label">Правильный ответ:</span>
    <span class="answer-text">${escapeHtml(formatTypingAnswer(state.sessionWord.word))}</span>
  `;
  $("typing-answer").classList.remove("hidden");
  if (state.currentRound === 2 || state.currentRound === 4) {
    speakText(state.sessionWord.word);
  }
  const round = state.currentRound;
  if (correct) {
    showInfo(`Раунд ${round}: верно`);
  } else {
    showError(`Раунд ${round}: ошибка. Правильный ответ показан ниже.`);
    state.explainErrorPayload = {
      word: state.sessionWord.word,
      expected: state.sessionWord.word,
      got: value,
      sentence: state.sessionWord.example || "",
    };
    $("explain-error-btn").classList.remove("hidden");
  }
  state.typingCorrect = correct;
  state.typingChecked = true;
  $("typing-check").textContent = "Далее";
}

async function onExplainErrorClick() {
  const payload = state.explainErrorPayload;
  if (!payload) return;
  const btn = $("explain-error-btn");
  btn.disabled = true;
  btn.textContent = "…";
  try {
    const res = await apiFetch(`/ai/explain-error`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      showError(await readError(res));
      return;
    }
    const data = await res.json();
    $("explain-error-result").textContent = data.explanation || "";
    $("explain-error-result").classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = "Почему?";
  }
}

function resetExplainError() {
  state.explainErrorPayload = null;
  $("explain-error-btn").classList.add("hidden");
  $("explain-error-result").classList.add("hidden");
  $("explain-error-result").textContent = "";
}

function onTypingNext() {
  if (!state.sessionWord || state.pendingCorrect === null) {
    return;
  }
  const correct = Boolean(state.pendingCorrect);
  state.pendingCorrect = null;
  finalizeRound(correct);
}

function toggleTypingFeedback() {
  if (!state.sessionWord || (state.currentRound !== 2 && state.currentRound !== 4)) {
    return;
  }
  state.typingFeedbackVisible = !state.typingFeedbackVisible;
  updateTypingFeedbackVisibility();
}

function updateTypingFeedbackVisibility() {
  $("typing-feedback").classList.toggle("hidden", !state.typingFeedbackVisible);
  $("typing-feedback-toggle").textContent = state.typingFeedbackVisible
    ? "Скрыть подсветку"
    : "Показать подсветку";
}

function fillClozeBlank(sentence, word) {
  return sentence.replace(/___/g, word);
}

function buildScrambledHint(phrase) {
  return phrase.split(/\s+/).map(scrambleWord);
}

function scrambleWord(word) {
  const m = word.match(/^([^A-Za-z]*)([A-Za-z]+)([^A-Za-z]*)$/);
  if (!m) {
    return word;
  }
  const prefix = m[1];
  const core = m[2];
  const suffix = m[3];
  if (core.length < 4) {
    return word;
  }
  const chars = core.toLowerCase().split("");
  for (let i = chars.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  const mixed = chars.join("");
  if (mixed === core.toLowerCase()) {
    chars.reverse();
  }
  return `${prefix}${chars.join("")}${suffix}`;
}

function renderTypingFeedback() {
  if (!state.sessionWord || (state.currentRound !== 2 && state.currentRound !== 4)) {
    return;
  }
  const expectedWords = state.sessionWord.word.trim().split(/\s+/).map(stripTokenPunctuation);
  const typedWords = $("typing-input").value.trim().split(/\s+/).filter(Boolean);
  const container = $("typing-feedback");
  container.innerHTML = "";
  for (let i = 0; i < expectedWords.length; i += 1) {
    const expected = expectedWords[i];
    const typed = typedWords[i] || "";
    const span = document.createElement("span");
    span.className = "feedback-word";
    span.textContent = typed || "_".repeat(Math.min(expected.length, 12));

    if (!typed) {
      container.appendChild(span);
      continue;
    }
    if (normalizeTypingToken(typed) === normalizeTypingToken(expected)) {
      span.classList.add("is-correct");
    } else if (normalizeTypingToken(expected).startsWith(normalizeTypingToken(typed))) {
      span.classList.add("is-partial");
    } else {
      span.classList.add("is-wrong");
    }
    container.appendChild(span);
  }
}

async function onRoundAnswered(correct) {
  if (correct) {
    showInfo(`Раунд ${state.currentRound}: верно`);
  } else {
    if (state.currentRound === 1 || state.currentRound === 3) {
      showError(`Раунд ${state.currentRound}: ошибка. Правильный ответ показан ниже.`);
      setOptionButtonsDisabled(true);
      $("typing-answer").textContent = `Правильный ответ: ${state.sessionWord.translation}`;
      $("typing-answer").classList.remove("hidden");
      $("typing-next-wrap").classList.remove("hidden");
      state.pendingCorrect = false;
      return;
    }
    showError(`Раунд ${state.currentRound}: ошибка`);
  }
  await finalizeRound(correct);
}

async function finalizeRound(correct) {
  setOptionButtonsDisabled(false);
  $("typing-next-wrap").classList.add("hidden");
  $("typing-answer").classList.add("hidden");
  $("typing-answer").textContent = "";
  const payload = {
    word_id: state.sessionWord.word_id,
    round: state.currentRound,
    correct,
  };
  const res = await apiFetch(`/review`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    showError(await readError(res));
    return;
  }
  state.roundDone[state.currentRound] += 1;
  state.roundIndex[state.currentRound] += 1;
  await Promise.all([loadWords(), loadStats()]);
  await loadNextTrainingWord();
}

async function loadStats() {
  const res = await apiFetch(`/stats`);
  if (!res.ok) {
    showError(await readError(res));
    return;
  }
  const stats = await res.json();
  $("home-total").textContent = stats.total_words;
  $("home-due").textContent = stats.due_today;
  $("stats-total").textContent = stats.total_words;
  $("stats-due").textContent = stats.due_today;
  renderVocabBar(stats);
  renderRoundsChart(stats);
  renderLevelsChart(stats);
  if (document.getElementById("screen-stats")?.classList.contains("active")) {
    await loadActivity();
  }
}

// Rotates through the tense topics by day-of-year, so the suggestion changes
// daily but stays stable across repeated opens on the same day.
function pickDailyTopic(topics) {
  if (!topics || topics.length === 0) return null;
  const now = new Date();
  const startOfYear = new Date(now.getFullYear(), 0, 0);
  const dayOfYear = Math.floor((now - startOfYear) / 86400000);
  return topics[dayOfYear % topics.length];
}

async function loadDailyTips() {
  const content = $("tips-content");
  content.innerHTML = '<p class="tips-loading">Загружаю…</p>';

  const [statsRes] = await Promise.all([
    apiFetch(`/stats`),
    state.theoryLoaded
      ? Promise.resolve()
      : fetch(THEORY_SOURCE_URL)
          .then((res) => (res.ok ? res.json() : null))
          .then((data) => {
            if (data) {
              state.theoryData = data;
              state.theoryLoaded = true;
            }
          })
          .catch(() => {}),
  ]);

  const dueToday = statsRes.ok ? (await statsRes.json()).due_today : null;
  const topics = state.theoryData?.categories?.[0]?.topics || [];
  const dailyTopic = pickDailyTopic(topics);

  const items = [];
  if (dueToday === null) {
    items.push("Не удалось загрузить слова на сегодня.");
  } else if (dueToday > 0) {
    items.push(`📚 Слов к повторению сегодня: <strong>${dueToday}</strong>`);
  } else {
    items.push("📚 На сегодня слов к повторению нет — можно добавить новые.");
  }
  if (dailyTopic) {
    items.push(`📖 Грамматика дня: <strong>${escapeHtml(dailyTopic.title)}</strong>`);
  }

  content.innerHTML = items.map((item) => `<p class="tips-item">${item}</p>`).join("");
}

function renderVocabBar(stats) {
  const total = Number(stats.total_words) || 0;
  const mastered = Number(stats.mastered) || 0;
  const learning = Number(stats.learning) || 0;
  const fresh = Math.max(0, total - mastered - learning);
  const container = $("stats-vocab-bar");

  if (total === 0) {
    container.innerHTML = '<div class="stacked-bar stacked-bar-empty">Пока нет слов в словаре</div>';
    return;
  }

  const segments = [
    { label: "Новые", value: fresh, color: "var(--chart-new)" },
    { label: "Изучаются", value: learning, color: "var(--chart-learning)" },
    { label: "Выучены", value: mastered, color: "var(--chart-mastered)" },
  ];

  const bar = document.createElement("div");
  bar.className = "stacked-bar";
  for (const seg of segments) {
    if (seg.value <= 0) continue;
    const piece = document.createElement("div");
    piece.className = "stacked-bar-segment";
    piece.style.flexBasis = `${(seg.value / total) * 100}%`;
    piece.style.background = seg.color;
    piece.title = `${seg.label}: ${seg.value}`;
    bar.appendChild(piece);
  }

  const legend = document.createElement("div");
  legend.className = "chart-legend";
  for (const seg of segments) {
    const item = document.createElement("div");
    item.className = "chart-legend-item";
    item.innerHTML = `<span class="chart-legend-swatch" style="background:${seg.color}"></span>${seg.label}: <span class="chart-legend-value">${seg.value}</span>`;
    legend.appendChild(item);
  }

  container.innerHTML = "";
  container.appendChild(bar);
  container.appendChild(legend);
}

function renderBarChart(container, bars) {
  container.innerHTML = "";
  const max = Math.max(1, ...bars.map((b) => b.value));
  for (const b of bars) {
    const col = document.createElement("div");
    col.className = "bar-chart-col";
    const heightPct = Math.max(4, (b.value / max) * 100);
    col.innerHTML = `
      <div class="bar-chart-value">${b.value}</div>
      <div class="bar-chart-plot">
        <div class="bar-chart-bar" style="height:${heightPct}%; background:${b.color}" title="${b.label}: ${b.value}"></div>
      </div>
      <div class="bar-chart-label">${b.label}</div>
    `;
    container.appendChild(col);
  }
}

function renderRoundsChart(stats) {
  renderBarChart($("stats-rounds-chart"), [
    { label: "Раунд 1", value: Number(stats.round1_due) || 0, color: "var(--chart-seq-1)" },
    { label: "Раунд 2", value: Number(stats.round2_due) || 0, color: "var(--chart-seq-2)" },
    { label: "Раунд 3", value: Number(stats.round3_due) || 0, color: "var(--chart-seq-3)" },
    { label: "Раунд 4", value: Number(stats.round4_due) || 0, color: "var(--chart-seq-4)" },
  ]);
}

function renderLevelsChart(stats) {
  renderBarChart($("stats-levels-chart"), [
    { label: "Ур. 1", value: Number(stats.level1) || 0, color: "var(--chart-level-1)" },
    { label: "Ур. 2", value: Number(stats.level2) || 0, color: "var(--chart-level-2)" },
    { label: "Ур. 3", value: Number(stats.level3) || 0, color: "var(--chart-level-3)" },
    { label: "Ур. 4", value: Number(stats.level4) || 0, color: "var(--chart-level-4)" },
    { label: "Ур. 5", value: Number(stats.level5) || 0, color: "var(--chart-level-5)" },
  ]);
}

function buildUniqueOptions(correct, pool, size) {
  const unique = new Set([correct]);
  for (const item of shuffle(pool)) {
    if (unique.size >= size) {
      break;
    }
    unique.add(item);
  }
  return shuffle([...unique]);
}

function renderNoTrainingWords() {
  state.sessionWord = null;
  state.trainingCompleted = true;
  $("training-card").classList.remove("round2-mode");
  $("train-stage").textContent = "Раунды";
  $("train-session").textContent = "";
  $("train-word").textContent = "Нет слов для тренировки";
  $("train-prompt").textContent = "";
  $("typing-hint").classList.add("hidden");
  $("train-example").textContent = "";
  $("train-options").innerHTML = "";
  $("typing-block").classList.add("hidden");
  $("typing-answer").classList.add("hidden");
  $("typing-next-wrap").classList.add("hidden");
  $("speak-btn").classList.add("hidden");
  $("train-restart").classList.remove("hidden");
}

function renderTrainingComplete() {
  state.sessionWord = null;
  $("training-card").classList.remove("round2-mode");
  $("train-stage").textContent = "Раунды завершены";
  $("train-session").textContent = "";
  $("train-word").textContent = "Все 4 раунда завершены";
  $("train-prompt").textContent = "Вы можете начать новую сессию позже.";
  $("typing-hint").classList.add("hidden");
  $("train-example").textContent = "";
  $("train-options").innerHTML = "";
  $("typing-block").classList.add("hidden");
  $("typing-answer").classList.add("hidden");
  $("typing-next-wrap").classList.add("hidden");
  $("speak-btn").classList.add("hidden");
  $("train-restart").classList.remove("hidden");
}

function advanceRoundIfNeeded() {
  for (let round = state.currentRound; round <= 4; round += 1) {
    if (state.roundIndex[round] < state.roundWordIds[round].length) {
      state.currentRound = round;
      return true;
    }
  }
  return false;
}

function speakText(text) {
  if (!text) {
    return;
  }
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-US";
  speechSynthesis.speak(utterance);
}

function normalize(value) {
  return String(value).trim().toLowerCase().replace(/\s+/g, " ");
}

function stripTokenPunctuation(value) {
  return String(value).replace(/^[^\p{L}\p{N}']+|[^\p{L}\p{N}']+$/gu, "");
}

function normalizeTypingToken(value) {
  return normalize(stripTokenPunctuation(value));
}

function normalizeTypingPhrase(value) {
  return String(value)
    .trim()
    .split(/\s+/)
    .map(stripTokenPunctuation)
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function formatTypingAnswer(value) {
  return String(value).replace(/[.!?]+$/g, "").trim();
}

function shuffle(items) {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

const TOAST_DURATION_MS = 5000;

function showToast(text, type) {
  const container = $("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-text"></span>
    <button type="button" class="toast-close" aria-label="Закрыть">✕</button>
  `;
  toast.querySelector(".toast-text").textContent = text;

  const dismiss = () => {
    toast.classList.add("toast-hide");
    setTimeout(() => toast.remove(), 200);
  };
  const timer = setTimeout(dismiss, TOAST_DURATION_MS);
  toast.querySelector(".toast-close").addEventListener("click", () => {
    clearTimeout(timer);
    dismiss();
  });

  container.appendChild(toast);
}

function showError(text) {
  showToast(text, "error");
}

function showInfo(text) {
  showToast(text, "info");
}

async function readError(res) {
  try {
    const body = await res.json();
    return body.error || `error (${res.status})`;
  } catch {
    return `error (${res.status})`;
  }
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function detectAPIBase() {
  for (const candidate of ["/api/v1", "/api"]) {
    try {
      // /stats now requires auth — 401 still proves the route resolved (only a 404
      // means "wrong base path"), so check for that instead of res.ok.
      const res = await fetch(`${candidate}/stats`);
      if (res.status !== 404) {
        API_BASE = candidate;
        return;
      }
    } catch (_err) {
      // fallback on next candidate
    }
  }
}

function showLoginScreen() {
  document.body.classList.add("auth-flow");
  $("profile-wrap").classList.add("hidden");
  document.querySelector(".tabs").classList.add("hidden");
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $("screen-login").classList.add("active");
}

async function showApp() {
  document.body.classList.remove("auth-flow");
  $("profile-wrap").classList.remove("hidden");
  document.querySelector(".tabs").classList.remove("hidden");
  $("screen-login").classList.remove("active");
  $("screen-placement").classList.remove("active");
  switchScreen("home");
  await Promise.all([loadWords(), loadStats(), loadAIStatus()]);
}

async function showPlacement() {
  document.body.classList.add("auth-flow");
  $("profile-wrap").classList.add("hidden");
  document.querySelector(".tabs").classList.add("hidden");
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $("screen-placement").classList.add("active");

  const res = await apiFetch(`/placement/questions`);
  if (!res.ok) {
    // AI/API hiccup shouldn't trap the user — let them into the app, untested.
    await showApp();
    return;
  }
  const questions = await res.json();
  const container = $("placement-questions");
  container.innerHTML = questions
    .map(
      (q) => `
      <div class="placement-question" data-question-id="${q.id}">
        <div class="placement-question-text">${q.id}. ${escapeHtml(q.text)}</div>
        <div class="placement-options">
          ${q.options
            .map(
              (opt, idx) => `
            <label>
              <input type="radio" name="placement-q${q.id}" value="${idx}" />
              ${escapeHtml(opt)}
            </label>
          `
            )
            .join("")}
        </div>
      </div>
    `
    )
    .join("");
}

async function submitPlacement(answers) {
  const res = await apiFetch(`/placement/submit`, {
    method: "POST",
    body: JSON.stringify({ answers }),
  });
  if (!res.ok) {
    $("placement-message").textContent = await readError(res);
    $("placement-message").classList.remove("hidden");
    return;
  }
  await showApp();
}

$("placement-submit").addEventListener("click", async () => {
  const answers = {};
  document.querySelectorAll("#placement-questions .placement-question").forEach((block) => {
    const id = Number(block.dataset.questionId);
    const checked = block.querySelector("input[type=radio]:checked");
    if (checked) {
      answers[id] = Number(checked.value);
    }
  });
  await submitPlacement(answers);
});

$("placement-skip").addEventListener("click", async () => {
  await submitPlacement({});
});

async function bootstrap() {
  await detectAPIBase();
  if (!getAuthToken()) {
    showLoginScreen();
    return;
  }
  await enterAfterAuth();
}

// Decides between the placement quiz (first login, no level yet) and the main
// app, based on the freshly-fetched /auth/me. Clears the token and falls back
// to the login screen if the token turned out to be invalid/expired.
async function enterAfterAuth() {
  const res = await apiFetch(`/auth/me`);
  if (!res.ok) {
    setAuthToken(null);
    showLoginScreen();
    return;
  }
  const me = await res.json();
  state.user = me;
  if (!me.cefr_level) {
    await showPlacement();
    return;
  }
  await showApp();
}

function openProfileModal() {
  $("profile-name").value = state.user?.name || "";
  $("profile-email-input").value = state.user?.email || "";
  $("profile-save-status").textContent = "";
  $("profile-save-status").classList.remove("is-error");
  $("profile-modal").classList.remove("hidden");
}

function closeProfileModal() {
  $("profile-modal").classList.add("hidden");
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = $("login-email").value.trim();
  const password = $("login-password").value;
  const res = await apiFetch(`/auth/login`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    $("login-message").textContent = await readError(res);
    $("login-message").classList.remove("hidden");
    return;
  }
  const data = await res.json();
  setAuthToken(data.token);
  $("login-message").classList.add("hidden");
  await enterAfterAuth();
});

$("register-btn").addEventListener("click", async () => {
  const email = $("login-email").value.trim();
  const password = $("login-password").value;
  const res = await apiFetch(`/auth/register`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  const msg = $("login-message");
  msg.classList.remove("hidden");
  if (!res.ok) {
    msg.textContent = await readError(res);
    return;
  }
  msg.textContent = "Аккаунт создан, теперь войдите.";
});

$("logout-btn").addEventListener("click", async () => {
  try {
    await apiFetch(`/auth/logout`, { method: "POST" });
  } catch (_err) {
    // best-effort — stateless JWT, nothing to invalidate server-side anyway
  }
  setAuthToken(null);
  showLoginScreen();
});

async function loadAIStatus() {
  const el = $("chat-status");
  if (!el) return;
  try {
    const res = await apiFetch(`/ai/status`);
    if (!res.ok) {
      state.aiReady = false;
      el.className = "chat-status hidden";
      return;
    }
    const data = await res.json();
    state.aiReady = Boolean(data.ready);
    el.className = "chat-status hidden";
  } catch {
    state.aiReady = false;
    el.className = "chat-status hidden";
  }
}

function renderChatMessages() {
  const box = $("chat-messages");
  if (!box) return;
  box.innerHTML = "";
  state.chatMessages.forEach((msg) => {
    const row = document.createElement("div");
    row.className = `chat-row chat-row-${msg.role}`;
    const bubble = document.createElement("div");
    bubble.className = msg.quiz || msg.html ? "chat-bubble chat-bubble-quiz" : "chat-bubble";
    if (msg.text) {
      const textEl = document.createElement("div");
      textEl.textContent = msg.text;
      bubble.appendChild(textEl);
    }
    if (msg.html) {
      // Trusted markup only (e.g. a theory topic's pre-rendered content from
      // our own static JSON) — never raw user/AI text, which stays in .text.
      const htmlEl = document.createElement("div");
      htmlEl.className = "chat-bubble-html theory-topic-content";
      htmlEl.innerHTML = msg.html;
      bubble.appendChild(htmlEl);
    }
    if (msg.quiz) {
      bubble.appendChild(buildQuizMetaEl(msg.quiz));
      bubble.appendChild(buildQuizQuestionsEl(msg.quiz.questions));
    }
    row.appendChild(bubble);
    box.appendChild(row);
  });
  box.scrollTop = box.scrollHeight;
}

const PRACTICE_INTENT_RE =
  /(сгенерир|создай|составь|придума|сделай|дай|хочу).{0,25}(задани|упражнени|квиз|практик)/i;
const PRACTICE_LEVEL_RE = /\b(A1|A2|B1|B2|C1|C2)\b/i;

// Best-effort read of specific words the user named in their request (quoted,
// or after "слово(-ам)/по"), so "хочу практику по 'perennial'" uses that word
// instead of falling back to due/random ones from the dictionary.
function extractPracticeWordsFromText(text) {
  const quoted = [...text.matchAll(/['"«]([a-zA-Z][a-zA-Z' -]{1,30})['"»]/g)].map((m) => m[1].trim());
  if (quoted.length > 0) return quoted;

  const afterWords = text.match(/слов(?:а|ам|у|о)?\s*(?:по\s+)?[:\-]?\s*([a-zA-Z][a-zA-Z ,'-]{2,80})/i);
  if (afterWords) {
    const candidates = afterWords[1]
      .split(/\s*,\s*|\s+и\s+/i)
      .map((w) => w.trim())
      .filter((w) => /^[a-zA-Z][a-zA-Z' -]*$/.test(w));
    if (candidates.length > 0) return candidates;
  }
  return null;
}

function extractPracticeLevelFromText(text) {
  const match = text.match(PRACTICE_LEVEL_RE);
  return match ? match[1].toUpperCase() : null;
}

async function onChatSubmit(e) {
  e.preventDefault();
  if (state.chatStreaming) return;
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text) return;

  state.chatMessages.push({ role: "user", text });
  input.value = "";
  input.style.height = "auto";

  if (PRACTICE_INTENT_RE.test(text)) {
    // /practice/generate has a canonical fallback, so this works even without a live AI
    // connection — unlike the chat stream below, it doesn't need state.aiReady.
    const explicitWords = extractPracticeWordsFromText(text);
    const level = extractPracticeLevelFromText(text) || "B1";
    state.chatStreaming = true;
    $("chat-send").disabled = true;
    state.chatMessages.push({
      role: "assistant",
      text: explicitWords
        ? `Готовлю практику по словам: ${explicitWords.join(", ")}…`
        : "Готовлю практику по словам к повторению…",
    });
    renderChatMessages();
    try {
      const words = explicitWords || (await pickPracticeWords());
      await renderPractice(words, level);
    } finally {
      state.chatStreaming = false;
      $("chat-send").disabled = false;
    }
    return;
  }

  if (!state.aiReady) {
    renderChatMessages();
    showError("AI репетитор временно недоступен. Попробуйте позже.");
    return;
  }

  state.chatStreaming = true;
  $("chat-send").disabled = true;
  state.chatMessages.push({ role: "assistant", text: "" });
  renderChatMessages();

  const assistantIndex = state.chatMessages.length - 1;
  try {
    const res = await apiFetch(`/ai/chat/stream`, {
      method: "POST",
      body: JSON.stringify({ message: text }),
    });
    if (!res.ok) {
      throw new Error(await readError(res));
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const line = part.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        try {
          const event = JSON.parse(line.slice(6));
          if (event.type === "content" && event.content) {
            state.chatMessages[assistantIndex].text += event.content;
            renderChatMessages();
          }
          if (event.type === "status" && event.status) {
            $("chat-status").textContent = event.status;
          }
          if (event.type === "error" && event.error) {
            throw new Error(event.error);
          }
        } catch (parseErr) {
          if (parseErr?.message && !parseErr.message.includes("JSON")) {
            throw parseErr;
          }
        }
      }
    }
    if (!state.chatMessages[assistantIndex].text) {
      state.chatMessages[assistantIndex].text = "(пустой ответ)";
      renderChatMessages();
    }
  } catch (err) {
    state.chatMessages[assistantIndex].text = `Ошибка: ${err?.message || "не удалось получить ответ"}`;
    renderChatMessages();
    showError(err?.message || "Ошибка чата");
  } finally {
    state.chatStreaming = false;
    $("chat-send").disabled = false;
    await loadAIStatus();
  }
}

async function pickPracticeWords() {
  try {
    const res = await apiFetch(`/review/session?limit=8`);
    if (res.ok) {
      const data = await res.json();
      const words = (data.words || []).map((w) => w.word).filter(Boolean);
      if (words.length > 0) return words.slice(0, 5);
    }
  } catch {
    // no due words available — fall back to the vocabulary below
  }
  if (state.words.length === 0) {
    await loadWords();
  }
  const shuffled = [...state.words].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, 5).map((w) => w.word);
}

bootstrap();

async function loadActivity() {
  const res = await apiFetch(`/stats/activity?days=84`);
  if (!res.ok) {
    showError(await readError(res));
    return;
  }
  const data = await res.json();
  renderActivityCalendar(data);
}

function renderActivityCalendar(rows) {
  const map = new Map(rows.map((r) => [r.date, r.count]));
  const today = new Date();
  const days = [];
  for (let i = 83; i >= 0; i -= 1) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    days.push({ key, count: map.get(key) || 0, day: d.getDate() });
  }
  const maxCount = Math.max(1, ...days.map((d) => d.count));
  const calendar = $("activity-calendar");
  calendar.innerHTML = "";
  for (const day of days) {
    const cell = document.createElement("div");
    cell.className = "calendar-cell";
    const intensity = day.count / maxCount;
    const alpha = day.count === 0 ? 0.06 : 0.3 + intensity * 0.6;
    cell.style.backgroundColor = `rgba(57, 135, 229, ${alpha.toFixed(3)})`;
    cell.title = `${day.key}: ${day.count}`;
    cell.textContent = day.day;
    calendar.appendChild(cell);
  }

  const streak = computeStreak(days);
  const maxDay = Math.max(...days.map((d) => d.count), 0);
  $("stats-streak").textContent = `${streak} 🔥`;
  $("stats-max-day").textContent = String(maxDay);
}

function computeStreak(days) {
  let streak = 0;
  for (let i = days.length - 1; i >= 0; i -= 1) {
    if (days[i].count > 0) {
      streak += 1;
    } else {
      break;
    }
  }
  return streak;
}

async function renderPractice(words, level = "B1", introText = null) {
  const normalizedWords = Array.isArray(words) ? words.filter(Boolean) : [];
  const list = normalizedWords.length > 0 ? normalizedWords : ["perennial"];
  let data;
  try {
    data = await fetchPracticeSet(list, level);
  } catch (err) {
    showError(err?.message || "Не удалось сгенерировать практику");
    return;
  }
  state.chatMessages.push({
    text: introText || `Практика по словам: ${list.join(", ")}`,
    role: "assistant",
    quiz: data,
  });
  switchScreen("practice");
  renderChatMessages();
}

async function fetchPracticeSet(words, level = "B1") {
  const word = words[0];
  const res = await apiFetch(`/practice/generate`, {
    method: "POST",
    body: JSON.stringify({ word, word_list: words, level }),
  });
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return await res.json();
}

function buildQuizMetaEl(data) {
  const sourceLabel = data.source === "repetitor" ? "AI-репетитор" : "локальный шаблон";
  const materialsPart = Array.isArray(data.sources) && data.sources.length > 0
    ? ` · Материалы: ${data.sources.join(", ")}`
    : "";
  const el = document.createElement("div");
  el.className = "quiz-meta";
  el.textContent = `Источник: ${sourceLabel}${materialsPart}`;
  return el;
}

function buildQuizQuestionsEl(questions) {
  const container = document.createElement("div");
  container.className = "practice-quiz";
  (questions || []).forEach((q, qIdx) => {
    const block = document.createElement("div");
    block.className = "quiz-question";
    block.innerHTML = `
      <div class="quiz-prompt">${qIdx + 1}. ${escapeHtml(q.prompt || "")}</div>
      <div class="quiz-options"></div>
      <div class="quiz-explanation hidden"></div>
    `;
    const optionsWrap = block.querySelector(".quiz-options");
    const explanationEl = block.querySelector(".quiz-explanation");
    (q.options || []).forEach((option, optIdx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "practice-option-btn";
      btn.textContent = option;
      btn.addEventListener("click", () => {
        if (block.dataset.answered) return;
        block.dataset.answered = "true";
        optionsWrap.querySelectorAll("button").forEach((b, bIdx) => {
          if (bIdx === q.correct_index) {
            b.classList.add("correct");
          } else if (bIdx === optIdx) {
            b.classList.add("wrong");
          }
        });
        explanationEl.textContent = q.explanation || "";
        explanationEl.classList.remove("hidden");
      });
      optionsWrap.appendChild(btn);
    });
    container.appendChild(block);
  });
  return container;
}

