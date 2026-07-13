package service

import (
	"context"
	"errors"
	"strings"
	"time"

	"anki/internal/auth"
	"anki/internal/model"
	"anki/internal/storage"

	"go.uber.org/zap"
)

var (
	ErrInvalidInput    = errors.New("invalid input")
	ErrConflict        = errors.New("conflict")
	ErrNotFound        = errors.New("not found")
	ErrInvalidPassword = errors.New("invalid email or password")
)

type Repository interface {
	ListWords(ctx context.Context, userID int64) ([]model.Word, error)
	AddWord(ctx context.Context, userID int64, w model.Word, now time.Time) (model.Word, error)
	DeleteWord(ctx context.Context, userID int64, id int64) error
	NextReviewWord(ctx context.Context, userID int64, now time.Time, cardType model.CardType) (*model.ReviewCard, error)
	CountDueByType(ctx context.Context, userID int64, now time.Time, cardType model.CardType) (int, error)
	CountDueCloze(ctx context.Context, userID int64, now time.Time) (int, error)
	SelectSessionWords(ctx context.Context, userID int64, now time.Time, limit int) ([]model.SessionWord, error)
	GetCardForRound(ctx context.Context, userID int64, wordID int64, cardType model.CardType) (*model.ReviewCard, error)
	NextAdvancedReviewWord(ctx context.Context, userID int64, now time.Time, cardType model.CardType, minLevel int) (*model.ReviewCard, error)
	CountAdvancedDueByType(ctx context.Context, userID int64, now time.Time, cardType model.CardType, minLevel int) (int, error)
	GetCardProgressByWord(ctx context.Context, userID int64, wordID int64) ([]model.CardProgress, error)
	SaveReviewResult(ctx context.Context, cardID int64, rating string, quality int, state model.ReviewState, now time.Time, responseTimeMS *int) error
	Stats(ctx context.Context, userID int64, now time.Time) (model.Stats, error)
	ActivityDays(ctx context.Context, userID int64, days int) ([]model.ActivityDay, error)
	EnqueueEvent(ctx context.Context, wordID int64, cardType model.CardType, correct bool, responseTimeMS *int, now time.Time) error
	FetchUnpublishedEvents(ctx context.Context, limit int, maxAttempts int) ([]model.OutboxEvent, error)
	MarkEventPublished(ctx context.Context, id int64) error
	MarkEventFailed(ctx context.Context, id int64) error
	CreateUser(ctx context.Context, email, passwordHash string, now time.Time) (model.User, error)
	GetUserByEmail(ctx context.Context, email string) (*model.User, error)
	GetUserByID(ctx context.Context, id int64) (*model.User, error)
	SetUserLevel(ctx context.Context, userID int64, level string) error
	UpdateUserProfile(ctx context.Context, userID int64, name, email string) error
}

type WordService struct {
	repo   Repository
	logger *zap.Logger
}

func NewWordService(repo Repository, logger *zap.Logger) *WordService {
	return &WordService{repo: repo, logger: logger}
}

func (s *WordService) CreateUser(ctx context.Context, email, password string) (model.User, error) {
	email = strings.TrimSpace(strings.ToLower(email))
	if email == "" || len(password) < 8 {
		return model.User{}, ErrInvalidInput
	}
	hash, err := auth.HashPassword(password)
	if err != nil {
		return model.User{}, err
	}
	created, err := s.repo.CreateUser(ctx, email, hash, time.Now().UTC())
	if err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "unique") {
			return model.User{}, ErrConflict
		}
		return model.User{}, err
	}
	s.seedStarterWords(ctx, created.ID)
	return created, nil
}

// starterWords greet a new account with a small ready-made deck instead of an
// empty dictionary — one word from each topic in word_topics.json, so the
// first training session has something to work with immediately.
var starterWords = []model.Word{
	{Word: "journey", Translation: "путешествие, поездка", Transcription: "/ˈdʒɜːrni/", Example: "It was a long journey across the country."},
	{Word: "recipe", Translation: "рецепт", Transcription: "/ˈresəpi/", Example: "She shared her grandmother's recipe with me."},
	{Word: "colleague", Translation: "коллега", Transcription: "/ˈkɒliːɡ/", Example: "My colleague helped me with the presentation."},
	{Word: "confident", Translation: "уверенный в себе", Transcription: "/ˈkɒnfɪdənt/", Example: "She spoke in a confident voice."},
	{Word: "cozy", Translation: "уютный", Transcription: "/ˈkoʊzi/", Example: "The cabin felt cozy and warm."},
	{Word: "device", Translation: "устройство", Transcription: "/dɪˈvaɪs/", Example: "This device connects to your phone via Bluetooth."},
	{Word: "forecast", Translation: "прогноз погоды", Transcription: "/ˈfɔːrkæst/", Example: "The forecast predicts rain tomorrow."},
	{Word: "healthy", Translation: "здоровый", Transcription: "/ˈhelθi/", Example: "Eating vegetables keeps you healthy."},
	{Word: "achievement", Translation: "достижение", Transcription: "/əˈtʃiːvmənt/", Example: "Winning the award was a great achievement."},
	{Word: "grateful", Translation: "благодарный", Transcription: "/ˈɡreɪtfəl/", Example: "I'm grateful for your help."},
}

func (s *WordService) seedStarterWords(ctx context.Context, userID int64) {
	now := time.Now().UTC()
	for _, w := range starterWords {
		if _, err := s.repo.AddWord(ctx, userID, w, now); err != nil {
			s.logger.Warn("seed starter word failed", zap.Int64("user_id", userID), zap.String("word", w.Word), zap.Error(err))
		}
	}
}

func (s *WordService) Authenticate(ctx context.Context, email, password string) (model.User, error) {
	email = strings.TrimSpace(strings.ToLower(email))
	user, err := s.repo.GetUserByEmail(ctx, email)
	if errors.Is(err, storage.ErrNotFound) {
		return model.User{}, ErrInvalidPassword
	}
	if err != nil {
		return model.User{}, err
	}
	if !auth.CheckPassword(user.PasswordHash, password) {
		return model.User{}, ErrInvalidPassword
	}
	return *user, nil
}

func (s *WordService) GetUserByID(ctx context.Context, userID int64) (model.User, error) {
	user, err := s.repo.GetUserByID(ctx, userID)
	if errors.Is(err, storage.ErrNotFound) {
		return model.User{}, ErrNotFound
	}
	if err != nil {
		return model.User{}, err
	}
	return *user, nil
}

func (s *WordService) SetUserLevel(ctx context.Context, userID int64, level string) error {
	err := s.repo.SetUserLevel(ctx, userID, level)
	if errors.Is(err, storage.ErrNotFound) {
		return ErrNotFound
	}
	return err
}

func (s *WordService) UpdateUserProfile(ctx context.Context, userID int64, name, email string) error {
	name = strings.TrimSpace(name)
	email = strings.TrimSpace(strings.ToLower(email))
	if email == "" || len(name) > 80 {
		return ErrInvalidInput
	}
	err := s.repo.UpdateUserProfile(ctx, userID, name, email)
	if errors.Is(err, storage.ErrNotFound) {
		return ErrNotFound
	}
	if err != nil && strings.Contains(strings.ToLower(err.Error()), "unique") {
		return ErrConflict
	}
	return err
}

func (s *WordService) ListWords(ctx context.Context, userID int64) ([]model.Word, error) {
	return s.repo.ListWords(ctx, userID)
}

func (s *WordService) AddWord(ctx context.Context, userID int64, w model.Word) (model.Word, error) {
	w.Word = strings.TrimSpace(w.Word)
	w.Translation = strings.TrimSpace(w.Translation)
	w.Example = strings.TrimSpace(w.Example)
	w.Transcription = strings.TrimSpace(w.Transcription)
	if w.Word == "" || w.Translation == "" {
		return model.Word{}, ErrInvalidInput
	}
	created, err := s.repo.AddWord(ctx, userID, w, time.Now().UTC())
	if err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "unique") {
			return model.Word{}, ErrConflict
		}
		return model.Word{}, err
	}
	return created, nil
}

func (s *WordService) DeleteWord(ctx context.Context, userID int64, id int64) error {
	if id <= 0 {
		return ErrInvalidInput
	}
	err := s.repo.DeleteWord(ctx, userID, id)
	if errors.Is(err, storage.ErrNotFound) {
		return ErrNotFound
	}
	return err
}

func (s *WordService) NextReviewWord(ctx context.Context, userID int64, round int) (*model.ReviewCard, error) {
	cardType, err := cardTypeFromRound(round)
	if err != nil {
		return nil, ErrInvalidInput
	}
	card, err := s.repo.NextReviewWord(ctx, userID, time.Now().UTC(), cardType)
	if errors.Is(err, storage.ErrNotFound) {
		return nil, ErrNotFound
	}
	return card, err
}

func (s *WordService) BuildSession(ctx context.Context, userID int64, limit int) ([]model.SessionWord, error) {
	if limit <= 0 || limit > 50 {
		limit = 15
	}
	return s.repo.SelectSessionWords(ctx, userID, time.Now().UTC(), limit)
}

func (s *WordService) GetCardForRound(ctx context.Context, userID int64, wordID int64, round int) (*model.ReviewCard, error) {
	if wordID <= 0 {
		return nil, ErrInvalidInput
	}
	cardType, err := cardTypeFromRound(round)
	if err != nil {
		return nil, ErrInvalidInput
	}
	card, err := s.repo.GetCardForRound(ctx, userID, wordID, cardType)
	if errors.Is(err, storage.ErrNotFound) {
		return nil, ErrNotFound
	}
	return card, err
}

func (s *WordService) SubmitReview(ctx context.Context, userID int64, wordID int64, round int, correct bool) error {
	if wordID <= 0 {
		return ErrInvalidInput
	}
	targetType, err := cardTypeFromRound(round)
	if err != nil {
		return ErrInvalidInput
	}
	progresses, err := s.repo.GetCardProgressByWord(ctx, userID, wordID)
	if errors.Is(err, storage.ErrNotFound) {
		return ErrNotFound
	}
	if err != nil {
		return err
	}

	now := time.Now().UTC()
	for _, progress := range progresses {
		if progress.Type != targetType {
			continue
		}
		updated := s.nextLevelState(progress.State, correct, now)
		rating := "again"
		quality := 1
		if correct {
			rating = "good"
			quality = 4
		}
		if err := s.repo.SaveReviewResult(ctx, progress.CardID, rating, quality, updated, now, nil); errors.Is(err, storage.ErrNotFound) {
			return ErrNotFound
		} else if err != nil {
			return err
		}
		s.enqueueEvent(ctx, wordID, targetType, correct, nil, now)
		break
	}
	return nil
}

func (s *WordService) Stats(ctx context.Context, userID int64) (model.Stats, error) {
	return s.repo.Stats(ctx, userID, time.Now().UTC())
}

func (s *WordService) RoundStats(ctx context.Context, userID int64) (model.RoundStats, error) {
	const perRoundLimit = 15
	now := time.Now().UTC()
	r1, err := s.repo.CountDueByType(ctx, userID, now, model.CardTypeENRU)
	if err != nil {
		return model.RoundStats{}, err
	}
	r2, err := s.repo.CountDueByType(ctx, userID, now, model.CardTypeRUEN)
	if err != nil {
		return model.RoundStats{}, err
	}
	r3, err := s.repo.CountDueByType(ctx, userID, now, model.CardTypeListening)
	if err != nil {
		return model.RoundStats{}, err
	}
	r4, err := s.repo.CountDueCloze(ctx, userID, now)
	if err != nil {
		return model.RoundStats{}, err
	}
	return model.RoundStats{
		Round1Due:    r1,
		Round2Due:    r2,
		Round3Due:    r3,
		Round4Due:    r4,
		Round1Target: min(r1, perRoundLimit),
		Round2Target: min(r2, perRoundLimit),
		Round3Target: min(r3, perRoundLimit),
		Round4Target: min(r4, perRoundLimit),
	}, nil
}

func (s *WordService) ActivityDays(ctx context.Context, userID int64, days int) ([]model.ActivityDay, error) {
	if days <= 0 || days > 366 {
		days = 90
	}
	return s.repo.ActivityDays(ctx, userID, days)
}

// TODO: вернуть 2, когда накопится достаточно слов высокого уровня.
const advancedMinLevel = 1

func (s *WordService) AdvancedRoundStats(ctx context.Context, userID int64) (model.AdvancedRoundStats, error) {
	const perRoundLimit = 15
	now := time.Now().UTC()
	speakingDue, err := s.repo.CountAdvancedDueByType(ctx, userID, now, model.CardTypeSpeaking, advancedMinLevel)
	if err != nil {
		return model.AdvancedRoundStats{}, err
	}
	timedDue, err := s.repo.CountAdvancedDueByType(ctx, userID, now, model.CardTypeTimed, advancedMinLevel)
	if err != nil {
		return model.AdvancedRoundStats{}, err
	}
	speakingClozeDue, err := s.repo.CountAdvancedDueByType(ctx, userID, now, model.CardTypeSpeakingCloze, advancedMinLevel)
	if err != nil {
		return model.AdvancedRoundStats{}, err
	}
	return model.AdvancedRoundStats{
		SpeakingDue:         speakingDue,
		TimedDue:            timedDue,
		SpeakingClozeDue:    speakingClozeDue,
		SpeakingTarget:      min(speakingDue, perRoundLimit),
		TimedTarget:         min(timedDue, perRoundLimit),
		SpeakingClozeTarget: min(speakingClozeDue, perRoundLimit),
		MinLevel:            advancedMinLevel,
	}, nil
}

func (s *WordService) NextAdvancedReviewWord(ctx context.Context, userID int64, round int) (*model.ReviewCard, error) {
	cardType, err := advancedCardTypeFromRound(round)
	if err != nil {
		return nil, ErrInvalidInput
	}
	card, err := s.repo.NextAdvancedReviewWord(ctx, userID, time.Now().UTC(), cardType, advancedMinLevel)
	if errors.Is(err, storage.ErrNotFound) {
		return nil, ErrNotFound
	}
	return card, err
}

func (s *WordService) SubmitAdvancedReview(ctx context.Context, userID int64, wordID int64, round int, correct bool, responseTimeMS *int) error {
	if wordID <= 0 {
		return ErrInvalidInput
	}
	targetType, err := advancedCardTypeFromRound(round)
	if err != nil {
		return ErrInvalidInput
	}
	progresses, err := s.repo.GetCardProgressByWord(ctx, userID, wordID)
	if errors.Is(err, storage.ErrNotFound) {
		return ErrNotFound
	}
	if err != nil {
		return err
	}

	now := time.Now().UTC()
	for _, progress := range progresses {
		if progress.Type != targetType {
			continue
		}
		updated := s.nextLevelState(progress.State, correct, now)
		rating := "again"
		quality := 1
		if correct {
			rating = "good"
			quality = 4
		}
		if err := s.repo.SaveReviewResult(ctx, progress.CardID, rating, quality, updated, now, responseTimeMS); errors.Is(err, storage.ErrNotFound) {
			return ErrNotFound
		} else if err != nil {
			return err
		}
		s.enqueueEvent(ctx, wordID, targetType, correct, responseTimeMS, now)
		break
	}
	return nil
}

// enqueueEvent records a learning event for the background publisher to relay to
// repetitor. Failure here doesn't affect SRS state, which is already saved — only logged.
func (s *WordService) enqueueEvent(ctx context.Context, wordID int64, cardType model.CardType, correct bool, responseTimeMS *int, now time.Time) {
	if err := s.repo.EnqueueEvent(ctx, wordID, cardType, correct, responseTimeMS, now); err != nil && s.logger != nil {
		s.logger.Warn("enqueue learning event failed", zap.Int64("word_id", wordID), zap.Error(err))
	}
}

func advancedCardTypeFromRound(round int) (model.CardType, error) {
	switch round {
	case 1:
		return model.CardTypeSpeaking, nil
	case 2:
		return model.CardTypeTimed, nil
	case 3:
		return model.CardTypeSpeakingCloze, nil
	default:
		return "", errors.New("invalid round")
	}
}

func (s *WordService) nextLevelState(state model.ReviewState, correct bool, now time.Time) model.ReviewState {
	intervals := []int{1, 2, 3, 7, 15, 30, 30, 60}
	currentLevel := state.Repetition
	if currentLevel < 0 {
		currentLevel = 0
	}
	if correct {
		if currentLevel < len(intervals) {
			currentLevel++
		}
		state.Repetition = currentLevel
		if currentLevel == 0 {
			state.Interval = 0
			state.NextReview = now
		} else {
			state.Interval = intervals[currentLevel-1]
			state.NextReview = now.AddDate(0, 0, state.Interval)
		}
		state.CorrectCount++
		state.Status = model.CardStatusReview
		return state
	}
	wasHigherLevel := currentLevel > 0
	if currentLevel > 0 {
		currentLevel--
	}
	state.Repetition = currentLevel
	state.Interval = 0
	if wasHigherLevel {
		state.NextReview = now.AddDate(0, 0, 1)
	} else {
		state.NextReview = now
	}
	state.WrongCount++
	state.Status = model.CardStatusLearning
	return state
}

func cardTypeFromRound(round int) (model.CardType, error) {
	switch round {
	case 1:
		return model.CardTypeENRU, nil
	case 2:
		return model.CardTypeRUEN, nil
	case 3:
		return model.CardTypeListening, nil
	case 4:
		return model.CardTypeCloze, nil
	default:
		return "", errors.New("invalid round")
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
