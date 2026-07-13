package storage

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"anki/internal/model"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("not found")

type Repository struct {
	pool *pgxpool.Pool
}

func NewRepository(pool *pgxpool.Pool) *Repository {
	return &Repository{pool: pool}
}

func (r *Repository) ListWords(ctx context.Context, userID int64) ([]model.Word, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id, word, translation, COALESCE(example, ''), COALESCE(transcription, ''), created_at
		FROM words
		WHERE user_id = $1
		ORDER BY created_at DESC`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	words := make([]model.Word, 0)
	for rows.Next() {
		var w model.Word
		if err := rows.Scan(&w.ID, &w.Word, &w.Translation, &w.Example, &w.Transcription, &w.CreatedAt); err != nil {
			return nil, err
		}
		words = append(words, w)
	}
	return words, rows.Err()
}

func (r *Repository) AddWord(ctx context.Context, userID int64, w model.Word, now time.Time) (model.Word, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return model.Word{}, err
	}
	defer tx.Rollback(ctx)

	var id int64
	err = tx.QueryRow(ctx, `
		INSERT INTO words(user_id, word, translation, example, transcription)
		VALUES ($1, $2, $3, NULLIF($4, ''), NULLIF($5, ''))
		RETURNING id
	`, userID, w.Word, w.Translation, w.Example, w.Transcription).Scan(&id)
	if err != nil {
		return model.Word{}, err
	}

	if err := ensureWordCards(ctx, tx, id, now.UTC()); err != nil {
		return model.Word{}, err
	}

	if err := tx.Commit(ctx); err != nil {
		return model.Word{}, err
	}

	w.ID = id
	w.CreatedAt = now.UTC()
	return w, nil
}

func (r *Repository) SyncWordPairs(ctx context.Context, userID int64, words []model.Word, now time.Time) (int, int, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return 0, 0, err
	}
	defer tx.Rollback(ctx)

	added := 0
	updated := 0
	for _, w := range words {
		word := strings.TrimSpace(w.Word)
		translation := strings.TrimSpace(w.Translation)
		if word == "" || translation == "" {
			continue
		}

		var (
			id              int64
			prevTranslation string
		)
		err = tx.QueryRow(ctx, `SELECT id, translation FROM words WHERE word = $1 AND user_id = $2`, word, userID).Scan(&id, &prevTranslation)
		if errors.Is(err, pgx.ErrNoRows) {
			insErr := tx.QueryRow(ctx, `
				INSERT INTO words(user_id, word, translation, example, transcription)
				VALUES ($1, $2, $3, NULL, NULL)
				RETURNING id
			`, userID, word, translation).Scan(&id)
			if insErr != nil {
				return added, updated, insErr
			}
			added++
		} else if err != nil {
			return added, updated, err
		} else if strings.TrimSpace(prevTranslation) != translation {
			if _, updErr := tx.Exec(ctx, `UPDATE words SET translation = $1 WHERE id = $2`, translation, id); updErr != nil {
				return added, updated, updErr
			}
			updated++
		}

		if err := ensureWordCards(ctx, tx, id, now.UTC()); err != nil {
			return added, updated, err
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return added, updated, err
	}
	return added, updated, nil
}

func ensureWordCards(ctx context.Context, tx pgx.Tx, wordID int64, now time.Time) error {
	cardTypes := []model.CardType{
		model.CardTypeENRU, model.CardTypeRUEN, model.CardTypeListening,
		model.CardTypeCloze, model.CardTypeSpeaking, model.CardTypeTimed,
		model.CardTypeSpeakingCloze,
	}
	for _, cardType := range cardTypes {
		var cardID int64
		// ON CONFLICT DO UPDATE (no-op) instead of DO NOTHING so RETURNING always fires,
		// even when the card already existed — avoids a second round-trip to fetch its id.
		if err := tx.QueryRow(ctx, `
			INSERT INTO cards(word_id, type, created_at)
			VALUES ($1, $2, $3)
			ON CONFLICT (word_id, type) DO UPDATE SET type = EXCLUDED.type
			RETURNING id
		`, wordID, string(cardType), now).Scan(&cardID); err != nil {
			return err
		}

		if _, err := tx.Exec(ctx, `
			INSERT INTO review_state(card_id, repetition, interval_days, ease_factor, next_review, status, learning_step)
			VALUES ($1, 0, 0, 2.5, $2, 'new', 0)
			ON CONFLICT (card_id) DO NOTHING
		`, cardID, now); err != nil {
			return err
		}
	}

	return nil
}

func (r *Repository) DeleteWord(ctx context.Context, userID int64, id int64) error {
	tag, err := r.pool.Exec(ctx, `DELETE FROM words WHERE id = $1 AND user_id = $2`, id, userID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repository) NextReviewWord(ctx context.Context, userID int64, now time.Time, cardType model.CardType) (*model.ReviewCard, error) {
	var card model.ReviewCard
	err := r.pool.QueryRow(ctx, `
		SELECT
			w.id,
			w.word,
			w.translation,
			COALESCE(w.example, ''),
			COALESCE(w.transcription, ''),
			w.created_at,
			'learning'
		FROM words w
		JOIN cards c ON c.word_id = w.id
		JOIN review_state r ON r.card_id = c.id
		WHERE r.next_review <= $1 AND c.type = $2 AND w.user_id = $3
		ORDER BY
			r.next_review ASC
		LIMIT 1
	`, now.UTC(), string(cardType), userID).Scan(
		&card.WordID,
		&card.Word,
		&card.Translation,
		&card.Example,
		&card.Transcription,
		&card.CreatedAt,
		&card.Status,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &card, nil
}

func (r *Repository) CountDueByType(ctx context.Context, userID int64, now time.Time, cardType model.CardType) (int, error) {
	var total int
	err := r.pool.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM review_state r
		JOIN cards c ON c.id = r.card_id
		JOIN words w ON w.id = c.word_id
		WHERE r.next_review <= $1 AND c.type = $2 AND w.user_id = $3
	`, now.UTC(), string(cardType), userID).Scan(&total)
	return total, err
}

// CountDueCloze counts due cloze cards regardless of whether the word has a static
// example — Example RAG can fill one live at render time (see Handler.ReviewCard).
func (r *Repository) CountDueCloze(ctx context.Context, userID int64, now time.Time) (int, error) {
	return r.CountDueByType(ctx, userID, now, model.CardTypeCloze)
}

func (r *Repository) SelectSessionWords(ctx context.Context, userID int64, now time.Time, limit int) ([]model.SessionWord, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT w.id AS word_id, w.word, MIN(rs.next_review) AS min_due,
		       CASE WHEN TRIM(COALESCE(w.example, '')) != '' THEN 1 ELSE 0 END AS has_example
		FROM cards c
		JOIN review_state rs ON rs.card_id = c.id
		JOIN words w ON w.id = c.word_id
		WHERE c.type IN ($1, $2, $3, $4) AND w.user_id = $5
		GROUP BY w.id
		HAVING SUM(CASE WHEN rs.next_review <= $6 THEN 1 ELSE 0 END) >= 1
		ORDER BY min_due ASC
		LIMIT $7
	`,
		string(model.CardTypeENRU), string(model.CardTypeRUEN), string(model.CardTypeListening), string(model.CardTypeCloze),
		userID, now.UTC(), limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	words := make([]model.SessionWord, 0, limit)
	for rows.Next() {
		var sw model.SessionWord
		var hasExample int
		if err := rows.Scan(&sw.WordID, &sw.Word, &sw.MinDue, &hasExample); err != nil {
			return nil, err
		}
		sw.HasExample = hasExample == 1
		words = append(words, sw)
	}
	return words, rows.Err()
}

func (r *Repository) GetCardForRound(ctx context.Context, userID int64, wordID int64, cardType model.CardType) (*model.ReviewCard, error) {
	var card model.ReviewCard
	err := r.pool.QueryRow(ctx, `
		SELECT w.id, w.word, w.translation, COALESCE(w.example, ''), COALESCE(w.transcription, ''), w.created_at
		FROM words w
		WHERE w.id = $1 AND w.user_id = $2
	`, wordID, userID).Scan(&card.WordID, &card.Word, &card.Translation, &card.Example, &card.Transcription, &card.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	card.Status = model.CardStatusLearning
	if cardType == model.CardTypeCloze && strings.TrimSpace(card.Example) == "" {
		card.Skip = true
	}
	return &card, nil
}

func (r *Repository) NextAdvancedReviewWord(ctx context.Context, userID int64, now time.Time, cardType model.CardType, minLevel int) (*model.ReviewCard, error) {
	var card model.ReviewCard
	err := r.pool.QueryRow(ctx, `
		SELECT
			w.id,
			w.word,
			w.translation,
			COALESCE(w.example, ''),
			COALESCE(w.transcription, ''),
			w.created_at,
			'learning'
		FROM words w
		JOIN cards c ON c.word_id = w.id
		JOIN review_state r ON r.card_id = c.id
		WHERE r.next_review <= $1 AND c.type = $2 AND w.user_id = $3
		  AND w.id IN (`+wordLevelFilter(userID, minLevel)+`)
		ORDER BY r.next_review ASC
		LIMIT 1
	`, now.UTC(), string(cardType), userID).Scan(
		&card.WordID,
		&card.Word,
		&card.Translation,
		&card.Example,
		&card.Transcription,
		&card.CreatedAt,
		&card.Status,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &card, nil
}

func (r *Repository) CountAdvancedDueByType(ctx context.Context, userID int64, now time.Time, cardType model.CardType, minLevel int) (int, error) {
	var total int
	err := r.pool.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM review_state r
		JOIN cards c ON c.id = r.card_id
		JOIN words w ON w.id = c.word_id
		WHERE r.next_review <= $1 AND c.type = $2 AND w.user_id = $3
		  AND w.id IN (`+wordLevelFilter(userID, minLevel)+`)
	`, now.UTC(), string(cardType), userID).Scan(&total)
	return total, err
}

func wordLevelFilter(userID int64, minLevel int) string {
	// ROUND() on Postgres only has a numeric overload, not double precision — NUMERIC cast
	// (was REAL under SQLite, which accepted ROUND() on real directly). userID/minLevel are
	// server-derived ints (JWT claims / route params, never raw user text), so interpolating
	// them into this embedded SQL fragment carries no injection risk.
	return fmt.Sprintf(`
		SELECT c2.word_id
		FROM cards c2
		JOIN review_state r2 ON r2.card_id = c2.id
		JOIN words w2 ON w2.id = c2.word_id
		WHERE w2.user_id = %d
		GROUP BY c2.word_id
		HAVING ROUND(AVG(CAST(r2.repetition AS NUMERIC))) >= %d
	`, userID, minLevel)
}

func (r *Repository) GetCardProgressByWord(ctx context.Context, userID int64, wordID int64) ([]model.CardProgress, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT c.id, c.type, r.repetition, r.interval_days, r.ease_factor, r.next_review, r.correct_count, r.wrong_count, r.status, r.learning_step
		FROM cards c
		JOIN review_state r ON r.card_id = c.id
		JOIN words w ON w.id = c.word_id
		WHERE c.word_id = $1 AND w.user_id = $2
	`, wordID, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	result := make([]model.CardProgress, 0, 3)
	for rows.Next() {
		var cp model.CardProgress
		if err := rows.Scan(
			&cp.CardID,
			&cp.Type,
			&cp.State.Repetition,
			&cp.State.Interval,
			&cp.State.EaseFactor,
			&cp.State.NextReview,
			&cp.State.CorrectCount,
			&cp.State.WrongCount,
			&cp.State.Status,
			&cp.State.LearningStep,
		); err != nil {
			return nil, err
		}
		cp.State.CardID = cp.CardID
		result = append(result, cp)
	}
	if len(result) == 0 {
		return nil, ErrNotFound
	}
	return result, rows.Err()
}

func (r *Repository) GetReviewState(ctx context.Context, cardID int64) (model.ReviewState, error) {
	var s model.ReviewState
	err := r.pool.QueryRow(ctx, `
		SELECT card_id, repetition, interval_days, ease_factor, next_review, correct_count, wrong_count, status, learning_step
		FROM review_state
		WHERE card_id = $1
	`, cardID).Scan(&s.CardID, &s.Repetition, &s.Interval, &s.EaseFactor, &s.NextReview, &s.CorrectCount, &s.WrongCount, &s.Status, &s.LearningStep)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.ReviewState{}, ErrNotFound
	}
	return s, err
}

func (r *Repository) SaveReviewResult(ctx context.Context, cardID int64, rating string, quality int, state model.ReviewState, now time.Time, responseTimeMS *int) error {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	tag, err := tx.Exec(ctx, `
		UPDATE review_state
		SET repetition = $1, interval_days = $2, ease_factor = $3, next_review = $4, correct_count = $5, wrong_count = $6, updated_at = $7, status = $8, learning_step = $9
		WHERE card_id = $10
	`, state.Repetition, state.Interval, state.EaseFactor, state.NextReview.UTC(), state.CorrectCount, state.WrongCount, now.UTC(), string(state.Status), state.LearningStep, cardID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}

	if _, err := tx.Exec(ctx, `
		INSERT INTO review_log(card_id, word_id, quality, rating, interval_after, ease_factor_after, reviewed_at, response_time_ms)
		VALUES ($1, (SELECT word_id FROM cards WHERE id = $2), $3, $4, $5, $6, $7, $8)
	`, cardID, cardID, quality, rating, state.Interval, state.EaseFactor, now.UTC(), responseTimeMS); err != nil {
		return err
	}

	return tx.Commit(ctx)
}

func (r *Repository) Stats(ctx context.Context, userID int64, now time.Time) (model.Stats, error) {
	var stats model.Stats
	if err := r.pool.QueryRow(ctx, `SELECT COUNT(*) FROM words WHERE user_id = $1`, userID).Scan(&stats.TotalWords); err != nil {
		return stats, err
	}
	if err := r.pool.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM review_state r
		JOIN cards c ON c.id = r.card_id
		JOIN words w ON w.id = c.word_id
		WHERE r.next_review <= $1 AND w.user_id = $2
	`, now.UTC(), userID).Scan(&stats.DueToday); err != nil {
		return stats, err
	}
	if err := r.pool.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM (
			SELECT c.word_id
			FROM cards c
			JOIN review_state r ON r.card_id = c.id
			JOIN words w ON w.id = c.word_id
			WHERE w.user_id = $1
			GROUP BY c.word_id
			HAVING ROUND(AVG(CAST(r.repetition AS NUMERIC))) >= 4
		) t
	`, userID).Scan(&stats.Mastered); err != nil {
		return stats, err
	}
	todayUTC := now.UTC().Format("2006-01-02")
	if err := r.pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM review_log rl
		JOIN words w ON w.id = rl.word_id
		WHERE rl.reviewed_at IS NOT NULL AND `+reviewDayExpr()+` = $1 AND w.user_id = $2
	`, todayUTC, userID).Scan(&stats.ReviewsToday); err != nil {
		return stats, err
	}
	var totalToday int
	if err := r.pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM review_log rl
		JOIN words w ON w.id = rl.word_id
		WHERE rl.reviewed_at IS NOT NULL AND `+reviewDayExpr()+` = $1 AND w.user_id = $2
	`, todayUTC, userID).Scan(&totalToday); err != nil {
		return stats, err
	}
	var successToday int
	if err := r.pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM review_log rl
		JOIN words w ON w.id = rl.word_id
		WHERE rl.reviewed_at IS NOT NULL AND `+reviewDayExpr()+` = $1 AND w.user_id = $2 AND rl.quality >= 3
	`, todayUTC, userID).Scan(&successToday); err != nil {
		return stats, err
	}
	if totalToday > 0 {
		stats.SuccessRate = float64(successToday) / float64(totalToday)
	}

	if err := r.pool.QueryRow(ctx, `
		WITH word_levels AS (
			SELECT c.word_id, ROUND(AVG(CAST(r.repetition AS NUMERIC))) AS lvl
			FROM cards c
			JOIN review_state r ON r.card_id = c.id
			JOIN words w ON w.id = c.word_id
			WHERE w.user_id = $1
			GROUP BY c.word_id
		)
		SELECT
			COALESCE(SUM(CASE WHEN lvl <= 1 THEN 1 ELSE 0 END), 0),
			COALESCE(SUM(CASE WHEN lvl = 2 THEN 1 ELSE 0 END), 0),
			COALESCE(SUM(CASE WHEN lvl = 3 THEN 1 ELSE 0 END), 0),
			COALESCE(SUM(CASE WHEN lvl = 4 THEN 1 ELSE 0 END), 0),
			COALESCE(SUM(CASE WHEN lvl >= 5 THEN 1 ELSE 0 END), 0)
		FROM word_levels
	`, userID).Scan(&stats.Level1, &stats.Level2, &stats.Level3, &stats.Level4, &stats.Level5); err != nil {
		return stats, err
	}

	if err := r.pool.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM review_state r JOIN cards c ON c.id = r.card_id JOIN words w ON w.id = c.word_id
		WHERE r.next_review <= $1 AND c.type = $2 AND w.user_id = $3
	`, now.UTC(), string(model.CardTypeENRU), userID).Scan(&stats.Round1Due); err != nil {
		return stats, err
	}
	if err := r.pool.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM review_state r JOIN cards c ON c.id = r.card_id JOIN words w ON w.id = c.word_id
		WHERE r.next_review <= $1 AND c.type = $2 AND w.user_id = $3
	`, now.UTC(), string(model.CardTypeRUEN), userID).Scan(&stats.Round2Due); err != nil {
		return stats, err
	}
	if err := r.pool.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM review_state r JOIN cards c ON c.id = r.card_id JOIN words w ON w.id = c.word_id
		WHERE r.next_review <= $1 AND c.type = $2 AND w.user_id = $3
	`, now.UTC(), string(model.CardTypeListening), userID).Scan(&stats.Round3Due); err != nil {
		return stats, err
	}
	round4Due, err := r.CountDueCloze(ctx, userID, now)
	if err != nil {
		return stats, err
	}
	stats.Round4Due = round4Due

	stats.Learning = stats.TotalWords - stats.Mastered
	if stats.Learning < 0 {
		stats.Learning = 0
	}
	return stats, nil
}

func (r *Repository) ActivityDays(ctx context.Context, userID int64, days int) ([]model.ActivityDay, error) {
	if days <= 0 {
		days = 90
	}
	startDay := time.Now().UTC().AddDate(0, 0, -(days - 1)).Format("2006-01-02")
	rows, err := r.pool.Query(ctx, `
		SELECT `+reviewDayExpr()+` AS day, COUNT(*) AS total
		FROM review_log rl
		JOIN words w ON w.id = rl.word_id
		WHERE rl.reviewed_at IS NOT NULL AND `+reviewDayExpr()+` >= $1 AND w.user_id = $2
		GROUP BY `+reviewDayExpr()+`
		ORDER BY day ASC
	`, startDay, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	result := make([]model.ActivityDay, 0)
	for rows.Next() {
		var row model.ActivityDay
		if err := rows.Scan(&row.Date, &row.Count); err != nil {
			return nil, err
		}
		if row.Date == "" {
			continue
		}
		result = append(result, row)
	}
	return result, rows.Err()
}

func reviewDayExpr() string {
	return "to_char(reviewed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD')"
}

func (r *Repository) EnqueueEvent(ctx context.Context, wordID int64, cardType model.CardType, correct bool, responseTimeMS *int, now time.Time) error {
	_, err := r.pool.Exec(ctx, `
		INSERT INTO event_outbox (word_id, card_type, correct, response_time_ms, created_at)
		VALUES ($1, $2, $3, $4, $5)
	`, wordID, string(cardType), correct, responseTimeMS, now)
	return err
}

func (r *Repository) FetchUnpublishedEvents(ctx context.Context, limit int, maxAttempts int) ([]model.OutboxEvent, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT o.id, w.word, o.card_type, o.correct, o.response_time_ms
		FROM event_outbox o
		JOIN words w ON w.id = o.word_id
		WHERE o.published_at IS NULL AND o.publish_attempts < $1
		ORDER BY o.created_at ASC
		LIMIT $2
	`, maxAttempts, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	events := make([]model.OutboxEvent, 0)
	for rows.Next() {
		var e model.OutboxEvent
		var cardType string
		if err := rows.Scan(&e.ID, &e.Word, &cardType, &e.Correct, &e.ResponseTimeMS); err != nil {
			return nil, err
		}
		e.CardType = model.CardType(cardType)
		events = append(events, e)
	}
	return events, rows.Err()
}

func (r *Repository) MarkEventPublished(ctx context.Context, id int64) error {
	_, err := r.pool.Exec(ctx, `UPDATE event_outbox SET published_at = now() WHERE id = $1`, id)
	return err
}

func (r *Repository) MarkEventFailed(ctx context.Context, id int64) error {
	_, err := r.pool.Exec(ctx, `UPDATE event_outbox SET publish_attempts = publish_attempts + 1 WHERE id = $1`, id)
	return err
}

func (r *Repository) CreateUser(ctx context.Context, email, passwordHash string, now time.Time) (model.User, error) {
	var u model.User
	err := r.pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, created_at)
		VALUES ($1, $2, $3)
		RETURNING id, email, password_hash, created_at
	`, email, passwordHash, now.UTC()).Scan(&u.ID, &u.Email, &u.PasswordHash, &u.CreatedAt)
	return u, err
}

func (r *Repository) GetUserByEmail(ctx context.Context, email string) (*model.User, error) {
	var u model.User
	err := r.pool.QueryRow(ctx, `
		SELECT id, email, password_hash, created_at FROM users WHERE email = $1
	`, email).Scan(&u.ID, &u.Email, &u.PasswordHash, &u.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (r *Repository) GetUserByID(ctx context.Context, id int64) (*model.User, error) {
	var u model.User
	err := r.pool.QueryRow(ctx, `
		SELECT id, email, password_hash, name, cefr_level, created_at FROM users WHERE id = $1
	`, id).Scan(&u.ID, &u.Email, &u.PasswordHash, &u.Name, &u.CEFRLevel, &u.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	return &u, nil
}

func (r *Repository) SetUserLevel(ctx context.Context, userID int64, level string) error {
	tag, err := r.pool.Exec(ctx, `UPDATE users SET cefr_level = $1 WHERE id = $2`, level, userID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repository) UpdateUserProfile(ctx context.Context, userID int64, name, email string) error {
	tag, err := r.pool.Exec(ctx, `UPDATE users SET name = $1, email = $2 WHERE id = $3`, name, email, userID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func ParseRating(rating string) (int, error) {
	switch rating {
	case "again":
		return 1, nil
	case "hard":
		return 3, nil
	case "good":
		return 4, nil
	case "easy":
		return 5, nil
	default:
		return 0, fmt.Errorf("invalid rating: %s", rating)
	}
}
