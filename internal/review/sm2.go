package review

import (
	"time"

	"anki/internal/model"
)

type Calculator interface {
	Calculate(state model.ReviewState, quality int, now time.Time) model.ReviewState
}

type SM2 struct{}

func NewSM2() *SM2 {
	return &SM2{}
}

func (s *SM2) Calculate(state model.ReviewState, quality int, now time.Time) model.ReviewState {
	if quality < 3 {
		state.Repetition = 0
		state.Interval = 1
		state.WrongCount++
	} else {
		if state.Repetition == 0 {
			state.Interval = 1
		} else if state.Repetition == 1 {
			state.Interval = 6
		} else {
			state.Interval = int(float64(state.Interval) * state.EaseFactor)
			if state.Interval < 1 {
				state.Interval = 1
			}
		}
		state.Repetition++
		state.CorrectCount++
	}

	state.EaseFactor += 0.1 - float64(5-quality)*(0.08+float64(5-quality)*0.02)
	if state.EaseFactor < 1.3 {
		state.EaseFactor = 1.3
	}

	state.NextReview = now.AddDate(0, 0, state.Interval)
	return state
}
