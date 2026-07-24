package auth

import (
	"errors"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const tokenTTL = 30 * 24 * time.Hour

// GuestDeviceTokenTTL bounds the persistent guest-recognition cookie, not the API
// session itself (see GenerateGuestDeviceToken). 400 days is Safari's own hard cap
// on any cookie's lifetime, so there is no point asking for longer than that.
const GuestDeviceTokenTTL = 400 * 24 * time.Hour

type Claims struct {
	UserID int64  `json:"user_id"`
	Email  string `json:"email"`
	jwt.RegisteredClaims
}

func generateToken(secret string, userID int64, email string, ttl time.Duration) (string, error) {
	now := time.Now()
	claims := Claims{
		UserID: userID,
		Email:  email,
		RegisteredClaims: jwt.RegisteredClaims{
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(ttl)),
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(secret))
}

// GenerateToken issues a regular API-session token (Bearer header), used for every
// authenticated request regardless of whether the user is a guest or registered.
func GenerateToken(secret string, userID int64, email string) (string, error) {
	return generateToken(secret, userID, email, tokenTTL)
}

// GenerateGuestDeviceToken issues the long-lived token stored in the guest-recognition
// cookie only. It is never sent as a Bearer token — /auth/guest reads it back to
// re-identify a returning guest's device and then mints a fresh, short-lived
// GenerateToken session for actual API calls.
func GenerateGuestDeviceToken(secret string, userID int64, email string) (string, error) {
	return generateToken(secret, userID, email, GuestDeviceTokenTTL)
}

func ValidateToken(secret, tokenString string) (*Claims, error) {
	claims := &Claims{}
	token, err := jwt.ParseWithClaims(tokenString, claims, func(t *jwt.Token) (interface{}, error) {
		return []byte(secret), nil
	})
	if err != nil {
		return nil, err
	}
	if !token.Valid {
		return nil, errors.New("invalid token")
	}
	return claims, nil
}
