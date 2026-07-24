package api_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/cookiejar"
	"net/http/httptest"
	"os"
	"testing"

	"anki/internal/ai"
	"anki/internal/api"
	"anki/internal/auth"
	"anki/internal/service"
	"anki/internal/storage"

	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.uber.org/zap"
)

// newTestServer wires up just enough of main.go's routing (public /auth/guest,
// protected /words) to exercise the guest flow over real HTTP, cookies included.
// Requires DATABASE_URL to point at a disposable Postgres with migrations applied
// (see IMPROVEMENTS_SPEC.md Epic 5 for the docker/goose setup used to run this).
func newTestServer(t *testing.T) *httptest.Server {
	t.Helper()
	dsn := os.Getenv("DATABASE_URL")
	if dsn == "" {
		t.Skip("DATABASE_URL not set — skipping guest auth integration test")
	}

	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		t.Fatalf("connect to test db: %v", err)
	}
	t.Cleanup(pool.Close)

	repo := storage.NewRepository(pool)
	wordService := service.NewWordService(repo, zap.NewNop())
	handler := api.NewHandler(wordService, (*ai.Client)(nil), zap.NewNop(), "test-secret", false)

	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.POST("/api/v1/auth/guest", handler.GuestLogin)
	protected := router.Group("/api/v1")
	protected.Use(auth.RequireAuth("test-secret"))
	protected.GET("/words", handler.ListWords)
	protected.POST("/words", handler.AddWord)

	server := httptest.NewServer(router)
	t.Cleanup(server.Close)
	return server
}

type guestLoginResponse struct {
	Token   string `json:"token"`
	ID      int64  `json:"id"`
	IsGuest bool   `json:"is_guest"`
}

func guestLogin(t *testing.T, client *http.Client, baseURL string) guestLoginResponse {
	t.Helper()
	res, err := client.Post(baseURL+"/api/v1/auth/guest", "application/json", nil)
	if err != nil {
		t.Fatalf("guest login request: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("guest login: expected 200, got %d", res.StatusCode)
	}
	var body guestLoginResponse
	if err := json.NewDecoder(res.Body).Decode(&body); err != nil {
		t.Fatalf("decode guest login response: %v", err)
	}
	if !body.IsGuest {
		t.Fatalf("expected is_guest=true in guest login response")
	}
	return body
}

func addWord(t *testing.T, client *http.Client, baseURL, token, word string) {
	t.Helper()
	payload, _ := json.Marshal(map[string]string{"word": word, "translation": "тест"})
	req, err := http.NewRequest(http.MethodPost, baseURL+"/api/v1/words", bytes.NewReader(payload))
	if err != nil {
		t.Fatalf("build add word request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	res, err := client.Do(req)
	if err != nil {
		t.Fatalf("add word request: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusCreated {
		t.Fatalf("add word: expected 201, got %d", res.StatusCode)
	}
}

func listWords(t *testing.T, client *http.Client, baseURL, token string) []map[string]any {
	t.Helper()
	req, err := http.NewRequest(http.MethodGet, baseURL+"/api/v1/words", nil)
	if err != nil {
		t.Fatalf("build list words request: %v", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)
	res, err := client.Do(req)
	if err != nil {
		t.Fatalf("list words request: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("list words: expected 200, got %d", res.StatusCode)
	}
	var words []map[string]any
	if err := json.NewDecoder(res.Body).Decode(&words); err != nil {
		t.Fatalf("decode words response: %v", err)
	}
	return words
}

// TestGuestLogin_PersistsAcrossVisits reproduces the spec's own acceptance
// scenario: a guest is created, adds a word, "closes the tab" (a fresh HTTP
// client reusing only the persistent cookie, discarding the first client's
// in-memory session token), and revisits — they must land on the same account
// with the same data, purely via the guest-recognition cookie.
func TestGuestLogin_PersistsAcrossVisits(t *testing.T) {
	server := newTestServer(t)

	jar, err := cookiejar.New(nil)
	if err != nil {
		t.Fatalf("build cookie jar: %v", err)
	}
	firstVisit := &http.Client{Jar: jar}

	first := guestLogin(t, firstVisit, server.URL)
	addWord(t, firstVisit, server.URL, first.Token, "smuggle")

	// New guests are seeded with a starter deck (same as a fresh registered
	// signup), so assert presence of the added word, not an exact count.
	words := listWords(t, firstVisit, server.URL, first.Token)
	if !containsWord(words, "smuggle") {
		t.Fatalf("word just added is missing right after adding it: %v", words)
	}

	// Simulate closing the tab: a brand new client with no bearer token in memory,
	// but the SAME cookie jar (the browser would have kept the persistent cookie).
	secondVisit := &http.Client{Jar: jar}
	second := guestLogin(t, secondVisit, server.URL)

	if second.ID != first.ID {
		t.Fatalf("revisit created a new guest (id %d) instead of recognizing the original (id %d)", second.ID, first.ID)
	}

	wordsAfterRevisit := listWords(t, secondVisit, server.URL, second.Token)
	if !containsWord(wordsAfterRevisit, "smuggle") {
		t.Fatalf("word added before the revisit is missing after it: %v", wordsAfterRevisit)
	}
}

func containsWord(words []map[string]any, target string) bool {
	for _, w := range words {
		if w["word"] == target {
			return true
		}
	}
	return false
}

// TestGuestLogin_WithoutCookie_CreatesDistinctGuests guards against the opposite
// failure mode: two genuinely separate first-time visitors (no shared cookie
// jar) must NOT be merged into the same guest account.
func TestGuestLogin_WithoutCookie_CreatesDistinctGuests(t *testing.T) {
	server := newTestServer(t)

	jarA, _ := cookiejar.New(nil)
	jarB, _ := cookiejar.New(nil)
	clientA := &http.Client{Jar: jarA}
	clientB := &http.Client{Jar: jarB}

	a := guestLogin(t, clientA, server.URL)
	b := guestLogin(t, clientB, server.URL)

	if a.ID == b.ID {
		t.Fatalf("two independent visitors were assigned the same guest id %d", a.ID)
	}
}
