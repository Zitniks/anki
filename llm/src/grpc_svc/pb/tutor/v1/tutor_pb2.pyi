from google.protobuf import empty_pb2 as _empty_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RagCorpus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RAG_CORPUS_UNSPECIFIED: _ClassVar[RagCorpus]
    RAG_CORPUS_EXERCISE: _ClassVar[RagCorpus]
    RAG_CORPUS_EXAMPLE: _ClassVar[RagCorpus]
    RAG_CORPUS_EXPLANATION: _ClassVar[RagCorpus]
RAG_CORPUS_UNSPECIFIED: RagCorpus
RAG_CORPUS_EXERCISE: RagCorpus
RAG_CORPUS_EXAMPLE: RagCorpus
RAG_CORPUS_EXPLANATION: RagCorpus

class Credentials(_message.Message):
    __slots__ = ("email", "password")
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    email: str
    password: str
    def __init__(self, email: _Optional[str] = ..., password: _Optional[str] = ...) -> None: ...

class Session(_message.Message):
    __slots__ = ("credentials", "project_id", "chat_id", "practice_chat_id", "anki_user_id")
    CREDENTIALS_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    CHAT_ID_FIELD_NUMBER: _ClassVar[int]
    PRACTICE_CHAT_ID_FIELD_NUMBER: _ClassVar[int]
    ANKI_USER_ID_FIELD_NUMBER: _ClassVar[int]
    credentials: Credentials
    project_id: str
    chat_id: str
    practice_chat_id: str
    anki_user_id: int
    def __init__(self, credentials: _Optional[_Union[Credentials, _Mapping]] = ..., project_id: _Optional[str] = ..., chat_id: _Optional[str] = ..., practice_chat_id: _Optional[str] = ..., anki_user_id: _Optional[int] = ...) -> None: ...

class EnsureSessionRequest(_message.Message):
    __slots__ = ("credentials", "project_id", "chat_id", "practice_chat_id")
    CREDENTIALS_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    CHAT_ID_FIELD_NUMBER: _ClassVar[int]
    PRACTICE_CHAT_ID_FIELD_NUMBER: _ClassVar[int]
    credentials: Credentials
    project_id: str
    chat_id: str
    practice_chat_id: str
    def __init__(self, credentials: _Optional[_Union[Credentials, _Mapping]] = ..., project_id: _Optional[str] = ..., chat_id: _Optional[str] = ..., practice_chat_id: _Optional[str] = ...) -> None: ...

class StatusResponse(_message.Message):
    __slots__ = ("ready", "address", "project_id", "chat_id", "practice_chat_id", "error")
    READY_FIELD_NUMBER: _ClassVar[int]
    ADDRESS_FIELD_NUMBER: _ClassVar[int]
    PROJECT_ID_FIELD_NUMBER: _ClassVar[int]
    CHAT_ID_FIELD_NUMBER: _ClassVar[int]
    PRACTICE_CHAT_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    ready: bool
    address: str
    project_id: str
    chat_id: str
    practice_chat_id: str
    error: str
    def __init__(self, ready: _Optional[bool] = ..., address: _Optional[str] = ..., project_id: _Optional[str] = ..., chat_id: _Optional[str] = ..., practice_chat_id: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...

class ChatRequest(_message.Message):
    __slots__ = ("session", "message", "use_practice_chat")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    USE_PRACTICE_CHAT_FIELD_NUMBER: _ClassVar[int]
    session: Session
    message: str
    use_practice_chat: bool
    def __init__(self, session: _Optional[_Union[Session, _Mapping]] = ..., message: _Optional[str] = ..., use_practice_chat: _Optional[bool] = ...) -> None: ...

class ChatEvent(_message.Message):
    __slots__ = ("type", "content", "status", "error")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    type: str
    content: str
    status: str
    error: str
    def __init__(self, type: _Optional[str] = ..., content: _Optional[str] = ..., status: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...

class PracticeRequest(_message.Message):
    __slots__ = ("session", "words", "level", "topic_title", "topic_content")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    WORDS_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    TOPIC_TITLE_FIELD_NUMBER: _ClassVar[int]
    TOPIC_CONTENT_FIELD_NUMBER: _ClassVar[int]
    session: Session
    words: _containers.RepeatedScalarFieldContainer[str]
    level: str
    topic_title: str
    topic_content: str
    def __init__(self, session: _Optional[_Union[Session, _Mapping]] = ..., words: _Optional[_Iterable[str]] = ..., level: _Optional[str] = ..., topic_title: _Optional[str] = ..., topic_content: _Optional[str] = ...) -> None: ...

class PracticeQuestion(_message.Message):
    __slots__ = ("prompt", "options", "correct_index", "explanation")
    PROMPT_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    CORRECT_INDEX_FIELD_NUMBER: _ClassVar[int]
    EXPLANATION_FIELD_NUMBER: _ClassVar[int]
    prompt: str
    options: _containers.RepeatedScalarFieldContainer[str]
    correct_index: int
    explanation: str
    def __init__(self, prompt: _Optional[str] = ..., options: _Optional[_Iterable[str]] = ..., correct_index: _Optional[int] = ..., explanation: _Optional[str] = ...) -> None: ...

class PracticeResponse(_message.Message):
    __slots__ = ("questions", "source", "rag_sources")
    QUESTIONS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    RAG_SOURCES_FIELD_NUMBER: _ClassVar[int]
    questions: _containers.RepeatedCompositeFieldContainer[PracticeQuestion]
    source: str
    rag_sources: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, questions: _Optional[_Iterable[_Union[PracticeQuestion, _Mapping]]] = ..., source: _Optional[str] = ..., rag_sources: _Optional[_Iterable[str]] = ...) -> None: ...

class RagSearchRequest(_message.Message):
    __slots__ = ("session", "query", "corpus", "limit")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    CORPUS_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    session: Session
    query: str
    corpus: RagCorpus
    limit: int
    def __init__(self, session: _Optional[_Union[Session, _Mapping]] = ..., query: _Optional[str] = ..., corpus: _Optional[_Union[RagCorpus, str]] = ..., limit: _Optional[int] = ...) -> None: ...

class RagChunk(_message.Message):
    __slots__ = ("id", "title", "snippet", "score")
    ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    SNIPPET_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    id: str
    title: str
    snippet: str
    score: float
    def __init__(self, id: _Optional[str] = ..., title: _Optional[str] = ..., snippet: _Optional[str] = ..., score: _Optional[float] = ...) -> None: ...

class RagSearchResponse(_message.Message):
    __slots__ = ("chunks", "context")
    CHUNKS_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    chunks: _containers.RepeatedCompositeFieldContainer[RagChunk]
    context: str
    def __init__(self, chunks: _Optional[_Iterable[_Union[RagChunk, _Mapping]]] = ..., context: _Optional[str] = ...) -> None: ...

class EnrichWordRequest(_message.Message):
    __slots__ = ("session", "word", "level")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    WORD_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    session: Session
    word: str
    level: str
    def __init__(self, session: _Optional[_Union[Session, _Mapping]] = ..., word: _Optional[str] = ..., level: _Optional[str] = ...) -> None: ...

class EnrichWordResponse(_message.Message):
    __slots__ = ("translation", "example", "transcription", "source")
    TRANSLATION_FIELD_NUMBER: _ClassVar[int]
    EXAMPLE_FIELD_NUMBER: _ClassVar[int]
    TRANSCRIPTION_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    translation: str
    example: str
    transcription: str
    source: str
    def __init__(self, translation: _Optional[str] = ..., example: _Optional[str] = ..., transcription: _Optional[str] = ..., source: _Optional[str] = ...) -> None: ...

class PublishEventRequest(_message.Message):
    __slots__ = ("session", "word", "correct", "response_time_ms", "attempts", "card_type", "difficulty")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    WORD_FIELD_NUMBER: _ClassVar[int]
    CORRECT_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    ATTEMPTS_FIELD_NUMBER: _ClassVar[int]
    CARD_TYPE_FIELD_NUMBER: _ClassVar[int]
    DIFFICULTY_FIELD_NUMBER: _ClassVar[int]
    session: Session
    word: str
    correct: bool
    response_time_ms: int
    attempts: int
    card_type: str
    difficulty: str
    def __init__(self, session: _Optional[_Union[Session, _Mapping]] = ..., word: _Optional[str] = ..., correct: _Optional[bool] = ..., response_time_ms: _Optional[int] = ..., attempts: _Optional[int] = ..., card_type: _Optional[str] = ..., difficulty: _Optional[str] = ...) -> None: ...

class PublishEventResponse(_message.Message):
    __slots__ = ("accepted",)
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    def __init__(self, accepted: _Optional[bool] = ...) -> None: ...

class ExplainErrorRequest(_message.Message):
    __slots__ = ("session", "word", "expected", "got", "sentence")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    WORD_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_FIELD_NUMBER: _ClassVar[int]
    GOT_FIELD_NUMBER: _ClassVar[int]
    SENTENCE_FIELD_NUMBER: _ClassVar[int]
    session: Session
    word: str
    expected: str
    got: str
    sentence: str
    def __init__(self, session: _Optional[_Union[Session, _Mapping]] = ..., word: _Optional[str] = ..., expected: _Optional[str] = ..., got: _Optional[str] = ..., sentence: _Optional[str] = ...) -> None: ...

class ExplainErrorResponse(_message.Message):
    __slots__ = ("explanation", "source")
    EXPLANATION_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    explanation: str
    source: str
    def __init__(self, explanation: _Optional[str] = ..., source: _Optional[str] = ...) -> None: ...

class GetWeakTopicsRequest(_message.Message):
    __slots__ = ("session", "limit")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    session: Session
    limit: int
    def __init__(self, session: _Optional[_Union[Session, _Mapping]] = ..., limit: _Optional[int] = ...) -> None: ...

class WeakTopic(_message.Message):
    __slots__ = ("word", "p_know", "als")
    WORD_FIELD_NUMBER: _ClassVar[int]
    P_KNOW_FIELD_NUMBER: _ClassVar[int]
    ALS_FIELD_NUMBER: _ClassVar[int]
    word: str
    p_know: float
    als: float
    def __init__(self, word: _Optional[str] = ..., p_know: _Optional[float] = ..., als: _Optional[float] = ...) -> None: ...

class GetWeakTopicsResponse(_message.Message):
    __slots__ = ("topics",)
    TOPICS_FIELD_NUMBER: _ClassVar[int]
    topics: _containers.RepeatedCompositeFieldContainer[WeakTopic]
    def __init__(self, topics: _Optional[_Iterable[_Union[WeakTopic, _Mapping]]] = ...) -> None: ...

class CheckAnswersRequest(_message.Message):
    __slots__ = ("session", "exercise_context", "answer_key", "user_answers")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    EXERCISE_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    ANSWER_KEY_FIELD_NUMBER: _ClassVar[int]
    USER_ANSWERS_FIELD_NUMBER: _ClassVar[int]
    session: Session
    exercise_context: str
    answer_key: str
    user_answers: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, session: _Optional[_Union[Session, _Mapping]] = ..., exercise_context: _Optional[str] = ..., answer_key: _Optional[str] = ..., user_answers: _Optional[_Iterable[str]] = ...) -> None: ...

class AnswerCheckItem(_message.Message):
    __slots__ = ("correct", "correct_answer", "explanation")
    CORRECT_FIELD_NUMBER: _ClassVar[int]
    CORRECT_ANSWER_FIELD_NUMBER: _ClassVar[int]
    EXPLANATION_FIELD_NUMBER: _ClassVar[int]
    correct: bool
    correct_answer: str
    explanation: str
    def __init__(self, correct: _Optional[bool] = ..., correct_answer: _Optional[str] = ..., explanation: _Optional[str] = ...) -> None: ...

class CheckAnswersResponse(_message.Message):
    __slots__ = ("results",)
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[AnswerCheckItem]
    def __init__(self, results: _Optional[_Iterable[_Union[AnswerCheckItem, _Mapping]]] = ...) -> None: ...

class TenseDrillTopic(_message.Message):
    __slots__ = ("title", "level", "content")
    TITLE_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    title: str
    level: str
    content: str
    def __init__(self, title: _Optional[str] = ..., level: _Optional[str] = ..., content: _Optional[str] = ...) -> None: ...

class GenerateTenseDrillRequest(_message.Message):
    __slots__ = ("session", "topics", "level", "count")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    TOPICS_FIELD_NUMBER: _ClassVar[int]
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    session: Session
    topics: _containers.RepeatedCompositeFieldContainer[TenseDrillTopic]
    level: str
    count: int
    def __init__(self, session: _Optional[_Union[Session, _Mapping]] = ..., topics: _Optional[_Iterable[_Union[TenseDrillTopic, _Mapping]]] = ..., level: _Optional[str] = ..., count: _Optional[int] = ...) -> None: ...

class TenseDrillItem(_message.Message):
    __slots__ = ("sentence_ru", "correct_tense", "reference_translation")
    SENTENCE_RU_FIELD_NUMBER: _ClassVar[int]
    CORRECT_TENSE_FIELD_NUMBER: _ClassVar[int]
    REFERENCE_TRANSLATION_FIELD_NUMBER: _ClassVar[int]
    sentence_ru: str
    correct_tense: str
    reference_translation: str
    def __init__(self, sentence_ru: _Optional[str] = ..., correct_tense: _Optional[str] = ..., reference_translation: _Optional[str] = ...) -> None: ...

class GenerateTenseDrillResponse(_message.Message):
    __slots__ = ("items",)
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    items: _containers.RepeatedCompositeFieldContainer[TenseDrillItem]
    def __init__(self, items: _Optional[_Iterable[_Union[TenseDrillItem, _Mapping]]] = ...) -> None: ...

class WordDraft(_message.Message):
    __slots__ = ("word", "translation", "example", "transcription")
    WORD_FIELD_NUMBER: _ClassVar[int]
    TRANSLATION_FIELD_NUMBER: _ClassVar[int]
    EXAMPLE_FIELD_NUMBER: _ClassVar[int]
    TRANSCRIPTION_FIELD_NUMBER: _ClassVar[int]
    word: str
    translation: str
    example: str
    transcription: str
    def __init__(self, word: _Optional[str] = ..., translation: _Optional[str] = ..., example: _Optional[str] = ..., transcription: _Optional[str] = ...) -> None: ...

class AddWordsRequest(_message.Message):
    __slots__ = ("user_id", "words")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    WORDS_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    words: _containers.RepeatedCompositeFieldContainer[WordDraft]
    def __init__(self, user_id: _Optional[int] = ..., words: _Optional[_Iterable[_Union[WordDraft, _Mapping]]] = ...) -> None: ...

class AddWordResult(_message.Message):
    __slots__ = ("word", "added", "reason")
    WORD_FIELD_NUMBER: _ClassVar[int]
    ADDED_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    word: str
    added: bool
    reason: str
    def __init__(self, word: _Optional[str] = ..., added: _Optional[bool] = ..., reason: _Optional[str] = ...) -> None: ...

class AddWordsResponse(_message.Message):
    __slots__ = ("results",)
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[AddWordResult]
    def __init__(self, results: _Optional[_Iterable[_Union[AddWordResult, _Mapping]]] = ...) -> None: ...

class DeleteWordRequest(_message.Message):
    __slots__ = ("user_id", "word")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    WORD_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    word: str
    def __init__(self, user_id: _Optional[int] = ..., word: _Optional[str] = ...) -> None: ...

class DeleteWordResponse(_message.Message):
    __slots__ = ("deleted",)
    DELETED_FIELD_NUMBER: _ClassVar[int]
    deleted: bool
    def __init__(self, deleted: _Optional[bool] = ...) -> None: ...

class CheckWordsExistRequest(_message.Message):
    __slots__ = ("user_id", "words")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    WORDS_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    words: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, user_id: _Optional[int] = ..., words: _Optional[_Iterable[str]] = ...) -> None: ...

class WordExistCheck(_message.Message):
    __slots__ = ("word", "exists", "translation")
    WORD_FIELD_NUMBER: _ClassVar[int]
    EXISTS_FIELD_NUMBER: _ClassVar[int]
    TRANSLATION_FIELD_NUMBER: _ClassVar[int]
    word: str
    exists: bool
    translation: str
    def __init__(self, word: _Optional[str] = ..., exists: _Optional[bool] = ..., translation: _Optional[str] = ...) -> None: ...

class CheckWordsExistResponse(_message.Message):
    __slots__ = ("results",)
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[WordExistCheck]
    def __init__(self, results: _Optional[_Iterable[_Union[WordExistCheck, _Mapping]]] = ...) -> None: ...
