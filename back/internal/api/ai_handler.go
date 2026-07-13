package api

import (
	"errors"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

type chatRequest struct {
	Message string `json:"message"`
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

	err := h.repetitor.StreamChat(c.Request.Context(), req.Message, func(chunk []byte) error {
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
