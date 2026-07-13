package api

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
)

type enrichWordRequest struct {
	Word  string `json:"word"`
	Level string `json:"level"`
}

func (h *Handler) EnrichWord(c *gin.Context) {
	if h.repetitor == nil || !h.repetitor.Ready() {
		status := "repetitor is not available"
		if h.repetitor != nil && h.repetitor.Status().Error != "" {
			status = h.repetitor.Status().Error
		}
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": status})
		return
	}

	var req enrichWordRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}
	req.Word = strings.TrimSpace(req.Word)
	req.Level = strings.TrimSpace(req.Level)
	if req.Word == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "word is required"})
		return
	}
	if req.Level == "" {
		req.Level = "B1"
	}

	result, err := h.repetitor.EnrichWord(c.Request.Context(), req.Word, req.Level)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, result)
}
