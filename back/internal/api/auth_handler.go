package api

import (
	"errors"
	"net/http"

	"anki/internal/auth"
	"anki/internal/model"
	"anki/internal/service"

	"github.com/gin-gonic/gin"
)

// guestCookieName holds the long-lived guest-recognition token — separate from the
// Authorization-header session token — so a returning guest can be re-identified
// even after localStorage is cleared or evicted (e.g. Safari ITP).
const guestCookieName = "anki_guest_device"

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
	// Also clear the guest-recognition cookie: without this, a guest who explicitly
	// logs out would be silently signed back in as the same guest on next visit.
	c.SetCookie(guestCookieName, "", -1, "/", "", h.cookieSecure, true)
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// GuestLogin provisions frictionless access without registration. If the caller
// already carries a valid guest-recognition cookie, it re-identifies that same
// guest instead of creating a new one — so closing the tab and coming back keeps
// the guest's vocabulary and progress. Otherwise a brand-new guest account is
// created. Either way a fresh, short-lived API session token is minted and the
// long-lived recognition cookie is (re-)set with a sliding expiration.
func (h *Handler) GuestLogin(c *gin.Context) {
	if deviceToken, err := c.Cookie(guestCookieName); err == nil && deviceToken != "" {
		if claims, err := auth.ValidateToken(h.jwtSecret, deviceToken); err == nil {
			if user, err := h.service.GetUserByID(c.Request.Context(), claims.UserID); err == nil && user.IsGuest {
				h.issueGuestSession(c, user)
				return
			}
		}
	}

	user, err := h.service.CreateGuestUser(c.Request.Context())
	if err != nil {
		h.serverError(c, err)
		return
	}
	h.issueGuestSession(c, user)
}

func (h *Handler) issueGuestSession(c *gin.Context, user model.User) {
	sessionToken, err := auth.GenerateToken(h.jwtSecret, user.ID, user.Email)
	if err != nil {
		h.serverError(c, err)
		return
	}
	deviceToken, err := auth.GenerateGuestDeviceToken(h.jwtSecret, user.ID, user.Email)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.SetSameSite(http.SameSiteLaxMode)
	c.SetCookie(guestCookieName, deviceToken, int(auth.GuestDeviceTokenTTL.Seconds()), "/", "", h.cookieSecure, true)
	c.JSON(http.StatusOK, gin.H{"token": sessionToken, "id": user.ID, "email": user.Email, "is_guest": true})
}

func (h *Handler) Me(c *gin.Context) {
	userID := auth.UserIDFromContext(c)
	user, err := h.service.GetUserByID(c.Request.Context(), userID)
	if err != nil {
		h.serverError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"id": user.ID, "email": user.Email, "name": user.Name, "cefr_level": user.CEFRLevel, "is_guest": user.IsGuest,
	})
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
