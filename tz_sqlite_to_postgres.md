# ТЗ: Миграция Anki Lite с SQLite на PostgreSQL

**Проект:** Anki Lite (Go)
**Задача:** заменить SQLite на отдельный PostgreSQL (своя БД, рядом с repetitor)
**Данные:** миграция существующих НЕ требуется — стартуем с чистой БД
**Принцип:** меняем слой хранения и диалект SQL. Бизнес-логика, REST, gRPC, фронтенд — без изменений.

---

## 0. Зачем

SQLite не тянет конкурентную запись многих пользователей (одно WAL-соединение). Раз впереди
многопользовательскость (фича D из `tz_anki_go.md`), переход на Postgres снимает узкое место
заранее. Отдельная БД Anki, не общая с repetitor — чтобы границы владения данными оставались
чёткими (Anki владеет словарём и SRS, repetitor — AI и mastery).

---

## 1. Что меняется, что нет

### Затронуто

| Область | Было (SQLite) | Стало (Postgres) |
|---|---|---|
| Драйвер | `mattn/go-sqlite3` (cgo) | `jackc/pgx/v5` (pure Go) |
| Соединение | одно, WAL | пул `pgxpool` |
| Миграции | goose, SQLite-диалект | goose, Postgres-диалект |
| Плейсхолдеры | `?` | `$1, $2, ...` |
| Автоинкремент | `INTEGER PK AUTOINCREMENT` | `BIGSERIAL` / `GENERATED ALWAYS AS IDENTITY` |
| Даты | `DATETIME` (текст) | `TIMESTAMPTZ` |
| Булевы | `INTEGER` 0/1 | `BOOLEAN` |
| Upsert | `INSERT ... ON CONFLICT` | тот же, но строже к синтаксису |
| Рантайм-DDL | `EnsureAdvancedSchema` при старте | нормальная миграция |

### НЕ затронуто

- SRS-алгоритм (интервалы, раунды, learning_step)
- `service/service.go` — бизнес-логика (кроме сигнатур если репозиторий их меняет)
- REST API (`/api/v1/*`) — контракт тот же
- gRPC с repetitor — не при чём
- Фронтенд (`web/`) — вообще не трогаем
- Repetitor и его Postgres — отдельный проект, живёт как есть

---

## 2. Стек и зависимости

```
Драйвер:    github.com/jackc/pgx/v5
Пул:        github.com/jackc/pgx/v5/pgxpool
Миграции:   goose (остаётся; provider = postgres)
```

Опционально, чтобы не писать `$1,$2` руками и не мапить строки:
```
Query-билдер: github.com/Masterminds/squirrel   (опционально)
Или sqlc:     генерация типобезопасного кода из SQL (рекомендуется на будущее)
```

Для MVP достаточно чистого `pgx` без ORM.

---

## 3. Конфигурация

### 3.1 `.env` (было)

```env
DB_PATH=./anki.db
```

### 3.2 `.env` (стало)

```env
# отдельный Postgres для Anki
DATABASE_URL=postgres://anki:anki_pass@localhost:5434/anki?sslmode=disable

# пул соединений
DB_MAX_CONNS=10
DB_MIN_CONNS=2
```

Порт `5434`, чтобы не конфликтовать с Postgres repetitor (у него `5433` по OVERVIEW). Разные
инстансы — разные порты.

### 3.3 docker-compose (добавить сервис)

```yaml
services:
  anki-db:
    image: postgres:16
    environment:
      POSTGRES_DB: anki
      POSTGRES_USER: anki
      POSTGRES_PASSWORD: anki_pass
    ports: ["5434:5432"]
    volumes: [anki_pgdata:/var/lib/postgresql/data]
    restart: unless-stopped

volumes:
  anki_pgdata:
```

Обычный postgres:16 — pgvector не нужен, векторный поиск живёт в repetitor.

---

## 4. Схема БД (Postgres, чистая)

Собираем всю схему заново под Postgres-диалект. Порядок таблиц — с учётом FK.

### 4.1 words

```sql
CREATE TABLE words (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    word          TEXT UNIQUE NOT NULL,
    translation   TEXT NOT NULL,
    example       TEXT,
    transcription TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.2 cards

```sql
CREATE TABLE cards (
    id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    word_id  BIGINT NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    type     TEXT NOT NULL,   -- en_ru, ru_en, listening, cloze, speaking, timed, speaking_cloze
    UNIQUE (word_id, type)
);
```

### 4.3 review_state

```sql
CREATE TABLE review_state (
    card_id       BIGINT PRIMARY KEY REFERENCES cards(id) ON DELETE CASCADE,
    repetition    INTEGER NOT NULL DEFAULT 0,
    interval_days INTEGER NOT NULL DEFAULT 0,   -- 'interval' — зарезервировано в SQL, переименовать
    next_review   TIMESTAMPTZ,
    correct_count INTEGER NOT NULL DEFAULT 0,
    wrong_count   INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'new',  -- new, learning, review, relearning
    learning_step INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_review_state_due ON review_state (next_review);
```

**Внимание:** `interval` — зарезервированное слово в Postgres. Колонку переименовать в
`interval_days` (или экранировать кавычками, но переименование чище). Это правка в SQL и в
репозитории.

### 4.4 review_log

```sql
CREATE TABLE review_log (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    card_id          BIGINT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    word_id          BIGINT NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    quality          INTEGER,
    rating           INTEGER,
    response_time_ms INTEGER,
    reviewed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_review_log_reviewed ON review_log (reviewed_at);
CREATE INDEX idx_review_log_word ON review_log (word_id);
```

### 4.5 Миграции goose (Postgres)

Переписать существующие `00001`–`00005` + рантайм-`EnsureAdvancedSchema` в единый набор под
Postgres. Так как данные не переносим — можно схлопнуть в чистую последовательность:

| Файл | Содержание |
|---|---|
| `00001_init.sql` | words, cards, review_state, review_log (вся базовая схема сразу) |
| `00002_advanced_cards.sql` | (если нужно отдельно) типы speaking/timed/speaking_cloze — но их можно включить в 00001 |

Рантайм-DDL `EnsureAdvancedSchema` **убираем** — всё в миграциях. Схема не должна меняться при
старте сервера.

---

## 5. Изменения в коде

### 5.1 storage/repository.go — главный объём работы

Механические, но повсеместные правки:

```go
// БЫЛО (SQLite, database/sql + mattn)
db, err := sql.Open("sqlite3", dbPath)
row := db.QueryRow("SELECT id FROM words WHERE word = ?", word)

// СТАЛО (Postgres, pgx)
pool, err := pgxpool.New(ctx, databaseURL)
row := pool.QueryRow(ctx, "SELECT id FROM words WHERE word = $1", word)
```

Ключевые правки во всех методах репозитория:
- `?` → `$1, $2, ...` (нумерованные плейсхолдеры)
- `db.Query/QueryRow/Exec` → `pool.Query/QueryRow/Exec` + первым аргументом `ctx`
- `sql.Rows` → `pgx.Rows`, `rows.Scan` в целом совместим
- `LastInsertId()` не работает в Postgres → использовать `INSERT ... RETURNING id`
- булевы: передавать `bool`, а не `int`; сканировать в `bool`

### 5.2 INSERT ... RETURNING (важная правка)

```go
// БЫЛО
res, _ := db.Exec("INSERT INTO words(word, translation) VALUES(?, ?)", w, t)
id, _ := res.LastInsertId()

// СТАЛО
var id int64
pool.QueryRow(ctx,
    "INSERT INTO words(word, translation) VALUES($1, $2) RETURNING id",
    w, t).Scan(&id)
```

### 5.3 Upsert (синхронизация словаря при старте)

Автозагрузка слов из `anki_levels_and_lifecycle_cards.md` использует upsert. Postgres-синтаксис:

```sql
INSERT INTO words (word, translation)
VALUES ($1, $2)
ON CONFLICT (word)
DO UPDATE SET translation = EXCLUDED.translation;
```

### 5.4 Контекст везде

pgx требует `context.Context` первым аргументом каждого вызова. Если сервисный слой его ещё не
прокидывает — добавить `ctx` в сигнатуры методов репозитория. Это может затронуть `service.go`.

### 5.5 Пул вместо одного соединения

```go
// cmd/server/main.go
cfg, _ := pgxpool.ParseConfig(os.Getenv("DATABASE_URL"))
cfg.MaxConns = 10
cfg.MinConns = 2
pool, err := pgxpool.NewWithConfig(ctx, cfg)
defer pool.Close()
```

Пул убирает главную боль SQLite — конкурентная запись теперь безопасна.

---

## 6. Ловушки диалекта (чек-лист)

| Ловушка | Решение |
|---|---|
| `interval` — зарезервированное слово | переименовать колонку в `interval_days` |
| `LastInsertId()` не существует | `INSERT ... RETURNING id` |
| `?` плейсхолдеры | заменить на `$1, $2` |
| `AUTOINCREMENT` нет | `GENERATED ALWAYS AS IDENTITY` |
| `DATETIME('now')` | `now()` / `CURRENT_TIMESTAMP` |
| булевы как 0/1 | настоящий `BOOLEAN` |
| нет `ctx` в вызовах | pgx требует context первым аргументом |
| регистр идентификаторов | Postgres складывает в lowercase — не использовать кавычки в схеме |
| `strftime` для дат в статистике | переписать на `date_trunc` / `to_char` |
| календарь активности (84 дня) | `generate_series` вместо клиентской генерации дат |

Последние две — про экран статистики. Если там есть SQL с датами SQLite-специфичный — переписать.

---

## 7. Этапы

### Этап 1 — Инфраструктура
- docker-compose: сервис `anki-db` (postgres:16, порт 5434)
- `.env`: `DATABASE_URL` вместо `DB_PATH`
- зависимости: `go get jackc/pgx/v5`

### Этап 2 — Схема и миграции
- переписать goose-миграции под Postgres (чистая схема, §4)
- убрать рантайм `EnsureAdvancedSchema` → в миграцию
- проверить `goose up` на чистой БД

### Этап 3 — Слой хранения
- `storage/repository.go`: pgx, пул, `$N`, `RETURNING`, upsert
- прокинуть `ctx` где нужно
- переименование `interval` → `interval_days` в SQL и Go

### Этап 4 — Статистика (SQL с датами)
- переписать date-запросы (`strftime` → `date_trunc`, `generate_series` для календаря)

### Этап 5 — Проверка
- поднять с чистой БД, автозагрузка словаря (upsert)
- прогнать все режимы: тренировка, продвинутая, письмо, статистика
- проверить что REST-ответы идентичны прежним
- нагрузочно: несколько параллельных сессий (то ради чего переезжали)

---

## 8. Риски

| Риск | Решение |
|---|---|
| Пропущенный `?`-плейсхолдер → рантайм-ошибка | grep по `"?"` в SQL-строках; тесты на каждый метод репозитория |
| `interval` ломает запросы | переименовать сразу, не откладывать |
| Забытый `ctx` → не компилируется | компилятор поймает, не рантайм |
| cgo убирается (mattn) → проще сборка | бонус: pgx pure-Go, кросс-компиляция легче |
| Разъехались форматы дат в API | зафиксировать `TIMESTAMPTZ` → RFC3339 в JSON, проверить фронт |
| Два Postgres на машине (repetitor+anki) | разные порты (5433/5434), разные volume |

---

## 9. Структура изменений

```
anki/
├── cmd/server/main.go          ~ pgxpool вместо sql.Open, ctx
├── internal/
│   ├── storage/repository.go   ~ ПОЛНАЯ переработка под pgx (основной объём)
│   └── service/service.go      ~ прокинуть ctx если не было
├── migrations/                 ~ переписать под Postgres, убрать рантайм-DDL
│   └── 00001_init.sql
├── .env                        ~ DATABASE_URL
├── docker-compose.yml          + сервис anki-db
└── go.mod                      + pgx, - mattn/go-sqlite3
```

Фронтенд, gRPC, REST-контракт, SRS-логика — в списке изменений отсутствуют намеренно.

---

## 10. Definition of Done

- `docker compose up` поднимает `anki-db`
- `goose up` создаёт схему на чистой БД без ошибок
- автозагрузка словаря работает (upsert по `word`)
- все режимы работают: тренировка, продвинутая, письмо, статистика, чат, практика
- несколько параллельных сессий пишут одновременно без блокировок (главная цель переезда)
- REST-ответы совпадают с прежними по формату
- сборка без cgo (pure Go)
```
