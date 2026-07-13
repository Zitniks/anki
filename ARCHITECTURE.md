# Anki Lite — архитектура и компоненты

Go-монолит для изучения английского по интервальным повторениям (SRS), с AI-функциями поверх
внешнего Python-бэкенда (`llm_service`/`adaptive-learning-repetitor`) через gRPC. Postgres,
Gin, JWT-аутентификация, vanilla-JS фронтенд + отдельный React-лендинг.

## Система целиком

```
Браузер
  ├─ / (React-лендинг, landing/dist)          — маркетинг, кнопка «Начать» → /app
  └─ /app (web/index.html + app.js, vanilla)  — сам продукт (SPA-подобный, без сборки)
         │ REST /api/v1/* (JWT в заголовке)
         ▼
   Go-монолит (cmd/server) ──gRPC (localhost:50051)──▶ llm_service (Python, отдельный репозиторий)
         │
         ▼
      Postgres (localhost:5434)
```

Go-сторона владеет словарём/SRS/аккаунтами. Вся «умная» часть (LLM, RAG, BKT/ALS mastery) —
на стороне Python; Go — тонкий gRPC-клиент, деградирует до фоллбэков при недоступности AI.

## Запуск / точка входа

`cmd/server/main.go`:
1. Читает `DATABASE_URL`, `JWT_SECRET` (обязательные, fatal при отсутствии); `DB_MAX_CONNS`/
   `DB_MIN_CONNS` — опциональные размеры пула.
2. Поднимает `pgxpool.Pool`, пингует, создаёт `storage.Repository`.
3. Синхронизирует слова из `anki_levels_and_lifecycle_cards.md` (если файл есть) на служебного
   пользователя `id=1` (`local@anki`) — легаси-импорт, не мешает обычным пользователям.
4. Создаёт `service.WordService`, `ai.Client` (gRPC-клиент к repetitor — best-effort, при сбое
   просто остаётся «не готов», сервер не падает).
5. Запускает фоновую горутину `service.RunEventPublisher` (см. ниже).
6. Роутинг: `/` → лендинг, `/app` → SPA, `/assets/*` и `/landing-assets/*` — статика без
   коллизий, `/api/v1/*` и `/api/*` — идентичный набор REST-роутов (второй префикс — для
   фронтендового автоопределения базового пути).

Переменные окружения: `DATABASE_URL`, `JWT_SECRET`, `DB_MAX_CONNS`, `DB_MIN_CONNS`, `HTTP_ADDR`
(default `:8080`), `REPETITOR_GRPC_ADDR` (default `localhost:50051`), `REPETITOR_EMAIL`,
`REPETITOR_PASSWORD`, `REPETITOR_PROJECT_ID`/`REPETITOR_CHAT_ID`/`REPETITOR_PRACTICE_CHAT_ID`
(опционально, для переиспользования уже созданной сессии).

## Структура `internal/`

| Пакет | Роль |
|---|---|
| `api/` | Gin-хендлеры — декодируют JSON, зовут `service`/`ai`, мапят ошибки в HTTP-статусы. Без бизнес-логики. |
| `auth/` | Stateless JWT (HS256, `golang-jwt/jwt/v5`, 30 дней) + bcrypt. `RequireAuth` middleware, `UserIDFromContext`. |
| `service/` | Бизнес-логика: SRS-переходы, валидация, постановка событий в очередь. Определяет интерфейс `Repository`, который реализует `storage.Repository`. |
| `storage/` | Один файл (`repository.go`, ~680 строк) — сырой SQL через `pgx/v5`, без ORM. |
| `model/` | Плоские структуры/enum'ы, общие для всех слоёв. |
| `placement/` | Детерминированный CEFR-тест (12 вопросов), без зависимости от AI — работает даже если repetitor недоступен. |
| `ai/` | gRPC-клиент к repetitor + сгенерированные protobuf-стабы (`ai/pb/`). |
| `review/` | Классический SM-2 калькулятор (`sm2.go`) — присутствует в коде, но **не используется** текущими флоу; `service.go` считает уровни своим алгоритмом с фиксированной лесенкой интервалов. |

### `api/` — файлы
- `handler.go` — CRUD слов, SRS-флоу (базовый и продвинутый), статистика, `PracticeGenerate`
  (генерация AI-квиза + канонический фоллбэк).
- `auth_handler.go` — `Register`/`Login`/`Logout` (stateless-заглушка)/`Me`.
- `ai_handler.go` — `AIStatus`, `AIChatStream` (SSE-проксирование чата).
- `enrich_handler.go` — `EnrichWord` (AI-черновик перевода/примера/транскрипции).
- `placement_handler.go` — вопросы/сабмит placement-теста.
- `rag_handler.go` — `ExplainError` (почему ответ неверный), `WeakTopics` (слабые темы из
  mastery-модели repetitor).

### `service/service.go`
`WordService` — единая точка бизнес-логики: аккаунты (`CreateUser`/`Authenticate`/
`GetUserByID`/`SetUserLevel`), CRUD слов, два независимых SRS-флоу:
- **Базовый** (4 раунда: `en_ru`/`ru_en`/`listening`/`cloze`).
- **Продвинутый** (3 раунда: `speaking`/`timed`/`speaking_cloze`, доступен только словам с
  накопленным уровнем ≥1).

Оба используют один и тот же `nextLevelState` — не SM-2, а своя лесенка интервалов
`[1,2,3,7,15,30,30,60]` дней, ключ — счётчик `Repetition` (растёт на верном ответе, падает на
неверном).

## Схема БД (Postgres, goose-миграции)

Порядок: `00001_init` → `00002_event_outbox` → `00003_multiuser` → `00004_placement`.
(Есть архив `migrations_sqlite_archive/` — проект изначально был на SQLite.)

| Таблица | Назначение |
|---|---|
| `users` | `id, email, password_hash (bcrypt), created_at, cefr_level (nullable)`. |
| `words` | Словарь, теперь с `user_id` (FK, `ON DELETE CASCADE`), уникальность `(user_id, word)`. |
| `cards` | По одной на `(word, тип раунда)` — 7 типов, создаются автоматически при добавлении слова. |
| `review_state` | Текущее SRS-состояние карточки (1:1 с `cards`) — `repetition`, `interval_days`, `next_review`, `status`. |
| `review_log` | Аппенд-лог каждого ответа — источник для статистики/streak. |
| `event_outbox` | Очередь learning-событий на отправку в repetitor (outbox-паттерн, см. ниже). |

## REST API

Всё под `/api/v1` и `/api` (идентично). Публично: `POST /auth/register`, `POST /auth/login`.
Всё остальное — за `RequireAuth`:

- **Auth**: `POST /auth/logout`, `GET /auth/me`
- **Placement**: `GET /placement/questions`, `POST /placement/submit`
- **Слова**: `GET|POST /words`, `POST /words/enrich`, `DELETE /words/:id`
- **Базовая тренировка**: `GET /review/next|session|card|round-stats`, `POST /review`
- **Продвинутая**: `GET /review/advanced/round-stats|next`, `POST /review/advanced`
- **Практика**: `POST /practice/generate`
- **AI/чат/RAG**: `GET /ai/status`, `POST /ai/chat/stream`, `POST /ai/explain-error`,
  `GET /ai/weak-topics`
- **Статистика**: `GET /stats`, `GET /stats/activity`

## Фронтенд

### `/app` — `web/index.html` + `web/app.js` (vanilla, без сборки)

Экраны переключаются через `switchScreen(name)` (класс `.screen`/`.screen.active`), стейт — один
объект `state` + `localStorage` (JWT-токен, autoplay, статистика письма).

- **Логин** — email/пароль, JWT в `localStorage`, `apiFetch` авто-подставляет
  `Authorization` и редиректит на логин при 401.
- **Placement-тест** — показывается один раз, при первом входе без `cefr_level`.
- **Главная** — сводка (слов всего/к повторению), кнопка начать тренировку.
- **Словарь** — таблица слов с поиском и удалением.
- **Добавить** — форма + кнопка «✨ Заполнить через AI».
- **Тренировка** (базовая, 4 раунда) — узнавание, перевод-набор, аудирование, cloze-продакшн;
  кнопка «Почему?» дёргает RAG-объяснение неверного ответа.
- **Продвинутая** (3 раунда) — speech-to-text через Web Speech API, таймер, cloze с речью.
- **Письмо** — перевод на английский, фильтр по временам (данные из `/tense.md`).
- **Статистика письма** — локальная (localStorage), не завязана на бэкенд.
- **Статистика** — общие цифры, разбивка по раундам/уровням, streak, activity-календарь.
- **Слабые темы** — топ слабых слов из mastery-модели repetitor.
- **Практика (AI-квиз)** — форма настройки → полноэкранный режим с 5 сгенерированными
  MCQ-вопросами (клик по варианту — зелёный/красный + объяснение) и историей чата рядом.
- **Плавающий чат** — иконка 💬 внизу справа, доступна на всех экранах приложения (кроме
  логина/placement), открывает панель с тем же чатом, что и в полноэкранной практике —
  один и тот же DOM-виджет переиспользуется, а не дублируется.

`detectAPIBase()` при загрузке пробует `/api/v1` и `/api`, закрепляет рабочий вариант.

### `/` — `landing/` (React, отдельный проект)

Маркетинговая страница перед входом. Стек: Vite 8 + React 19 + TypeScript, Tailwind CSS 4
(`@tailwindcss/vite`), ручной shadcn/ui-стиль (`class-variance-authority`/`clsx`/`tailwind-merge`,
компоненты в `landing/src/components/ui/`). Сборка → `landing/dist`, отдаётся Go напрямую
(`index.html` на `/`, ассеты на `/landing-assets` — намеренно другой префикс, чтобы не
конфликтовать с `/assets`, который уже занят под `web/`).

## gRPC-интеграция (`internal/ai/grpc_client.go`)

| RPC | Кто вызывает | Что делает |
|---|---|---|
| `EnsureSession` | при старте (`bootstrap`) | Аутентификация в repetitor, резолв `project_id`/`chat_id`/`practice_chat_id`. |
| `Chat` (стрим) | `AIChatStream` | Стриминг чата, транслируется в SSE. |
| `GeneratePractice` | `PracticeGenerate` | 5 MCQ-вопросов с объяснениями (RAG-обоснованные). |
| `PublishEvent` | фоновый воркер | Одно learning-событие → BKT/ALS в repetitor. |
| `ExplainError` | `/ai/explain-error` | Объяснение, почему ответ неверный. |
| `GetWeakTopics` | `/ai/weak-topics` | Слабые слова/темы по mastery-модели. |
| `EnrichWord` | `/words/enrich` | AI-черновик перевода/примера/транскрипции. |
| `SearchRag` | `fillClozeFromRag` (внутри `ReviewCard`) | Живой пример из Example RAG, когда у слова нет статичного примера. |
| `Health` | — | Проверка доступности (нигде не вызывается в текущих хендлерах). |

## Фоновый воркер (`internal/service/event_publisher.go`)

Outbox-паттерн: `SubmitReview`/`SubmitAdvancedReview` синхронно пишут строку в `event_outbox`
(быстрая локальная транзакция, без сети) — сам ответ студенту не ждёт repetitor. Отдельная
горутина каждые 3 секунды вычитывает до 20 неотправленных строк (`publish_attempts < 10`) и
шлёт их через `PublishEvent`; при неудаче инкрементит счётчик попыток и пробует на следующем
тике. Гарантирует, что недоступность AI-бэкенда не блокирует и не роняет тренировку.
