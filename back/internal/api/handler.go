package api

import (
	"context"
	"errors"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"unicode"

	"anki/internal/ai"
	tutorpb "anki/internal/ai/pb/tutor/v1"
	"anki/internal/auth"
	"anki/internal/model"
	"anki/internal/service"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

type Handler struct {
	service   *service.WordService
	repetitor *ai.Client
	logger    *zap.Logger
	jwtSecret string
}

func NewHandler(s *service.WordService, repetitor *ai.Client, logger *zap.Logger, jwtSecret string) *Handler {
	return &Handler{service: s, repetitor: repetitor, logger: logger, jwtSecret: jwtSecret}
}

type addWordRequest struct {
	Word          string `json:"word"`
	Translation   string `json:"translation"`
	Example       string `json:"example"`
	Transcription string `json:"transcription"`
}

type reviewRequest struct {
	WordID  int64 `json:"word_id"`
	Round   int   `json:"round"`
	Correct bool  `json:"correct"`
}

type advancedReviewRequest struct {
	WordID         int64 `json:"word_id"`
	Round          int   `json:"round"`
	Correct        bool  `json:"correct"`
	ResponseTimeMS *int  `json:"response_time_ms,omitempty"`
}

type practiceGenerateRequest struct {
	Word        string   `json:"word"`
	Translation string   `json:"translation"`
	Level       string   `json:"level"`
	WordList    []string `json:"word_list"`
}

type practiceGenerateResponse struct {
	Questions []ai.PracticeQuestion `json:"questions"`
	Source    string                `json:"source"`
	Sources   []string              `json:"sources,omitempty"`
}

func (h *Handler) ListWords(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	words, err := h.service.ListWords(c.Request.Context(), userID)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, words)
}

func (h *Handler) AddWord(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	var req addWordRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}

	created, err := h.service.AddWord(c.Request.Context(), userID, model.Word{
		Word:          req.Word,
		Translation:   req.Translation,
		Example:       req.Example,
		Transcription: req.Transcription,
	})
	if err != nil {
		h.handleServiceErr(c, err)
		return
	}
	c.JSON(http.StatusCreated, created)
}

type addWordsBatchRequest struct {
	Words []addWordRequest `json:"words"`
}

type addWordsBatchResponse struct {
	Added   []model.Word `json:"added"`
	Skipped []string     `json:"skipped"` // already in the dictionary
	Failed  []string     `json:"failed"`  // invalid or errored
}

// AddWordsBatch adds several words in one request (e.g. "add this whole topic
// list") — same validation and card creation as AddWord, just looped, so a
// word already in the dictionary is reported as skipped rather than failing
// the whole batch.
func (h *Handler) AddWordsBatch(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	var req addWordsBatchRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}
	if len(req.Words) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "at least one word is required"})
		return
	}
	if len(req.Words) > 100 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "too many words in one batch (max 100)"})
		return
	}

	resp := addWordsBatchResponse{Added: []model.Word{}, Skipped: []string{}, Failed: []string{}}
	for _, w := range req.Words {
		created, err := h.service.AddWord(c.Request.Context(), userID, model.Word{
			Word:          w.Word,
			Translation:   w.Translation,
			Example:       w.Example,
			Transcription: w.Transcription,
		})
		switch {
		case err == nil:
			resp.Added = append(resp.Added, created)
		case errors.Is(err, service.ErrConflict):
			resp.Skipped = append(resp.Skipped, w.Word)
		default:
			if err != nil {
				h.logger.Warn("batch add word failed", zap.String("word", w.Word), zap.Error(err))
			}
			resp.Failed = append(resp.Failed, w.Word)
		}
	}
	c.JSON(http.StatusOK, resp)
}

func (h *Handler) DeleteWord(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid id"})
		return
	}
	if err := h.service.DeleteWord(c.Request.Context(), userID, id); err != nil {
		h.handleServiceErr(c, err)
		return
	}
	c.Status(http.StatusOK)
}

func (h *Handler) NextReviewWord(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	round, err := strconv.Atoi(c.DefaultQuery("round", "1"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid round"})
		return
	}
	card, err := h.service.NextReviewWord(c.Request.Context(), userID, round)
	if err != nil {
		h.handleServiceErr(c, err)
		return
	}
	c.JSON(http.StatusOK, card)
}

func (h *Handler) ReviewSession(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	limit, err := strconv.Atoi(c.DefaultQuery("limit", "15"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid limit"})
		return
	}
	words, err := h.service.BuildSession(c.Request.Context(), userID, limit)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"session_size": len(words),
		"words":        words,
	})
}

func (h *Handler) ReviewCard(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	wordID, err := strconv.ParseInt(c.Query("word_id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid word_id"})
		return
	}
	round, err := strconv.Atoi(c.DefaultQuery("round", "1"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid round"})
		return
	}
	card, err := h.service.GetCardForRound(c.Request.Context(), userID, wordID, round)
	if err != nil {
		h.handleServiceErr(c, err)
		return
	}
	if round == 4 && card.Skip && h.repetitor != nil && h.repetitor.Ready() {
		h.fillClozeFromRag(c.Request.Context(), card)
	}
	c.JSON(http.StatusOK, card)
}

// fillClozeFromRag tries to source a live cloze sentence from Example RAG when the
// word has no static example. Leaves card.Skip as-is if RAG has nothing usable either
// — same graceful degradation as today, just with an extra chance to avoid it.
func (h *Handler) fillClozeFromRag(ctx context.Context, card *model.ReviewCard) {
	resp, err := h.repetitor.SearchRag(ctx, card.Word, tutorpb.RagCorpus_RAG_CORPUS_EXAMPLE, 1)
	if err != nil || len(resp.Chunks) == 0 {
		return
	}
	cloze, ok := toClozeSentence(resp.Chunks[0].Snippet, card.Word)
	if !ok {
		return
	}
	card.Example = cloze
	card.Skip = false
}

var wordBoundaryPattern = regexp.MustCompile(`\W+`)

// toClozeSentence replaces the first whole-word, case-insensitive occurrence of word
// in sentence with "___". Returns ok=false if word doesn't appear verbatim, so callers
// don't show a cloze with nothing blanked out.
func toClozeSentence(sentence, word string) (string, bool) {
	tokens := wordBoundaryPattern.Split(sentence, -1)
	for _, tok := range tokens {
		if tok != "" && strings.EqualFold(tok, word) {
			re := regexp.MustCompile(`(?i)\b` + regexp.QuoteMeta(word) + `\b`)
			return re.ReplaceAllString(sentence, "___"), true
		}
	}
	return "", false
}

func (h *Handler) SubmitReview(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	var req reviewRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}
	if err := h.service.SubmitReview(c.Request.Context(), userID, req.WordID, req.Round, req.Correct); err != nil {
		h.handleServiceErr(c, err)
		return
	}
	c.Status(http.StatusOK)
}

func (h *Handler) Stats(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	stats, err := h.service.Stats(c.Request.Context(), userID)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, stats)
}

func (h *Handler) RoundStats(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	stats, err := h.service.RoundStats(c.Request.Context(), userID)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, stats)
}

func (h *Handler) AdvancedRoundStats(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	stats, err := h.service.AdvancedRoundStats(c.Request.Context(), userID)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, stats)
}

func (h *Handler) NextAdvancedReviewWord(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	round, err := strconv.Atoi(c.DefaultQuery("round", "1"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid round"})
		return
	}
	card, err := h.service.NextAdvancedReviewWord(c.Request.Context(), userID, round)
	if err != nil {
		h.handleServiceErr(c, err)
		return
	}
	c.JSON(http.StatusOK, card)
}

func (h *Handler) SubmitAdvancedReview(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	var req advancedReviewRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}
	if err := h.service.SubmitAdvancedReview(c.Request.Context(), userID, req.WordID, req.Round, req.Correct, req.ResponseTimeMS); err != nil {
		h.handleServiceErr(c, err)
		return
	}
	c.Status(http.StatusOK)
}

func (h *Handler) ActivityDays(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	days, err := strconv.Atoi(c.DefaultQuery("days", "90"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid days"})
		return
	}
	data, err := h.service.ActivityDays(c.Request.Context(), userID, days)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, data)
}

func (h *Handler) PracticeGenerate(c *gin.Context) {
	var req practiceGenerateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}
	req.Word = strings.TrimSpace(req.Word)
	req.Translation = strings.TrimSpace(req.Translation)
	req.Level = strings.TrimSpace(req.Level)
	if req.Level == "" {
		req.Level = "B1"
	}
	words := normalizePracticeWords(req.Word, req.WordList)
	if len(words) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "at least one target word is required"})
		return
	}
	for _, w := range words {
		if !isValidPracticeWord(w) {
			c.JSON(http.StatusBadRequest, gin.H{"error": "target words must contain English letters only (A-Z, space, hyphen, apostrophe)"})
			return
		}
	}
	req.Word = words[0]
	req.WordList = words

	if h.repetitor != nil && h.repetitor.Ready() {
		generated, err := h.repetitor.GeneratePractice(c.Request.Context(), words, req.Level)
		if err == nil {
			c.JSON(http.StatusOK, practiceGenerateResponse{
				Questions: generated.Questions,
				Source:    generated.Source,
				Sources:   generated.Sources,
			})
			return
		}
		h.logger.Warn("practice repetitor fallback", zap.Error(err))
	}

	c.JSON(http.StatusOK, buildPracticeFallback(req.Word))
}

func (h *Handler) handleServiceErr(c *gin.Context, err error) {
	switch {
	case errors.Is(err, service.ErrInvalidInput):
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
	case errors.Is(err, service.ErrNotFound):
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
	case errors.Is(err, service.ErrConflict):
		c.JSON(http.StatusConflict, gin.H{"error": "word already exists"})
	default:
		h.serverError(c, err)
	}
}

func (h *Handler) serverError(c *gin.Context, err error) {
	h.logger.Error("request failed", zap.Error(err), zap.String("path", c.Request.URL.Path))
	c.JSON(http.StatusInternalServerError, gin.H{"error": "internal server error"})
}

// buildPracticeFallback returns a tiny fixed quiz when repetitor is unreachable — not
// AI-grounded, just enough to keep the practice flow usable instead of erroring out.
func buildPracticeFallback(word string) practiceGenerateResponse {
	return practiceGenerateResponse{
		Questions: []ai.PracticeQuestion{
			{
				Prompt:       "Which sentence uses \"" + word + "\" correctly?",
				Options:      []string{"I practice " + word + " every day.", "I quickly " + word + " the lesson.", "The " + word + " is running.", "She is very " + word + " about it."},
				CorrectIndex: 0,
				Explanation:  "\"" + word + "\" fits naturally as the object of a routine action like \"practice ... every day.\"",
			},
			{
				Prompt:       "Can \"" + word + "\" be used in an everyday English sentence?",
				Options:      []string{"Yes", "No", "Only in formal writing", "Only as a name"},
				CorrectIndex: 0,
				Explanation:  "\"" + word + "\" is an ordinary vocabulary word, usable in everyday sentences.",
			},
		},
		Source: "fallback",
	}
}

func normalizePracticeWords(primary string, extras []string) []string {
	raw := make([]string, 0, 1+len(extras))
	if strings.TrimSpace(primary) != "" {
		raw = append(raw, splitPracticeInput(primary)...)
	}
	for _, item := range extras {
		raw = append(raw, splitPracticeInput(item)...)
	}

	seen := make(map[string]struct{}, len(raw))
	out := make([]string, 0, len(raw))
	for _, item := range raw {
		norm := strings.Join(strings.Fields(strings.TrimSpace(item)), " ")
		if norm == "" {
			continue
		}
		key := strings.ToLower(norm)
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		out = append(out, norm)
		if len(out) >= 50 {
			break
		}
	}
	return out
}

func splitPracticeInput(value string) []string {
	parts := strings.FieldsFunc(value, func(r rune) bool {
		return r == ',' || r == ';' || r == '\n' || r == '\t'
	})
	return parts
}

func isValidPracticeWord(value string) bool {
	if value == "" {
		return false
	}
	hasASCII := false
	for _, r := range value {
		switch {
		case r >= 'a' && r <= 'z':
			hasASCII = true
		case r >= 'A' && r <= 'Z':
			hasASCII = true
		case r == '\'' || r == '-' || unicode.IsSpace(r):
			// allowed punctuation and separators
		default:
			return false
		}
	}
	return hasASCII
}
