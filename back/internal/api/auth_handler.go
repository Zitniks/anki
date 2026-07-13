package api

import (
	"errors"
	"net/http"

	"anki/internal/auth"
	"anki/internal/service"

	"github.com/gin-gonic/gin"
)

type registerRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

func (h *Handler) Register(c *gin.Context) {
	var req registerRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}
	user, err := h.service.CreateUser(c.Request.Context(), req.Email, req.Password)
	if err != nil {
		switch {
		case errors.Is(err, service.ErrInvalidInput):
			c.JSON(http.StatusBadRequest, gin.H{"error": "email required, password must be at least 8 characters"})
		case errors.Is(err, service.ErrConflict):
			c.JSON(http.StatusConflict, gin.H{"error": "email already registered"})
		default:
			h.serverError(c, err)
		}
		return
	}
	c.JSON(http.StatusCreated, gin.H{"id": user.ID, "email": user.Email})
}

func (h *Handler) Login(c *gin.Context) {
	var req loginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}
	user, err := h.service.Authenticate(c.Request.Context(), req.Email, req.Password)
	if err != nil {
		if errors.Is(err, service.ErrInvalidPassword) {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid email or password"})
			return
		}
		h.serverError(c, err)
		return
	}
	token, err := auth.GenerateToken(h.jwtSecret, user.ID, user.Email)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"token": token})
}

func (h *Handler) Logout(c *gin.Context) {
	// Stateless JWT — nothing to invalidate server-side; the client discards its token.
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

func (h *Handler) Me(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	user, err := h.service.GetUserByID(c.Request.Context(), userID)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"id": user.ID, "email": user.Email, "name": user.Name, "cefr_level": user.CEFRLevel})
}

type updateProfileRequest struct {
	Name  string `json:"name"`
	Email string `json:"email"`
}

func (h *Handler) UpdateProfile(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	var req updateProfileRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
		return
	}
	if err := h.service.UpdateUserProfile(c.Request.Context(), userID, req.Name, req.Email); err != nil {
		switch {
		case errors.Is(err, service.ErrInvalidInput):
			c.JSON(http.StatusBadRequest, gin.H{"error": "email is required, name must be at most 80 characters"})
		case errors.Is(err, service.ErrConflict):
			c.JSON(http.StatusConflict, gin.H{"error": "email already in use"})
		case errors.Is(err, service.ErrNotFound):
			c.JSON(http.StatusNotFound, gin.H{"error": "user not found"})
		default:
			h.serverError(c, err)
		}
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}
