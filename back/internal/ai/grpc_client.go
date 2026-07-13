package ai

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	tutorpb "anki/internal/ai/pb/tutor/v1"

	"go.uber.org/zap"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/protobuf/types/known/emptypb"
)

// Client talks to adaptive-learning-repetitor over gRPC.
type Client struct {
	addr           string
	email          string
	password       string
	projectID      string
	chatID         string
	practiceChatID string
	conn           *grpc.ClientConn
	rpc            tutorpb.TutorServiceClient
	logger         *zap.Logger
	mu             sync.RWMutex
	ready          bool
	lastError      string
}

// Status describes repetitor connectivity for the UI.
type Status struct {
	Ready     bool   `json:"ready"`
	BaseURL   string `json:"base_url"`
	ProjectID string `json:"project_id,omitempty"`
	ChatID    string `json:"chat_id,omitempty"`
	Error     string `json:"error,omitempty"`
}

// PracticeQuestion is one MCQ question with its grounded explanation.
type PracticeQuestion struct {
	Prompt       string   `json:"prompt"`
	Options      []string `json:"options"`
	CorrectIndex int32    `json:"correct_index"`
	Explanation  string   `json:"explanation"`
}

// PracticeResult is the structured practice payload returned to the frontend.
type PracticeResult struct {
	Questions []PracticeQuestion `json:"questions"`
	Source    string             `json:"source"`
	Sources   []string           `json:"sources,omitempty"`
}

// EnrichResult is the AI-generated word draft returned to the frontend.
type EnrichResult struct {
	Translation   string `json:"translation"`
	Example       string `json:"example"`
	Transcription string `json:"transcription"`
	Source        string `json:"source"`
}

// ExplainResult is the AI-generated mistake explanation returned to the frontend.
type ExplainResult struct {
	Explanation string `json:"explanation"`
	Source      string `json:"source"`
}

// WeakTopic is one entry in the "Слабые темы" list.
type WeakTopic struct {
	Word  string  `json:"word"`
	PKnow float64 `json:"p_know"`
	ALS   float64 `json:"als"`
}

// NewClient dials repetitor gRPC and bootstraps session ids.
func NewClient(logger *zap.Logger) (*Client, error) {
	addr := strings.TrimSpace(getEnv("REPETITOR_GRPC_ADDR", "localhost:50051"))
	email := strings.TrimSpace(os.Getenv("REPETITOR_EMAIL"))
	password := os.Getenv("REPETITOR_PASSWORD")

	c := &Client{
		addr:           addr,
		email:          email,
		password:       password,
		projectID:      strings.TrimSpace(os.Getenv("REPETITOR_PROJECT_ID")),
		chatID:         strings.TrimSpace(os.Getenv("REPETITOR_CHAT_ID")),
		practiceChatID: strings.TrimSpace(os.Getenv("REPETITOR_PRACTICE_CHAT_ID")),
		logger:         logger,
	}

	if email == "" || password == "" {
		c.setError("REPETITOR_EMAIL and REPETITOR_PASSWORD are required")
		return c, nil
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	if err := c.connect(ctx); err != nil {
		c.setError(err.Error())
		logger.Warn("repetitor grpc connect failed", zap.Error(err))
		return c, nil
	}

	if err := c.bootstrap(ctx); err != nil {
		c.setError(err.Error())
		logger.Warn("repetitor grpc bootstrap failed", zap.Error(err))
		_ = c.close()
		return c, nil
	}

	c.mu.Lock()
	c.ready = true
	c.lastError = ""
	c.mu.Unlock()

	logger.Info("repetitor grpc client ready",
		zap.String("addr", addr),
		zap.String("project_id", c.projectID),
		zap.String("chat_id", c.chatID),
	)
	return c, nil
}

func (c *Client) connect(ctx context.Context) error {
	conn, err := grpc.DialContext(ctx, c.addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock(),
	)
	if err != nil {
		return fmt.Errorf("grpc dial %s: %w", c.addr, err)
	}
	c.conn = conn
	c.rpc = tutorpb.NewTutorServiceClient(conn)
	return nil
}

func (c *Client) close() error {
	if c.conn == nil {
		return nil
	}
	err := c.conn.Close()
	c.conn = nil
	c.rpc = nil
	return err
}

func (c *Client) Ready() bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.ready
}

func (c *Client) Status() Status {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return Status{
		Ready:     c.ready,
		BaseURL:   c.addr,
		ProjectID: c.projectID,
		ChatID:    c.chatID,
		Error:     c.lastError,
	}
}

func (c *Client) setError(msg string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.ready = false
	c.lastError = msg
}

func (c *Client) bootstrap(ctx context.Context) error {
	resp, err := c.rpc.EnsureSession(ctx, &tutorpb.EnsureSessionRequest{
		Credentials:    c.credentials(),
		ProjectId:      c.projectID,
		ChatId:         c.chatID,
		PracticeChatId: c.practiceChatID,
	})
	if err != nil {
		return err
	}
	if !resp.Ready {
		if resp.Error != "" {
			return errors.New(resp.Error)
		}
		return errors.New("repetitor session not ready")
	}
	c.projectID = resp.ProjectId
	c.chatID = resp.ChatId
	c.practiceChatID = resp.PracticeChatId
	return nil
}

func (c *Client) credentials() *tutorpb.Credentials {
	return &tutorpb.Credentials{
		Email:    c.email,
		Password: c.password,
	}
}

func (c *Client) session() *tutorpb.Session {
	return &tutorpb.Session{
		Credentials:    c.credentials(),
		ProjectId:      c.projectID,
		ChatId:         c.chatID,
		PracticeChatId: c.practiceChatID,
	}
}

// StreamChat proxies gRPC chat events as SSE frames for the browser.
func (c *Client) StreamChat(ctx context.Context, message string, write func([]byte) error) error {
	if !c.Ready() {
		return errors.New(c.Status().Error)
	}

	stream, err := c.rpc.Chat(ctx, &tutorpb.ChatRequest{
		Session: c.session(),
		Message: message,
	})
	if err != nil {
		return err
	}

	for {
		event, recvErr := stream.Recv()
		if recvErr != nil {
			if errors.Is(recvErr, context.Canceled) || stream.Context().Err() != nil {
				return nil
			}
			return recvErr
		}
		frame, err := chatEventToSSE(event)
		if err != nil {
			return err
		}
		if frame != "" {
			if wErr := write([]byte(frame)); wErr != nil {
				return wErr
			}
		}
		if event.Type == "done" {
			return nil
		}
	}
}

// GeneratePractice calls repetitor unary RPC with RAG + LLM.
func (c *Client) GeneratePractice(ctx context.Context, words []string, level string) (PracticeResult, error) {
	if !c.Ready() {
		return PracticeResult{}, errors.New(c.Status().Error)
	}
	resp, err := c.rpc.GeneratePractice(ctx, &tutorpb.PracticeRequest{
		Session: c.session(),
		Words:   words,
		Level:   level,
	})
	if err != nil {
		return PracticeResult{}, err
	}
	questions := make([]PracticeQuestion, 0, len(resp.Questions))
	for _, q := range resp.Questions {
		questions = append(questions, PracticeQuestion{
			Prompt:       q.Prompt,
			Options:      q.Options,
			CorrectIndex: q.CorrectIndex,
			Explanation:  q.Explanation,
		})
	}
	return PracticeResult{
		Questions: questions,
		Source:    resp.Source,
		Sources:   resp.RagSources,
	}, nil
}

// PublishEvent sends one review answer to repetitor as a learning event (BKT/ALS input).
func (c *Client) PublishEvent(ctx context.Context, word string, correct bool, responseTimeMs, attempts int, cardType, difficulty string) error {
	if !c.Ready() {
		return errors.New(c.Status().Error)
	}
	_, err := c.rpc.PublishEvent(ctx, &tutorpb.PublishEventRequest{
		Session:        c.session(),
		Word:           word,
		Correct:        correct,
		ResponseTimeMs: int32(responseTimeMs),
		Attempts:       int32(attempts),
		CardType:       cardType,
		Difficulty:     difficulty,
	})
	return err
}

// ExplainError asks repetitor to explain why a training answer was wrong.
func (c *Client) ExplainError(ctx context.Context, word, expected, got, sentence string) (ExplainResult, error) {
	if !c.Ready() {
		return ExplainResult{}, errors.New(c.Status().Error)
	}
	resp, err := c.rpc.ExplainError(ctx, &tutorpb.ExplainErrorRequest{
		Session:  c.session(),
		Word:     word,
		Expected: expected,
		Got:      got,
		Sentence: sentence,
	})
	if err != nil {
		return ExplainResult{}, err
	}
	return ExplainResult{
		Explanation: resp.Explanation,
		Source:      resp.Source,
	}, nil
}

// GetWeakTopics returns the project's weakest word-topics from repetitor mastery.
func (c *Client) GetWeakTopics(ctx context.Context, limit int32) ([]WeakTopic, error) {
	if !c.Ready() {
		return nil, errors.New(c.Status().Error)
	}
	resp, err := c.rpc.GetWeakTopics(ctx, &tutorpb.GetWeakTopicsRequest{
		Session: c.session(),
		Limit:   limit,
	})
	if err != nil {
		return nil, err
	}
	topics := make([]WeakTopic, 0, len(resp.Topics))
	for _, t := range resp.Topics {
		topics = append(topics, WeakTopic{Word: t.Word, PKnow: t.PKnow, ALS: t.Als})
	}
	return topics, nil
}

// EnrichWord calls repetitor to draft translation/example/transcription for a word.
func (c *Client) EnrichWord(ctx context.Context, word, level string) (EnrichResult, error) {
	if !c.Ready() {
		return EnrichResult{}, errors.New(c.Status().Error)
	}
	resp, err := c.rpc.EnrichWord(ctx, &tutorpb.EnrichWordRequest{
		Session: c.session(),
		Word:    word,
		Level:   level,
	})
	if err != nil {
		return EnrichResult{}, err
	}
	return EnrichResult{
		Translation:   resp.Translation,
		Example:       resp.Example,
		Transcription: resp.Transcription,
		Source:        resp.Source,
	}, nil
}

// SearchRag queries a specific RAG corpus.
func (c *Client) SearchRag(ctx context.Context, query string, corpus tutorpb.RagCorpus, limit int32) (*tutorpb.RagSearchResponse, error) {
	if !c.Ready() {
		return nil, errors.New(c.Status().Error)
	}
	return c.rpc.SearchRag(ctx, &tutorpb.RagSearchRequest{
		Session: c.session(),
		Query:   query,
		Corpus:  corpus,
		Limit:   limit,
	})
}

// Health checks repetitor gRPC availability.
func (c *Client) Health(ctx context.Context) (*tutorpb.StatusResponse, error) {
	if c.rpc == nil {
		return nil, errors.New("grpc client not connected")
	}
	return c.rpc.Health(ctx, &emptypb.Empty{})
}

func chatEventToSSE(event *tutorpb.ChatEvent) (string, error) {
	payload := map[string]string{"type": event.Type}
	switch event.Type {
	case "content":
		payload["content"] = event.Content
	case "status":
		payload["status"] = event.Status
	case "error":
		payload["error"] = event.Error
	case "done":
	default:
		if event.Content != "" {
			payload["content"] = event.Content
		}
	}
	b, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	return "data: " + string(b) + "\n\n", nil
}

func getEnv(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}
