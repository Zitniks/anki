package model

import "time"

type CardType string

const (
	CardTypeENRU          CardType = "en_ru"
	CardTypeRUEN          CardType = "ru_en"
	CardTypeListening     CardType = "listening"
	CardTypeCloze         CardType = "cloze"
	CardTypeSpeaking      CardType = "speaking"
	CardTypeTimed         CardType = "timed"
	CardTypeSpeakingCloze CardType = "speaking_cloze"
)

type CardStatus string

const (
	CardStatusNew        CardStatus = "new"
	CardStatusLearning   CardStatus = "learning"
	CardStatusReview     CardStatus = "review"
	CardStatusRelearning CardStatus = "relearning"
)

type Word struct {
	ID            int64     `json:"id"`
	Word          string    `json:"word"`
	Translation   string    `json:"translation"`
	Example       string    `json:"example,omitempty"`
	Transcription string    `json:"transcription,omitempty"`
	CreatedAt     time.Time `json:"created_at"`
}

type ReviewState struct {
	CardID       int64
	Repetition   int
	Interval     int
	EaseFactor   float64
	NextReview   time.Time
	CorrectCount int
	WrongCount   int
	Status       CardStatus
	LearningStep int
}

type ReviewCard struct {
	WordID        int64      `json:"word_id"`
	Word          string     `json:"word"`
	Translation   string     `json:"translation"`
	Example       string     `json:"example,omitempty"`
	Transcription string     `json:"transcription,omitempty"`
	CreatedAt     time.Time  `json:"created_at"`
	Status        CardStatus `json:"status"`
	Skip          bool       `json:"skip,omitempty"`
}

type SessionWord struct {
	WordID     int64     `json:"word_id"`
	Word       string    `json:"word"`
	MinDue     time.Time `json:"min_due"`
	HasExample bool      `json:"has_example"`
}

type CardProgress struct {
	CardID int64
	Type   CardType
	State  ReviewState
}

type Stats struct {
	TotalWords   int     `json:"total_words"`
	DueToday     int     `json:"due_today"`
	Learning     int     `json:"learning"`
	Mastered     int     `json:"mastered"`
	ReviewsToday int     `json:"reviews_today"`
	SuccessRate  float64 `json:"success_rate"`
	Level1       int     `json:"level1"`
	Level2       int     `json:"level2"`
	Level3       int     `json:"level3"`
	Level4       int     `json:"level4"`
	Level5       int     `json:"level5"`
	Round1Due    int     `json:"round1_due"`
	Round2Due    int     `json:"round2_due"`
	Round3Due    int     `json:"round3_due"`
	Round4Due    int     `json:"round4_due"`
}

type RoundStats struct {
	Round1Due    int `json:"round1_due"`
	Round2Due    int `json:"round2_due"`
	Round3Due    int `json:"round3_due"`
	Round4Due    int `json:"round4_due"`
	Round1Target int `json:"round1_target"`
	Round2Target int `json:"round2_target"`
	Round3Target int `json:"round3_target"`
	Round4Target int `json:"round4_target"`
}

type AdvancedRoundStats struct {
	SpeakingDue         int `json:"speaking_due"`
	TimedDue            int `json:"timed_due"`
	SpeakingClozeDue    int `json:"speaking_cloze_due"`
	SpeakingTarget      int `json:"speaking_target"`
	TimedTarget         int `json:"timed_target"`
	SpeakingClozeTarget int `json:"speaking_cloze_target"`
	MinLevel            int `json:"min_level"`
}

type ActivityDay struct {
	Date  string `json:"date"`
	Count int    `json:"count"`
}

type OutboxEvent struct {
	ID             int64
	Word           string
	CardType       CardType
	Correct        bool
	ResponseTimeMS *int
}

type User struct {
	ID           int64     `json:"id"`
	Email        string    `json:"email"`
	PasswordHash string    `json:"-"`
	Name         *string   `json:"name,omitempty"`
	CEFRLevel    *string   `json:"cefr_level,omitempty"`
	CreatedAt    time.Time `json:"created_at"`
}
