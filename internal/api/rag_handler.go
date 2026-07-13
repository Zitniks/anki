package api

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
)

type explainErrorRequest struct {
	Word     string `json:"word"`
	Expected string `json:"expected"`
	Got      string `json:"got"`
	Sentence string `json:"sentence"`
}

func (h *Handler) ExplainError(c *gin.Context) {
	if h.repetitor == nil || !h.repetitor.Ready() {
		status := "repetitor is not available"
		if h.repetitor != nil && h.repetitor.Status().Error != "" {
			status = h.repetitor.Status().Error
		}
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": status})
		return
	}

	var req explainErrorRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}
	req.Word = strings.TrimSpace(req.Word)
	if req.Word == "" || strings.TrimSpace(req.Expected) == "" || strings.TrimSpace(req.Got) == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "word, expected and got are required"})
		return
	}

	result, err := h.repetitor.ExplainError(c.Request.Context(), req.Word, req.Expected, req.Got, req.Sentence)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, result)
}

func (h *Handler) WeakTopics(c *gin.Context) {
	if h.repetitor == nil || !h.repetitor.Ready() {
		status := "repetitor is not available"
		if h.repetitor != nil && h.repetitor.Status().Error != "" {
			status = h.repetitor.Status().Error
		}
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": status})
		return
	}

	limit := int32(10)
	if raw := c.Query("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = int32(n)
		}
	}

	topics, err := h.repetitor.GetWeakTopics(c.Request.Context(), limit)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, topics)
}
