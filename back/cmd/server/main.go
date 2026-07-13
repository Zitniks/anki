package main

import (
	"bufio"
	"context"
	"errors"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"anki/internal/ai"
	"anki/internal/api"
	"anki/internal/auth"
	"anki/internal/model"
	"anki/internal/service"
	"anki/internal/storage"

	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.uber.org/zap"
)

func main() {
	logger, err := zap.NewProduction()
	if err != nil {
		panic(err)
	}
	defer logger.Sync()

	ctx := context.Background()

	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		logger.Fatal("DATABASE_URL is not set")
	}
	jwtSecret := os.Getenv("JWT_SECRET")
	if jwtSecret == "" {
		logger.Fatal("JWT_SECRET is not set")
	}

	cfg, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		logger.Fatal("parse database url", zap.Error(err))
	}
	if maxConns := getEnvInt("DB_MAX_CONNS", 0); maxConns > 0 {
		cfg.MaxConns = int32(maxConns)
	}
	if minConns := getEnvInt("DB_MIN_CONNS", 0); minConns > 0 {
		cfg.MinConns = int32(minConns)
	}

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		logger.Fatal("open db pool", zap.Error(err))
	}
	defer pool.Close()

	if err := pool.Ping(ctx); err != nil {
		logger.Fatal("ping db", zap.Error(err))
	}

	repo := storage.NewRepository(pool)
	if added, updated, err := syncWordPairsFromFile(ctx, repo, "./anki_levels_and_lifecycle_cards.md", legacySyncUserID); err != nil {
		logger.Error("sync words from file", zap.Error(err))
	} else {
		logger.Info("words sync completed", zap.Int("added", added), zap.Int("updated", updated))
	}
	wordService := service.NewWordService(repo, logger)
	repetitorClient, _ := ai.NewClient(logger)
	handler := api.NewHandler(wordService, repetitorClient, logger, jwtSecret)
	go service.RunEventPublisher(ctx, repo, repetitorClient, logger)

	router := gin.New()
	router.Use(gin.Recovery())

	router.Static("/assets", "./web")
	router.Static("/landing-assets", "./landing/dist")
	router.StaticFile("/theory_tenses.json", "./theory_tenses.json")
	router.StaticFile("/word_topics.json", "./word_topics.json")
	router.StaticFile("/book_norwood_builder.json", "./book_norwood_builder.json")
	router.GET("/", func(c *gin.Context) {
		c.File("./landing/dist/index.html")
	})
	router.GET("/app", func(c *gin.Context) {
		c.File("./web/index.html")
	})

	registerAPIRoutes(router.Group("/api/v1"), handler, jwtSecret)
	registerAPIRoutes(router.Group("/api"), handler, jwtSecret)

	addr := getEnv("HTTP_ADDR", ":8080")
	logger.Info("server started", zap.String("addr", addr), zap.String("storage", "postgres"))
	if err := router.Run(addr); err != nil && !errors.Is(err, http.ErrServerClosed) {
		logger.Fatal("run server", zap.Error(err))
	}
}

func registerAPIRoutes(group *gin.RouterGroup, handler *api.Handler, jwtSecret string) {
	group.POST("/auth/register", handler.Register)
	group.POST("/auth/login", handler.Login)

	protected := group.Group("")
	protected.Use(auth.RequireAuth(jwtSecret))

	protected.POST("/auth/logout", handler.Logout)
	protected.GET("/auth/me", handler.Me)
	protected.PATCH("/auth/me", handler.UpdateProfile)
	protected.GET("/placement/questions", handler.PlacementQuestions)
	protected.POST("/placement/submit", handler.PlacementSubmit)

	protected.GET("/words", handler.ListWords)
	protected.POST("/words", handler.AddWord)
	protected.POST("/words/batch", handler.AddWordsBatch)
	protected.POST("/words/enrich", handler.EnrichWord)
	protected.DELETE("/words/:id", handler.DeleteWord)
	protected.GET("/review/next", handler.NextReviewWord)
	protected.GET("/review/session", handler.ReviewSession)
	protected.GET("/review/card", handler.ReviewCard)
	protected.POST("/review", handler.SubmitReview)
	protected.GET("/review/round-stats", handler.RoundStats)
	protected.GET("/review/advanced/round-stats", handler.AdvancedRoundStats)
	protected.GET("/review/advanced/next", handler.NextAdvancedReviewWord)
	protected.POST("/review/advanced", handler.SubmitAdvancedReview)
	protected.POST("/practice/generate", handler.PracticeGenerate)
	protected.GET("/ai/status", handler.AIStatus)
	protected.POST("/ai/chat/stream", handler.AIChatStream)
	protected.POST("/ai/explain-error", handler.ExplainError)
	protected.GET("/ai/weak-topics", handler.WeakTopics)
	protected.GET("/stats/activity", handler.ActivityDays)
	protected.GET("/stats", handler.Stats)
}

func getEnv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	n, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return n
}

// legacySyncUserID owns words synced from anki_levels_and_lifecycle_cards.md — same
// sentinel account (id=1) pre-existing data was assigned to in the multiuser migration.
const legacySyncUserID = 1

func syncWordPairsFromFile(ctx context.Context, repo *storage.Repository, path string, userID int64) (int, int, error) {
	file, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return 0, 0, nil
		}
		return 0, 0, err
	}
	defer file.Close()

	words := make([]model.Word, 0, 256)
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") || !strings.Contains(line, " — ") {
			continue
		}

		parts := strings.SplitN(line, " — ", 2)
		if len(parts) < 2 {
			continue
		}
		word := strings.TrimSpace(parts[0])
		translation := strings.TrimSpace(parts[1])
		if word == "" || translation == "" {
			continue
		}

		words = append(words, model.Word{
			Word:        word,
			Translation: translation,
		})
	}
	if err := scanner.Err(); err != nil {
		return 0, 0, err
	}

	return repo.SyncWordPairs(ctx, userID, words, time.Now().UTC())
}
