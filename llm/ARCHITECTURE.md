# llm_service — архитектура и компоненты

Python-бэкенд AI-репетитора: FastAPI + собственноручный LangGraph `StateGraph`-агент, Postgres +
pgvector, gRPC-сервис — мост к отдельному Go-приложению «Anki Lite» (`../ankis`). Это будущий
канонический дом кода `adaptive-learning-repetitor` (зеркалируется вручную, сейчас — рабочая
копия, к которой обращается живой gRPC-процесс).

## Общая система

```
Go-приложение Anki Lite ──gRPC (:50051)──▶ llm_service
                                              │
                          FastAPI + LangGraph agent (StateGraph)
                                              │
                     ┌────────────────────────┼────────────────────────┐
                     ▼                        ▼                        ▼
              Postgres + pgvector      3 RAG-корпуса              BKT/ALS mastery
           (Project/Chat/Message/…)  (Exercise/Example/         (TopicMastery per
                                       Explanation)               project+topic)
```

## Вход и конфигурация

- **`src/main.py`** — точка входа. `RequestIDMiddleware` (корреляция логов), `lifespan()` строит
  LangGraph-граф один раз при старте и кладёт на `app.state.graph`; если `GRPC_ENABLED` — там же
  поднимает gRPC-сервер на том же графе. CORS открыт полностью (`*`) — авторизация ожидается на
  уровне реверс-прокси (Caddy) перед сервисом. Роутеры — из `routers.ALL_ROUTERS`.
- **`src/settings.py`** — Pydantic `BaseSettings`. LLM-провайдер — OpenAI-совместимый эндпоинт;
  задеплоенный провайдер — **Yandex Cloud** (`yandexgpt/latest`), `LLM_PROJECT_ID` специально
  под Yandex folder-scoped project id. Отдельный дешёвый тир `LLM_CHEAP_*` — для классификации,
  извлечения словаря, именования чатов. `settings.llm`/`settings.llm_cheap`/`settings.s3_session`
  — ленивые `cached_property`. `model_validator` отказывается стартовать с
  дефолтными/плейсхолдер-секретами при `DEBUG=False`.
- **`src/database.py`** — SQLAlchemy async (asyncpg) + отдельный sync-движок для Alembic.
  ~17 моделей: `User`, `Project` (студент), `Chat`, `Message`, `File` (полиморфная), `Vocabulary`,
  `Topic`, `Material` (Exercise RAG), `ExampleBank` (Example RAG), `KnowledgeDoc`/`KnowledgeChunk`
  (Explanation RAG), `Lesson`, `CalendarEvent`, `RepeatItem`, `LearningEvent` (сырое событие),
  `TopicMastery` (агрегированная student model: BKT + ALS + калибровка), `UsageLog`.
- **`src/logger.py`** — `loguru`, ~19 именованных компонент-логгеров (`chat_logger`, `llm_logger`,
  `db_logger`, ...), request-id из `ContextVar`.

## LangGraph-агент (`src/chat/`)

Граф: `prepare → classify → route → model ⇄ tools → END`.

| Файл | Роль |
|---|---|
| `graph.py` | Собирает и компилирует `StateGraph`; узлы `_prepare_messages`, `_classify`, `_route`, `_call_model`, `_should_continue`. |
| `intent.py` | `classify_intent()` — LLM-классификация сообщения в `exercise\|explanation\|example\|chat` + тема + confidence, через `with_structured_output`. |
| `rag_router.py` | Чистая функция `resolve_route()` — приоритет: форс от Adaptive Engine → chat без RAG → уверенный классификатор (один корпус) → неуверенный (ensemble всех трёх, RRF-слияние). |
| `prompts.py` | `MAIN_SYSTEM_PROMPT` (репетитор говорит с преподавателем, не со студентом напрямую), правила инструментов, `format_vocabulary()`. |
| `tools.py` | `TOOLS`: `process_youtube_link`, `fetch_url_content` (с SSRF-гардом `_is_safe_public_url`), `generate_image`, `search_stock_photos`, `extract_vocabulary`, CRUD-хелперы, `search_materials` (ручной Exercise RAG). |
| `state.py` | `TutorRuntimeContext` (неизменяемый ввод хода), `TutorState`, `build_runnable_config()`. |
| `lifecycle.py` | `handle_chat()` — точка входа запроса: лимит токенов/день, сборка контекста, SSE-ответ. |
| `persistence.py` | Сохранение/загрузка сообщений, вложений, контекста документов. |
| `streaming.py` | `normalize_agent_events()` — стейт-машина для «thinking»-блоков + нормализация событий в SSE. |

## RAG (`src/analytics/`) — три независимых корпуса

| | Exercise RAG | Explanation RAG | Example RAG |
|---|---|---|---|
| Класс | `ExerciseRetriever` | `ExplanationRetriever` | `ExampleRetriever` |
| Поиск | pgvector + BM25 гибрид | pgvector, по чанкам | pgvector |
| Таблица | `materials` | `knowledge_docs`+`knowledge_chunks` | `example_bank` |
| Модуль | `rag.py` | `knowledge_docs.py` | `example_bank.py` |
| Форсируется действием движка | — (дефолт для `exercise`) | `prerequisite` | `more_examples` |

Общий контракт — `TutorRetriever(BaseRetriever)` в `retrievers.py` (`.ainvoke(query)`, только
async). Эмбеддинги (`embeddings.py`) — **`intfloat/multilingual-e5-small`**, 384-мерная,
CPU, `@lru_cache`. Переход с `multi-qa-MiniLM-L6-cos-v1` был вынужденным: на русскоязычных
запросах без английского якоря старая модель давала Recall@5 38.5%, e5-multilingual — 92.3%.
E5 требует префиксы `"query: "`/`"passage: "` — их подстановка спрятана за флагом `is_query` в
`embed()`/`embed_batch()`.

Метрики из `RAG_ROUTER.md` (соседний репозиторий `adaptive-learning-repetitor`, откуда
`llm_service` зеркалируется): router accuracy 96.3%, общий Recall@5 92.3%, MRR 0.776,
nDCG@5 0.741.

## Adaptive learning / mastery

- **`bkt.py`** — Bayesian Knowledge Tracing (Corbett & Anderson 1994): `P(L0)`/`P(T)`/`P(G)`/`P(S)`
  → апдейт `P(know)` по факту ответа; `is_mastered()` — порог 0.95.
- **`als.py`** — Adaptive Learning Score: взвешенная сумма accuracy(0.35)/time(0.15)/
  attempts(0.15)/hints(0.15)/confidence(0.10)/mastery(0.10) → один скор 0–1.
- **`forgetting.py`** — кривая забывания Эббингауза, применяется на чтении (не персистится):
  `p_know * exp(-0.05 * days_idle)`, не ниже BKT-прайора.
- **`calibration.py`** — `confidence_bias = самооценка − точность`; двигает сложность следующего
  задания (переуверенный студент → сложнее, неуверенный → держим уровень дольше).
- **`adaptive/engine.py`** — `decide()`: приоритет действий — недостающий prerequisite (accuracy
  <0.5 и attempts≥3) → `more_examples` (hint_usage>0.7) → `repeat`/`increase_difficulty`/
  `next_topic` → `continue`.
- **`adaptive/recommendation.py`** — превращает решение движка в конкретные материалы
  (`difficulty_to_cefr`, `rank_materials`).
- **`adaptive/curriculum.py`** — граф пререквизитов (`TOPIC_GRAPH`, A2→C1), топологическая
  сортировка, зоны ZPD (`mastered`/`in_progress`/`ready`/`blocked`), сборка плана уроков.

## gRPC-сервис (`src/grpc_svc/`) — мост к Anki Lite

`servicer.py::TutorGrpcServicer` реализует 9 RPC:

| RPC | Что делает |
|---|---|
| `Health` | Проверка живости. |
| `EnsureSession` | Аутентификация email/password, лениво создаёт/переиспользует проект «Anki Lite» и чаты «Anki Tutor»/«Anki Practice». |
| `Chat` (стрим) | Ведёт диалог через общий граф, стримит события, сохраняет ответ. |
| `GeneratePractice` | 5-вопросный RAG-обоснованный MCQ-квиз (`practice.py`). |
| `SearchRag` | Прямой поиск по одному из трёх корпусов. |
| `EnrichWord` | AI-черновик перевода/примера/IPA-транскрипции (`enrich.py`). |
| `PublishEvent` | Learning-событие → `LearningEvent` + BKT/ALS апдейт (`events.py`). |
| `ExplainError` | Объяснение ошибки, обосновано Explanation RAG (`explain.py`). |
| `GetWeakTopics` | Слабейшие темы/слова по `p_know`/ALS (`topic_mastery.get_weak`). |

`session.py::resolve_session()` — единая точка аутентификации + резолва project/chat для всех
RPC, возвращает `ResolvedSession`.

Провайдерский нюанс: function-calling бэкенд Yandex иногда портит символ `/` в аргументах
tool-call (превращает в control-байты) — воркэраунд в `enrich.py` (транскрипция без слэшей,
добавляются постфактум) и `practice.py` (зачистка control-символов из всего сгенерированного
текста).

## REST API (`src/routers/`)

Домены: `auth` (JWT), `pages` (Jinja2 HTML, без префикса), `chat`, `project`, `topics`,
`vocabulary`, `notes`, `materials` (Exercise RAG), `example_bank` (Example RAG),
`knowledge_docs` (Explanation RAG), `lessons`, `calendar_events`, `files`, `repeat_items`,
`usage`, `analytics` (learning events + student model), `adaptive` (next action), `recommendation`,
`curriculum`, `reflection`, `rag` (прямой поиск/переиндексация по всем трём корпусам).

## Repositories (`src/repositories/`)

`BaseRepository[T]` — generic CRUD (`get`/`get_all`/`create`/`create_many`/`delete`), каждый метод
открывает свою сессию, возвращает `dict` (ORM-инстансы не покидают репозиторий). Доступ — через
фасад `storage` (`repositories/storage.py`), лениво резолвит нужный репозиторий по имени:
`projects`, `chats`, `messages`, `files`, `file_storage`, `vocabulary`, `topics`, `materials`,
`material_links`, `lessons`, `calendar_events`, `repeat_items`, `users`, `usage_log`,
`learning_events`, `topic_mastery`, `example_bank`, `knowledge_docs`.

## Скрипты

В `llm_service/scripts/` сейчас только `gen_proto.sh` (регенерация gRPC-стабов). Eval- и
seed-скрипты (`eval_rag.py`, `seed_examples.py`, `seed_knowledge_docs.py`, `seed_materials.py`,
`enrich_relevant_ids.py`, `bench_embeddings.py`) живут только в соседнем
`adaptive-learning-repetitor/scripts/` — при переезде на `llm_service` как канонический репозиторий
их нужно будет перенести отдельно.
