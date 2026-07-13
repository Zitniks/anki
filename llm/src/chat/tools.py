"""LangChain tool definitions for tutor assistant.

Tools receive a typed ``ToolRuntime[TutorRuntimeContext]`` for per-turn inputs
and return ``Command(update=...)`` to write into ``TutorState``.
"""

import asyncio
import ipaddress
import re
import socket
from functools import partial
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

from chat.state import TutorRuntimeContext
from database import async_session_factory
from logger import extract_logger, image_gen_logger, llm_logger
from repositories import storage
from settings import settings
from analytics.rag import search as rag_search, build_context as rag_build_context, index_material as rag_index_material

# ========== INPUT SCHEMAS ==========


class GenerateImageInput(BaseModel):
    prompt: str = Field(description="Описание изображения для генерации")


class SearchStockPhotosInput(BaseModel):
    query: str = Field(
        description="Английское описание сцены/объекта для поиска фото (e.g. 'busy market', 'rainy street'). "
        "Всегда передавай query на английском.")
    n: int = Field(default=3, ge=1, le=5, description="Сколько фото вернуть (1–5, по умолчанию 3).")
    page: int = Field(
        default=1,
        ge=1,
        description="Номер страницы результатов. Если пользователь просит 'ещё' или 'другие' фото по тому же "
        "запросу — увеличивай (2, 3, ...), чтобы получить новые фото без повторов.")


class ProcessYoutubeLinkInput(BaseModel):
    url: str = Field(description="Ссылка на YouTube видео")


class FetchUrlContentInput(BaseModel):
    url: str = Field(description="HTTP(S) ссылка на веб-страницу (не YouTube) для извлечения текста")


class ExtractVocabularyInput(BaseModel):
    vocabulary: list[str] = Field(
        description="Список новых английских слов и фраз в начальной форме для сохранения в словарь студента.")


class GetRecentLessonsInput(BaseModel):
    n: int = Field(default=5, description="Количество последних уроков для получения (по умолчанию 5)")


class ListMaterialsInput(BaseModel):
    level: str | None = Field(default=None, description="Фильтр по уровню: A1, A2, B1, B2, C1, C2.")
    tag: str | None = Field(default=None, description="Фильтр по тегу (точное совпадение).")


class GetMaterialByIdInput(BaseModel):
    material_id: int = Field(description="ID материала из list_materials.")


class SaveMaterialInput(BaseModel):
    name: str = Field(description="Короткое название материала.")
    content: str = Field(description="Текст упражнения или материала.")
    level: str = Field(description="Уровень: A1, A2, B1, B2, C1 или C2.")
    answers: str | None = Field(default=None, description="Ответы к упражнению, если они есть.")
    tags: list[str] | None = Field(default=None, description="Теги — только если пользователь явно их указал.")


class SearchMaterialsInput(BaseModel):
    query: str = Field(description="Поисковый запрос на английском: тема, грамматическая конструкция или пример предложения.")
    topic: str | None = Field(default=None, description="Опциональный фильтр по теме (тег).")
    limit: int = Field(default=3, ge=1, le=10, description="Максимальное количество результатов.")


class GetVocabularyInput(BaseModel):
    # NOTE: Dummy optional field to avoid LangChain's empty-args_schema
    # short-circuit in BaseTool._to_args_and_kwargs, which would otherwise
    # drop the injected ToolRuntime. The LLM ignores the field; the tool
    # body ignores it. Safe to remove once we stop passing args_schema.
    noop: str | None = Field(default=None, description="Игнорируется.")


# ========== HELPERS ==========

_YOUTUBE_ID_RE = re.compile(r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})")
_TRANSCRIPT_MAX_CHARS = 4000
_MAX_HISTORY_IMAGES = 4
_URL_FETCH_TIMEOUT = 15
_URL_CONTENT_MAX_CHARS = 6000
_URL_USER_AGENT = "Mozilla/5.0 (compatible; TutorAssistantBot/1.0; +https://example.com/bot)"
_URL_MAX_REDIRECTS = 3
_PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
_PEXELS_TIMEOUT = 10


def _is_safe_public_url(url: str) -> bool:
    """Return True only if the URL's host resolves to a public, routable address.

    Rejects loopback, private, link-local, reserved, multicast, and unspecified
    IPs to mitigate SSRF against in-cluster services (Postgres, MinIO) and
    cloud metadata endpoints. Note: this does one DNS lookup; a DNS-rebind
    attack between this check and the subsequent fetch is not prevented.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
                or ip.is_unspecified):
            return False
    return True


async def _generate_image(prompt: str, images: list[dict] | None = None) -> tuple[str, str] | None:
    """Generate image via OpenAI-compatible API using direct client.

    Parameters
    ----------
    prompt : str
        Text prompt for image generation.
    images : list[dict] or None, optional
        Optional list of VLM image dicts (``name``, ``url``) to include as context.

    Returns
    -------
    tuple[str, str] or None
        ``(image_url, text_content)`` on success, or None if generation is disabled or fails.
    """
    if not settings.IMAGE_GEN_ENABLED:
        image_gen_logger.warning("image_gen.disabled")
        return None

    image_gen_logger.info(f"image_gen.start model={settings.IMAGE_GEN_MODEL} "
                          f"prompt_len={len(prompt)} images_count={len(images) if images else 0}")

    client = AsyncOpenAI(api_key=settings.IMAGE_GEN_API_KEY, base_url=settings.IMAGE_GEN_API_BASE)

    if images:
        content = [{"type": "text", "text": prompt}]
        for img in images:
            content.append({"type": "image_url", "image_url": {"url": img["url"]}})
    else:
        content = prompt

    for attempt in range(settings.IMAGE_GEN_MAX_RETRIES):
        try:
            response = await client.chat.completions.create(model=settings.IMAGE_GEN_MODEL,
                                                            messages=[{
                                                                "role": "user",
                                                                "content": content
                                                            }])

            choice = response.choices[0]
            text_content = choice.message.content or ""

            image_url = None
            if hasattr(choice.message, "images") and choice.message.images:
                image_url = choice.message.images[0]["image_url"]["url"]
                image_gen_logger.debug(f"image_gen.found_image images_count={len(choice.message.images)}")

            if not image_url:
                image_gen_logger.error(f"image_gen.no_image_url content_sample={text_content[:200]} "
                                       f"has_images_field={hasattr(choice.message, 'images')}")
                return None

            image_gen_logger.info(f"image_gen.success text_len={len(text_content)}")
            return image_url, text_content

        except Exception as e:
            if attempt < settings.IMAGE_GEN_MAX_RETRIES - 1:
                image_gen_logger.warning(f"image_gen.retry attempt={attempt + 1} error={e}")
                await asyncio.sleep(2)
                continue
            image_gen_logger.error(f"image_gen.error error={e}", exc_info=True)
            return None
    return None


# ========== TOOL DEFINITIONS ==========


@tool("process_youtube_link", args_schema=ProcessYoutubeLinkInput)
async def process_youtube_link_tool(url: str) -> str:
    """Загрузить транскрипт YouTube видео для создания упражнения на аудирование или gap-fill. Вызывай когда репетитор вставляет ссылку на YouTube."""
    match = _YOUTUBE_ID_RE.search(url)
    if not match:
        llm_logger.warning(f"tool.process_youtube_link invalid_url={url!r}")
        return "Не удалось получить транскрипт видео. Возможно, субтитры отключены или ссылка некорректна."

    video_id = match.group(1)
    api = YouTubeTranscriptApi()
    fetch = partial(api.fetch, video_id, languages=["en", "en-US", "en-GB", "en-AU", "a.en"])

    transcript_list = None
    for attempt in range(settings.YOUTUBE_MAX_RETRIES):
        try:
            transcript_list = await asyncio.get_event_loop().run_in_executor(None, fetch)
            break
        except (TranscriptsDisabled, NoTranscriptFound) as e:
            llm_logger.warning(f"tool.process_youtube_link video_id={video_id} error={e}")
            return "Не удалось получить транскрипт видео. Возможно, субтитры отключены или ссылка некорректна."
        except Exception as e:
            if "429" in str(e) and attempt < settings.YOUTUBE_MAX_RETRIES - 1:
                llm_logger.warning(f"tool.process_youtube_link rate_limited video_id={video_id} attempt={attempt + 1}")
                await asyncio.sleep(2**attempt)
                continue
            llm_logger.error(f"tool.process_youtube_link video_id={video_id} error={e}", exc_info=True)
            return "Не удалось получить транскрипт видео. Возможно, субтитры отключены или ссылка некорректна."

    text = " ".join(entry.text for entry in transcript_list)
    if len(text) > _TRANSCRIPT_MAX_CHARS:
        text = text[:_TRANSCRIPT_MAX_CHARS].rsplit(" ", 1)[0]

    llm_logger.info(f"tool.process_youtube_link video_id={video_id} chars={len(text)}")
    return f"ТРАНСКРИПТ ВИДЕО:\n\n{text}"


@tool("fetch_url_content", args_schema=FetchUrlContentInput)
async def fetch_url_content_tool(url: str) -> str:
    """Загрузить и извлечь основной текст со страницы по HTTP(S) ссылке (не YouTube). Вызывай всегда, когда репетитор вставляет ссылку на веб-страницу (статья, блог, материал), чтобы использовать её содержимое для упражнений."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        llm_logger.warning(f"tool.fetch_url_content invalid_url={url!r}")
        return "Не удалось загрузить страницу: некорректная ссылка."

    if not _is_safe_public_url(url):
        llm_logger.warning(f"tool.fetch_url_content blocked_url={url!r}")
        return "Не удалось загрузить страницу: ссылка ведёт на недопустимый адрес."

    current = url
    try:
        async with httpx.AsyncClient(
            timeout=_URL_FETCH_TIMEOUT,
            follow_redirects=False,
            headers={"User-Agent": _URL_USER_AGENT},
        ) as client:
            for _ in range(_URL_MAX_REDIRECTS + 1):
                response = await client.get(current)
                if not response.is_redirect:
                    break
                location = response.headers.get("location")
                if not location:
                    break
                current = urljoin(current, location)
                if not _is_safe_public_url(current):
                    llm_logger.warning(f"tool.fetch_url_content blocked_redirect from={url!r} to={current!r}")
                    return "Не удалось загрузить страницу: переадресация на недопустимый адрес."
            else:
                llm_logger.warning(f"tool.fetch_url_content too_many_redirects url={url}")
                return "Не удалось загрузить страницу: слишком много переадресаций."
    except Exception as e:
        llm_logger.error(f"tool.fetch_url_content fetch_error url={url} error={e}", exc_info=True)
        return "Не удалось загрузить страницу. Проверьте ссылку или попробуйте позже."

    if response.status_code >= 400:
        llm_logger.warning(f"tool.fetch_url_content http_error url={url} status={response.status_code}")
        return f"Не удалось загрузить страницу (HTTP {response.status_code})."

    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        llm_logger.warning(f"tool.fetch_url_content unsupported_content_type url={url} content_type={content_type}")
        return "Не удалось извлечь текст: ссылка ведёт не на HTML-страницу."

    html = response.text
    extract = partial(
        trafilatura.extract,
        html,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    try:
        text = await asyncio.get_event_loop().run_in_executor(None, extract)
    except Exception as e:
        llm_logger.error(f"tool.fetch_url_content extract_error url={url} error={e}", exc_info=True)
        return "Не удалось извлечь текст со страницы."

    if not text:
        llm_logger.warning(f"tool.fetch_url_content empty_extract url={url}")
        return "Не удалось извлечь текст со страницы (возможно, требуется JavaScript или контент недоступен)."

    if len(text) > _URL_CONTENT_MAX_CHARS:
        text = text[:_URL_CONTENT_MAX_CHARS].rsplit(" ", 1)[0]

    llm_logger.info(f"tool.fetch_url_content url={url} chars={len(text)}")
    return f"СОДЕРЖИМОЕ СТРАНИЦЫ:\n\n{text}"


@tool("generate_image", args_schema=GenerateImageInput)
async def generate_image_tool(
    prompt: str,
    runtime: ToolRuntime[TutorRuntimeContext],
) -> Command | str:
    """Сгенерировать изображение по описанию. Используй когда пользователь просит создать, нарисовать или сгенерировать изображение или картинку."""
    ctx = runtime.context

    history_images = [img for msg in ctx.history for img in msg.get("images", [])][-_MAX_HISTORY_IMAGES:]

    result = await _generate_image(prompt, images=history_images or None)
    if result:
        image_url, text = result
        image_gen_logger.info(f"tool.generate_image project_id={ctx.project_id} success=True")
        return Command(
            update={
                "images": [{"name": "generated_image.png", "url": image_url, "source": "generated"}],
                "messages": [
                    ToolMessage(
                        content=text or "Изображение успешно сгенерировано",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )

    image_gen_logger.warning(f"tool.generate_image project_id={ctx.project_id} success=False")
    return "К сожалению, не удалось сгенерировать изображение."


# ========== STOCK PHOTO SEARCH ==========


async def _search_pexels(query: str, n: int, page: int = 1) -> list[dict]:
    """Search Pexels ``/v1/search`` for photos.

    The Pexels host is hardcoded HTTPS to a well-known public API, so the
    SSRF guard used by ``fetch_url_content`` is not needed here.

    Returns
    -------
    list of dict
        Each dict: ``name`` (alt/credit), ``url`` (large image URL),
        ``page_url`` (Pexels photo page), ``source`` ("pexels").
    """
    headers = {"Authorization": settings.PEXELS_API_KEY}
    params = {"query": query, "per_page": n, "page": page}
    async with httpx.AsyncClient(timeout=_PEXELS_TIMEOUT) as client:
        response = await client.get(_PEXELS_SEARCH_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

    photos = []
    for photo in data.get("photos", []):
        src = photo.get("src", {})
        url = src.get("large") or src.get("medium") or src.get("original")
        if not url:
            continue
        photographer = photo.get("photographer", "Unknown")
        photos.append({
            "name": f"Photo by {photographer} on Pexels",
            "url": url,
            "page_url": photo.get("url", ""),
            "source": "pexels",
            "width": photo.get("width"),
            "height": photo.get("height"),
        })
    return photos


@tool("search_stock_photos", args_schema=SearchStockPhotosInput)
async def search_stock_photos_tool(
    query: str,
    runtime: ToolRuntime[TutorRuntimeContext],
    n: int = 3,
    page: int = 1,
) -> Command | str:
    """Найти готовые фотографии (Pexels) по английскому запросу. Используй для бытовых сцен и реальных объектов (рынок, доктор, дождливая улица) вместо generate_image. Возвращает 1–5 реальных фото."""
    ctx = runtime.context
    if not settings.STOCK_PHOTO_ENABLED:
        return "Поиск фото временно недоступен."

    try:
        photos = await _search_pexels(query, n, page=page)
    except Exception as e:
        llm_logger.error(f"tool.search_stock_photos project_id={ctx.project_id} "
                         f"query={query!r} page={page} error={e}", exc_info=True)
        return "Не удалось загрузить фото. Попробуйте позже."

    if not photos:
        llm_logger.info(f"tool.search_stock_photos project_id={ctx.project_id} "
                        f"query={query!r} page={page} count=0")
        return f"По запросу '{query}' фото не найдены, попробуйте переформулировать."

    llm_logger.info(f"tool.search_stock_photos project_id={ctx.project_id} "
                    f"query={query!r} page={page} count={len(photos)}")

    lines = [f"Найдено {len(photos)} фото по запросу '{query}' (page={page}):"]
    for i, p in enumerate(photos, start=1):
        author = p.get("name", "").replace(" on Pexels", "").replace("Photo by ", "")
        page_url = p.get("page_url") or ""
        lines.append(f"{i}. {author} — {page_url}")
    lines.append(
        "Фотографии уже показаны репетитору в UI с подписью автора. "
        "Если упоминаешь конкретное фото — используй ТОЛЬКО ссылки из списка выше, "
        "не выдумывай URL. Если ссылки не нужны — просто коротко подтверди.")
    summary = "\n".join(lines)
    return Command(
        update={
            "images": photos,
            "messages": [ToolMessage(content=summary, tool_call_id=runtime.tool_call_id)],
        })


@tool("extract_vocabulary", args_schema=ExtractVocabularyInput)
async def extract_vocabulary_tool(
    vocabulary: list[str],
    runtime: ToolRuntime[TutorRuntimeContext],
) -> Command:
    """Сохранить английские слова/фразы в словарь студента. Вызывай ТОЛЬКО когда репетитор явно просит запомнить/сохранить/добавить в словарь. НЕ вызывай автоматически по словам, просто встреченным в тексте или упражнении."""
    ctx = runtime.context
    result = await storage.vocabulary.add_words(ctx.project_id, vocabulary)

    extract_logger.info(f"tool.extract_vocabulary project_id={ctx.project_id} "
                        f"added={len(result['added'])} skipped_existing={len(result['skipped_existing'])} "
                        f"skipped_deleted={len(result['skipped_deleted'])} rejected={len(result['rejected'])}")

    parts = []
    if result["added"]:
        parts.append(f"Сохранено в словарь: {', '.join(result['added'])}")
    if result["skipped_existing"]:
        parts.append(f"Уже есть в словаре: {', '.join(result['skipped_existing'])}")
    if result["skipped_deleted"]:
        parts.append(f"Ранее удалены (не добавлены): {', '.join(result['skipped_deleted'])}")
    if result["rejected"]:
        parts.append(f"Некорректные слова (не добавлены): {', '.join(result['rejected'])}")
    message = "\n".join(parts) if parts else "Новая лексика не найдена."

    return Command(update={
        "messages": [ToolMessage(content=message, tool_call_id=runtime.tool_call_id)],
    })


@tool("get_recent_lessons", args_schema=GetRecentLessonsInput)
async def get_recent_lessons_tool(
    n: int = 5,
    *,
    runtime: ToolRuntime[TutorRuntimeContext],
) -> str:
    """Получить информацию о последних N уроках студента. Вызывай когда нужно создать упражнение на основе пройденного материала или узнать что изучалось на последних занятиях."""
    ctx = runtime.context
    all_lessons = await storage.lessons.get_by_project(ctx.project_id)
    lessons = sorted(all_lessons, key=lambda lesson: lesson["date"], reverse=True)[:n]

    llm_logger.info(f"tool.get_recent_lessons project_id={ctx.project_id} count={len(lessons)}")

    if not lessons:
        return "История уроков не найдена."

    lines = [f"- {lesson['date'][:10]}: {lesson['description']}" for lesson in lessons]
    return "Последние уроки:\n" + "\n".join(lines)


@tool("get_vocabulary", args_schema=GetVocabularyInput)
async def get_vocabulary_tool(
    runtime: ToolRuntime[TutorRuntimeContext],
    noop: str | None = None,
) -> str:
    """Получить весь словарный запас студента, отсортированный от старых слов к новым (по дате добавления). Вызывай когда студент или репетитор хочет посмотреть все изученные слова."""
    ctx = runtime.context
    words = await storage.vocabulary.get_active_by_project(ctx.project_id)

    llm_logger.info(f"tool.get_vocabulary project_id={ctx.project_id} count={len(words)}")

    if not words:
        return "Словарный запас пуст."
    return "\n".join(f"{i + 1}. {w}" for i, w in enumerate(words))


@tool("list_materials", args_schema=ListMaterialsInput)
async def list_materials_tool(
    runtime: ToolRuntime[TutorRuntimeContext],
    level: str | None = None,
    tag: str | None = None,
) -> str:
    """Получить список материалов репетитора (краткое представление: id, название, уровень, теги). Вызывай когда репетитор спрашивает что есть в материалах или ищет конкретный материал. Используй фильтры level/tag чтобы сузить выдачу."""
    ctx = runtime.context
    materials = await storage.materials.get_all(user_id=str(ctx.user_id))

    filtered = []
    for m in materials:
        if level and m.get("level") != level:
            continue
        if tag and tag not in (m.get("tags") or []):
            continue
        filtered.append(m)

    llm_logger.info(f"tool.list_materials user_id={ctx.user_id} total={len(materials)} "
                    f"returned={len(filtered)} level={level} tag={tag}")

    if not filtered:
        return "Материалы не найдены."

    lines = []
    for m in filtered:
        tags = m.get("tags") or []
        tags_str = f" [{', '.join(tags)}]" if tags else ""
        level_str = f" ({m.get('level')})" if m.get("level") else ""
        lines.append(f"#{m['id']}: {m['name']}{level_str}{tags_str}")
    return "\n".join(lines)


@tool("get_material_by_id", args_schema=GetMaterialByIdInput)
async def get_material_by_id_tool(
    material_id: int,
    runtime: ToolRuntime[TutorRuntimeContext],
) -> str:
    """Получить полное содержимое материала по id. Вызывай после list_materials когда нужно использовать материал в текущем чате."""
    ctx = runtime.context
    material = await storage.materials.get(material_id)

    if not material or str(material.get("user_id")) != str(ctx.user_id):
        llm_logger.warning(f"tool.get_material_by_id not_found_or_forbidden "
                           f"user_id={ctx.user_id} material_id={material_id}")
        return "Материал не найден."

    llm_logger.info(f"tool.get_material_by_id user_id={ctx.user_id} material_id={material_id}")

    parts = [f"Название: {material['name']}"]
    if material.get("level"):
        parts.append(f"Уровень: {material['level']}")
    if material.get("tags"):
        parts.append(f"Теги: {', '.join(material['tags'])}")
    parts.append(f"\nСодержимое:\n{material['content']}")
    if material.get("answers"):
        parts.append(f"\nОтветы:\n{material['answers']}")
    return "\n".join(parts)


@tool("save_material", args_schema=SaveMaterialInput)
async def save_material_tool(
    name: str,
    content: str,
    level: str,
    runtime: ToolRuntime[TutorRuntimeContext],
    answers: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Сохранить новый материал в библиотеку репетитора. Вызывай ТОЛЬКО по явной просьбе репетитора ("добавь в материалы", "сохрани это упражнение"). Если уровень не указан и не очевиден из содержимого — сначала уточни у репетитора. Теги добавляй только если репетитор их явно назвал."""
    ctx = runtime.context
    data = {
        "user_id": ctx.user_id,
        "name": name,
        "content": content,
        "level": level,
        "answers": answers,
        "tags": tags,
    }
    material = await storage.materials.create(data=data)

    try:
        async with async_session_factory() as session:
            await rag_index_material(session, material["id"], name, content, tags)
    except Exception:
        pass

    llm_logger.info(f"tool.save_material user_id={ctx.user_id} material_id={material['id']} "
                    f"name={name!r} level={level} has_answers={answers is not None} "
                    f"tags={tags}")

    return (f"Сохранено как материал #{material['id']}. "
            f"В ответе репетитору добавь ссылку: "
            f"[Открыть материал](/materials?material={material['id']})")


@tool("search_materials", args_schema=SearchMaterialsInput)
async def search_materials_tool(
    query: str,
    runtime: ToolRuntime[TutorRuntimeContext],
    topic: str | None = None,
    limit: int = 3,
) -> str:
    """Семантический поиск по библиотеке материалов репетитора. Вызывай когда студент задаёт вопрос по грамматике или просит объяснение — сначала найди релевантные материалы и используй их как основу ответа. Возвращает тексты упражнений и объяснений."""
    ctx = runtime.context
    async with async_session_factory() as session:
        chunks = await rag_search(session, query, str(ctx.user_id), topic=topic, limit=limit)

    llm_logger.info(
        f"tool.search_materials user_id={ctx.user_id} query={query!r} found={len(chunks)}"
    )

    if not chunks:
        return "Подходящих материалов не найдено. Попробуй другой запрос."

    context = rag_build_context(chunks)
    return context


TOOLS = [
    process_youtube_link_tool,
    fetch_url_content_tool,
    generate_image_tool,
    extract_vocabulary_tool,
    get_recent_lessons_tool,
    get_vocabulary_tool,
    list_materials_tool,
    get_material_by_id_tool,
    save_material_tool,
    search_materials_tool,
]
if settings.STOCK_PHOTO_ENABLED:
    TOOLS.append(search_stock_photos_tool)
