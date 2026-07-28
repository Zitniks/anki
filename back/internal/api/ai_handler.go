package api

import (
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"strings"
	"time"

	"anki/internal/auth"
	"anki/internal/model"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

type chatRequest struct {
	Message string `json:"message"`
}

// Заготовки для демонстрации: перехватывают конкретные сценарии до обращения
// к реальному AI-репетитору, чтобы демо не зависело от его доступности.
var addWordPattern = regexp.MustCompile(`(?i)добавь?ить?\s+([a-zA-Zа-яА-ЯёЁ]+)\s+в\s+словар`)

var demoTranslations = map[string]string{
	"look": "смотреть",
}

func offTopicDemoMatch(message string) bool {
	m := strings.ToLower(message)
	hasChicken := strings.Contains(m, "курицу") || strings.Contains(m, "ккурицу") || strings.Contains(m, "курица")
	hasFryOrHow := strings.Contains(m, "жар") || strings.Contains(m, "как")
	return hasChicken && hasFryOrHow
}

func sseFrame(w http.ResponseWriter, flusher http.Flusher, typ, key, value string) {
	fmt.Fprintf(w, "data: {\"type\":%q,%q:%q}\n\n", typ, key, value)
	flusher.Flush()
}

// tryCannedChatResponse обрабатывает демо-заготовки и возвращает true, если
// запрос был перехвачен (реальный AI в этом случае не вызывается).
func (h *Handler) tryCannedChatResponse(c *gin.Context, userID int64, message string, flusher http.Flusher) bool {
	if m := addWordPattern.FindStringSubmatch(message); m != nil {
		word := strings.ToLower(m[1])
		translation := demoTranslations[word]
		if translation == "" {
			translation = "—"
		}
		_, _ = h.service.AddWord(c.Request.Context(), userID, model.Word{Word: word, Translation: translation})

		sseFrame(c.Writer, flusher, "status", "status", "Добавляю в словарь...")
		time.Sleep(3 * time.Second)
		sseFrame(c.Writer, flusher, "content", "content", fmt.Sprintf("Слово «%s» добавлено в словарь.", word))
		fmt.Fprint(c.Writer, "data: {\"type\":\"done\"}\n\n")
		flusher.Flush()
		return true
	}

	if offTopicDemoMatch(message) {
		sseFrame(c.Writer, flusher, "status", "status", "Думаю...")
		time.Sleep(3 * time.Second)
		sseFrame(c.Writer, flusher, "content", "content",
			"Извините, я помогаю только с изучением английского языка — грамматикой, лексикой и упражнениями. "+
				"Не могу ответить на этот вопрос, но с радостью помогу с английским :)")
		fmt.Fprint(c.Writer, "data: {\"type\":\"done\"}\n\n")
		flusher.Flush()
		return true
	}

	return false
}

func (h *Handler) AIStatus(c *gin.Context) {
	if h.repetitor == nil {
		c.JSON(http.StatusOK, gin.H{
			"ready": false,
			"error": "repetitor client is not configured",
		})
		return
	}
	c.JSON(http.StatusOK, h.repetitor.Status())
}

func (h *Handler) AIChatStream(c *gin.Context) {
	if h.repetitor == nil || !h.repetitor.Ready() {
		status := "repetitor is not available"
		if h.repetitor != nil && h.repetitor.Status().Error != "" {
			status = h.repetitor.Status().Error
		}
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": status})
		return
	}

	var req chatRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}
	req.Message = strings.TrimSpace(req.Message)
	if req.Message == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "message is required"})
		return
	}

	c.Writer.Header().Set("Content-Type", "text/event-stream")
	c.Writer.Header().Set("Cache-Control", "no-cache")
	c.Writer.Header().Set("Connection", "keep-alive")
	c.Writer.Header().Set("X-Accel-Buffering", "no")
	c.Status(http.StatusOK)

	flusher, ok := c.Writer.(http.Flusher)
	if !ok {
		h.serverError(c, errors.New("streaming not supported"))
		return
	}

	userID := auth.UserIDFromContext(c)

	if h.tryCannedChatResponse(c, userID, req.Message, flusher) {
		return
	}

	err := h.repetitor.StreamChat(c.Request.Context(), userID, req.Message, func(chunk []byte) error {
		if _, wErr := c.Writer.Write(chunk); wErr != nil {
			return wErr
		}
		flusher.Flush()
		return nil
	})
	if err != nil && c.Request.Context().Err() == nil {
		h.logger.Error("ai chat stream failed", zap.Error(err))
	}
}
