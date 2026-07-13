package api

import (
	"net/http"

	"anki/internal/auth"
	"anki/internal/placement"

	"github.com/gin-gonic/gin"
)

func (h *Handler) PlacementQuestions(c *gin.Context) {
	c.JSON(http.StatusOK, placement.Questions())
}

type placementSubmitRequest struct {
	Answers map[int]int `json:"answers"`
}

func (h *Handler) PlacementSubmit(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	var req placementSubmitRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}
	level := placement.Score(req.Answers)
	if err := h.service.SetUserLevel(c.Request.Context(), userID, level); err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"level": level})
}
