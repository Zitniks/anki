# ТЗ: Достройка Anki Lite (Go) — новые режимы и интеграция с repetitor

**Проект:** Anki Lite
**Компонент:** Go-монолит (`cmd/server`), достройка в текущей архитектуре
**База:** Gin + SQLite (goose) + gRPC-клиент к `adaptive-learning-repetitor`
**Принцип:** не переписываем, а достраиваем. Текущие режимы (SRS, письмо, чат, практика) остаются как есть.

---

## 0. Контекст и что уже есть

Работает: словарь (CRUD), тренировка (4 раунда SRS), продвинутая (3 раунда), письмо,
статистика, чат и практика через repetitor по gRPC. Данные — локальный SQLite, один пользователь.

Repetitor (Python) уже умеет: LangGraph-агент, три RAG-корпуса (EXERCISE / EXAMPLE / EXPLANATION),
BKT/ALS/topic_mastery, `Chat` / `GeneratePractice` / `SearchRag` по gRPC.

**Ключевое ограничение сегодня:** Anki и repetitor живут в параллельных мирах. Anki считает SRS
локально и никогда не сообщает repetitor об успехах студента. BKT/ALS в repetitor есть, но
пустуют — их никто не кормит.Половина мощности AI простаивает.

---

## 1. Что достраиваем (скоуп)

| # | Фича | Суть | Ломает ли текущее |
|---|---|---|---|
| A | **AI-обогащение слов** | при добавлении слова repetitor заполняет пример/транскрипцию/перевод | нет, дополняет |
| B | **SRS → repetitor (learning events)** | тренировка шлёт события ответов, BKT/ALS считают mastery | нет, добавляет вызовы |
| C | **Новые RAG-режимы** | разбор ошибок, контекстные примеры, повторение слабых тем | нет, новые экраны |
| D | **Многопользовательскость** | аккаунты, изоляция данных, синхронизация | **да** — меняет модель данных |

Порядок реализации в §9 выстроен от наименее разрушительного (A) к самому тяжёлому (D).

---

## 2. Границы (что НЕ делаем)

- Не переписываем SRS-алгоритм — интервалы и раунды остаются как есть.
- Не переносим бизнес-логику mastery в Anki — BKT/ALS живут только в repetitor.
- Не дублируем RAG в Go — весь поиск и генерация на стороне repetitor, Anki проксирует.
- Не трогаем существующие миграции `00001`–`00005` — только новые поверх.
- Многопользовательскость (D) не тащит за собой обязательное облако — сначала локальные аккаунты,
  синхронизация отдельным под-этапом.

---

## 3. Архитектура после достройки

```
┌──────────────────────────────────────────────────────────┐
│  Браузер (SPA)                                            │
│  + экран «Разбор ошибок», «Слабые темы», кнопка «AI» в    │
│    форме добавления слова, экран логина (этап D)          │
└───────────────────────────┬──────────────────────────────┘
                            │ HTTP /api/v1/*  (+ Bearer token на этапе D)
┌───────────────────────────▼──────────────────────────────┐
│  Anki Go (монолит, cmd/server)                           │
│                                                          │
│  api/            handler.go, ai_handler.go               │
│                  + enrich_handler.go   (фича A)           │
│                  + auth_handler.go     (фича D)           │
│  service/        SRS + раунды                            │
│                  + event_publisher.go  (фича B)           │
│                  + enrich_service.go   (фича A)           │
│  ai/grpc_client  + EnrichWord, PublishEvent, GetWeakTopics│
│  storage/        SQLite; + users, sessions (фича D)      │
│  auth/           JWT, middleware       (фича D)           │
└──────────────┬────────────────────────┬──────────────────┘
               │ SQLite                  │ gRPC :50051
               ▼                         ▼
        локальные данные          adaptive-learning-repetitor
        (words, cards, SRS,       (LLM, RAG, BKT/ALS,
         users на этапе D)         topic_mastery)
```

Принцип: **Anki остаётся владельцем словаря и SRS. Repetitor остаётся владельцем AI и mastery.**
Новые фичи — это новые мосты между двумя мирами, а не перенос логики.

---

## 4. Фича A — AI-обогащение слов

### 4.1 Задача

При добавлении слова студент часто оставляет пустыми `example`, `transcription`, а иногда
хочет проверить перевод. Repetitor (LLM + RAG) может заполнить это автоматически.

### 4.2 Поток

```
POST /api/v1/words/enrich   { "word": "resilient" }
   → Go: grpc EnrichWord(word)
      → repetitor: LLM + Example RAG → { translation, example, transcription }
   → Go возвращает черновик, НЕ сохраняет
   → студент правит и жмёт «Сохранить» → обычный POST /words
```

Обогащение — **черновик для предпросмотра**, не автосохранение. Студент контролирует что попадёт
в словарь. Это защищает от галлюцинаций LLM.

### 4.3 gRPC-контракт (добавить в tutor.proto)

```protobuf
rpc EnrichWord (EnrichWordRequest) returns (EnrichWordResponse);

message EnrichWordRequest {
  string word  = 1;
  string level = 2;   // CEFR, опционально, для подбора примера по уровню
}

message EnrichWordResponse {
  string translation   = 1;
  string example       = 2;   // с ___ на месте изучаемого слова
  string transcription = 3;
  string source        = 4;   // "rag" | "llm" | "fallback"
}
```

### 4.4 REST (Anki)

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| POST | `/api/v1/words/enrich` | `{word, level?}` | `{translation, example, transcription, source}` |

### 4.5 Поведение при недоступном repetitor

Кнопка «AI-заполнить» показывает ошибку, форма остаётся заполняемой вручную. Обогащение —
удобство, не блокер добавления слова.

### 4.6 UI

В `#screen-add` рядом с полем Word — кнопка «✨ Заполнить через AI». По клику: спиннер →
поля Translation / Example / Transcription заполняются черновиком, помечаются «AI, проверьте».

---

## 5. Фича B — SRS → repetitor (learning events)

### 5.1 Задача

Каждый ответ в тренировке — это сигнал о знании слова. Сейчас он оседает только в локальном
`review_log`. Нужно дублировать его в repetitor, чтобы BKT/ALS строили модель знаний, а фичи C
(слабые темы, рекомендации) получили данные.

### 5.2 Что считать «темой» для BKT

BKT работает по темам (topic), а Anki оперирует словами. Нужен маппинг. Варианты:

- **Слово = тема** — каждое слово отдельная тема. Просто, но тем тысячи, mastery размажется.
- **Грамматическое время = тема** (для письма/cloze) — есть в `tense.md`.
- **CEFR-уровень + часть речи = тема** — грубее, но агрегируется.

**Решение для MVP:** слово = тема (`topic = "word:{word}"`). Repetitor уже хранит topic_mastery
по строковому ключу, схема не меняется. Позже можно ввести иерархию.

### 5.3 Поток

```
POST /review  (студент ответил)
   → Go: пишет review_log + обновляет review_state  (как сейчас)
   → Go: АСИНХРОННО grpc PublishEvent(word, correct, response_time)
      → repetitor: /analytics/events → BKT обновляет P(know)
```

Ключевое — **асинхронность**. Публикация события не должна тормозить ответ студенту и не должна
ронять тренировку если repetitor лёг. Fire-and-forget с очередью и ретраями.

### 5.4 gRPC-контракт

```protobuf
rpc PublishEvent (PublishEventRequest) returns (PublishEventResponse);

message PublishEventRequest {
  string word          = 1;
  bool   correct       = 2;
  int32  response_time_ms = 3;
  int32  attempts      = 4;
  string card_type     = 5;   // en_ru, ru_en, cloze, ...
  string difficulty    = 6;   // easy | medium | hard
}

message PublishEventResponse {
  bool accepted = 1;
}
```

### 5.5 Надёжность — очередь событий

Не звать gRPC прямо в обработчике ответа. Вместо этого:

```
service/event_publisher.go
  - буферизированный канал chan Event (size N)
  - воркер-горутина читает канал, шлёт gRPC
  - при ошибке: ретрай с backoff, при переполнении — дроп с логом
  - при старте: не блокирует, если repetitor недоступен
```

Локальный SRS — источник истины. Repetitor — вторичный потребитель. Потеря события не ломает
обучение, просто mastery чуть отстанет.

### 5.6 Миграция (опционально)

Для гарантии доставки — таблица исходящих событий (outbox pattern):

```sql
-- 00006_event_outbox.sql
CREATE TABLE event_outbox (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    word          TEXT NOT NULL,
    correct       INTEGER NOT NULL,
    response_time_ms INTEGER,
    card_type     TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    published_at  DATETIME,          -- NULL = ещё не отправлено
    attempts      INTEGER DEFAULT 0
);
CREATE INDEX idx_outbox_unpublished ON event_outbox (published_at) WHERE published_at IS NULL;
```

Воркер читает неотправленные, шлёт, проставляет `published_at`. Переживает перезапуск сервера.

---

## 6. Фича C — новые RAG-режимы

Три экрана, каждый использует уже готовые RAG-корпуса repetitor через gRPC. Логика на стороне
repetitor, Anki — тонкий клиент.

### 6.1 Разбор ошибок (Explanation RAG)

**Когда:** студент ошибся в cloze или ru_en. Вместо простого «неверно» — объяснение.

```
студент ошибся: ждали "have been", ввёл "have being"
   → POST /api/v1/ai/explain-error  {word, expected, got, sentence}
      → grpc Chat / SearchRag(EXPLANATION)  → объяснение из knowledge_docs
   → показать под карточкой: почему ошибка, правило
```

Не блокирует тренировку — объяснение по кнопке «Почему?», не автоматически.

### 6.2 Контекстные примеры (Example RAG)

**Когда:** в cloze-раунде у слова пустой `example` (сейчас такие молча пропускаются, §5.4 OVERVIEW).

```
нет статичного example → grpc SearchRag(EXAMPLE, word)
   → живое предложение из example_bank → используется как cloze на лету
```

Оживляет слова без примеров — их сейчас теряется целый раунд.

### 6.3 Повторение слабых тем (RAG + mastery)

**Когда:** отдельный экран «Слабые темы». Требует фичу B (иначе mastery пустой).

```
GET /api/v1/ai/weak-topics
   → grpc GetWeakTopics()  → repetitor: topic_mastery где P(know) низкий
   → список слов + кнопка «Проработать» → генерит практику (GeneratePractice) по ним
```

### 6.4 gRPC-контракт (добавить)

```protobuf
rpc GetWeakTopics (GetWeakTopicsRequest) returns (GetWeakTopicsResponse);
rpc ExplainError  (ExplainErrorRequest)  returns (ExplainErrorResponse);

message GetWeakTopicsRequest  { int32 limit = 1; }
message WeakTopic { string word = 1; double p_know = 2; double als = 3; }
message GetWeakTopicsResponse { repeated WeakTopic topics = 1; }

message ExplainErrorRequest {
  string word = 1; string expected = 2; string got = 3; string sentence = 4;
}
message ExplainErrorResponse { string explanation = 1; string source = 2; }
```

### 6.5 REST (Anki)

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/v1/ai/explain-error` | Разбор ошибки (Explanation RAG) |
| GET | `/api/v1/ai/example?word=` | Живой пример (Example RAG) |
| GET | `/api/v1/ai/weak-topics` | Слабые темы из mastery |

---

## 7. Фича D — многопользовательскость

Самая тяжёлая: ломает фундаментальное допущение «один пользователь, один SQLite».

### 7.1 Решение об изоляции данных

Два подхода:

- **Один SQLite, колонка `user_id` везде** — проще кодить, но WAL + один файл плохо масштабируется
  под конкурентную запись многих юзеров.
- **SQLite на пользователя** (`data/{user_id}/anki.db`) — изоляция бесплатно, масштаб лучше, но
  сложнее бэкапы и миграции.

**Решение для MVP:** один SQLite + `user_id` во всех таблицах данных. Это меньше кода и достаточно
для десятков пользователей. Переезд на файл-на-юзера или Postgres — если упрёмся.

### 7.2 Миграция

```sql
-- 00007_multiuser.sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,       -- bcrypt
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
    token       TEXT PRIMARY KEY,      -- или JWT без хранения
    user_id     INTEGER NOT NULL REFERENCES users(id),
    expires_at  DATETIME NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- добавить user_id в существующие таблицы
ALTER TABLE words       ADD COLUMN user_id INTEGER REFERENCES users(id);
ALTER TABLE review_log  ADD COLUMN user_id INTEGER REFERENCES users(id);
-- cards, review_state наследуют через word_id → words.user_id

-- дефолтный пользователь для существующих данных (миграция без потерь)
INSERT INTO users (id, email, password_hash) VALUES (1, 'local@anki', '');
UPDATE words      SET user_id = 1 WHERE user_id IS NULL;
UPDATE review_log SET user_id = 1 WHERE user_id IS NULL;
```

Существующие данные не теряются — уезжают под дефолтного пользователя id=1.

### 7.3 Auth

```
auth/jwt.go         — генерация/валидация JWT
auth/middleware.go  — Gin middleware: извлечь user_id из Bearer, положить в контекст
api/auth_handler.go — POST /register, POST /login, POST /logout
```

Каждый запрос данных фильтруется по `user_id` из токена. Repetitor тоже получает `user_id` в
gRPC-вызовах, чтобы mastery/RAG были персональными (у repetitor уже есть проекты/пользователи —
маппим Anki user → repetitor project).

### 7.4 REST (Anki)

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/api/v1/auth/register` | `{email, password}` → создать юзера |
| POST | `/api/v1/auth/login` | `{email, password}` → `{token}` |
| POST | `/api/v1/auth/logout` | инвалидация сессии |
| GET | `/api/v1/auth/me` | текущий пользователь |

Все существующие `/words`, `/review/*`, `/stats` получают middleware и фильтр по `user_id`.

### 7.5 Синхронизация (под-этап, опционально)

После аккаунтов — синхронизация между устройствами. Простейший вариант: сервер уже центральный
(данные в его SQLite), значит «синхронизация» = просто вход под тем же аккаунтом с другого
устройства. Настоящий offline-first sync (CRDT, версионирование) — отдельная большая задача, вне
MVP.

---

## 8. Сводка изменений в gRPC-контракте

Добавляем в `proto/tutor/v1/tutor.proto` (repetitor должен реализовать серверную часть):

| RPC | Тип | Фича | Назначение |
|---|---|---|---|
| `EnrichWord` | unary | A | автозаполнение слова |
| `PublishEvent` | unary | B | learning event → BKT/ALS |
| `ExplainError` | unary | C | разбор ошибки |
| `GetWeakTopics` | unary | C | слабые темы из mastery |

Существующие (`Health`, `EnsureSession`, `Chat`, `GeneratePractice`, `SearchRag`) — без изменений.
На этапе D во все вызовы добавляется `user_id` / `project_id`.

---

## 9. Этапы реализации

### Этап 1 — Фича A (AI-обогащение) · наименее рискованный
- proto: `EnrichWord` + перегенерация stubs
- `ai/grpc_client.go`: метод `EnrichWord`
- `api/enrich_handler.go` + роут `POST /words/enrich`
- UI: кнопка «AI-заполнить» в `#screen-add`
- **Результат:** слова заполняются автоматически, ничего старого не сломано

### Этап 2 — Фича B (learning events) · средний риск
- proto: `PublishEvent`
- `service/event_publisher.go`: канал + воркер + ретраи
- миграция `00006_event_outbox.sql` (outbox для надёжности)
- врезка в обработчик `POST /review` (fire-and-forget)
- **Результат:** BKT/ALS в repetitor наполняются данными

### Этап 3 — Фича C (RAG-режимы) · зависит от B для «слабых тем»
- proto: `ExplainError`, `GetWeakTopics`
- 3.1 Разбор ошибок → кнопка «Почему?» в тренировке
- 3.2 Контекстные примеры → fallback в cloze при пустом example
- 3.3 Экран «Слабые темы» (нужен наполненный mastery из этапа 2)
- **Результат:** AI-режимы поверх готовых RAG

### Этап 4 — Фича D (многопользовательскость) · самый тяжёлый, ломающий
- миграция `00007_multiuser.sql` (users, sessions, user_id)
- `auth/`: JWT + middleware
- `api/auth_handler.go`: register/login/logout/me
- врезка middleware во все data-роуты + фильтр по user_id
- маппинг Anki user → repetitor project во всех gRPC-вызовах
- UI: экран логина/регистрации
- **Результат:** несколько пользователей, изоляция данных

### Этап 5 — Синхронизация (опционально)
- вход с разных устройств под одним аккаунтом (центральный сервер)
- offline-first sync — вынести в отдельное ТЗ если понадобится

---

## 10. Риски и решения

| Риск | Решение |
|---|---|
| repetitor лёг → тренировка встала | Все AI-вызовы опциональны и асинхронны; SRS работает автономно |
| PublishEvent тормозит ответ студенту | Fire-and-forget через канал+воркер, не в hot path |
| Потеря learning events при рестарте | Outbox-таблица `event_outbox`, воркер добивает недоставленное |
| LLM галлюцинирует при обогащении | Обогащение — черновик для проверки, не автосохранение |
| Многопользовательскость ломает данные | Дефолтный user id=1, старые данные мигрируют без потерь |
| SQLite не тянет много юзеров | MVP на один файл + user_id; переезд на файл-на-юзера/Postgres при росте |
| «Слово = тема» размывает mastery | Осознанный MVP-компромисс; иерархия тем — позже |
| GigaChat роняет второй SystemMessage | Известно из repetitor; провайдер Yandex, врезку контекста не менять до смены LLM |

---

## 11. Что меняется в структуре репозитория

```
anki/
├── internal/
│   ├── api/
│   │   ├── enrich_handler.go     + фича A
│   │   └── auth_handler.go       + фича D
│   ├── service/
│   │   ├── event_publisher.go    + фича B (канал, воркер, ретраи)
│   │   └── enrich_service.go     + фича A
│   ├── auth/                     + фича D
│   │   ├── jwt.go
│   │   └── middleware.go
│   └── ai/grpc_client.go         + EnrichWord, PublishEvent, ExplainError, GetWeakTopics
├── migrations/
│   ├── 00006_event_outbox.sql    + фича B
│   └── 00007_multiuser.sql       + фича D
├── proto/tutor/v1/tutor.proto    + 4 новых RPC
└── web/
    ├── index.html                + экраны «Слабые темы», логин; кнопка AI в «Добавить»
    └── app.js                    + логика новых экранов
```

---

## 12. Определения готовности (DoD)

| Фича | Готово когда |
|---|---|
| A | Слово заполняется через AI, черновик правится, repetitor недоступен → ручной ввод работает |
| B | Ответ в тренировке порождает событие в repetitor; рестарт сервера не теряет события (outbox) |
| C | Ошибка даёт объяснение; пустой example подхватывает RAG-пример; экран слабых тем показывает данные |
| D | Регистрация/логин работают; данные изолированы по user_id; старые данные под user id=1 не потеряны |
```
