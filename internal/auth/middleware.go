package auth

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
)

const userIDContextKey = "user_id"

func RequireAuth(secret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		header := c.GetHeader("Authorization")
		token := strings.TrimPrefix(header, "Bearer ")
		if token == "" || token == header {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing bearer token"})
			return
		}
		claims, err := ValidateToken(secret, token)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid or expired token"})
			return
		}
		c.Set(userIDContextKey, claims.UserID)
		c.Set("email", claims.Email)
		c.Next()
	}
}

// UserIDFromContext returns the authenticated user id set by RequireAuth.
// Only call it from routes behind RequireAuth — it panics otherwise, since a
// missing user_id there means the middleware chain is misconfigured.
func UserIDFromContext(c *gin.Context) int64 {
	return c.MustGet(userIDContextKey).(int64)
}
