// Package placement implements a fixed, deterministic English placement quiz.
// It intentionally has no dependency on repetitor/LLM — this runs on first
// login, before the student has done anything else, and must not fail just
// because the AI backend happens to be down.
package placement

// Question is what the client sees — no correct-answer index.
type Question struct {
	ID      int      `json:"id"`
	Text    string   `json:"text"`
	Options []string `json:"options"`
}

type question struct {
	text    string
	options []string
	correct int
}

// bank is ordered A1 -> C1. Index+1 is the question ID.
var bank = []question{
	{"She ___ to school every day.", []string{"goes", "go", "going", "gone"}, 0},
	{"I ___ a doctor.", []string{"am", "is", "are", "be"}, 0},
	{"There ___ some milk in the fridge.", []string{"is", "are", "be", "been"}, 0},
	{"He has lived here ___ 2015.", []string{"since", "for", "from", "at"}, 0},
	{"If it rains, we ___ inside.", []string{"will stay", "stay", "stayed", "would stay"}, 0},
	{"By the time we arrived, the movie ___ already started.", []string{"had", "has", "have", "was"}, 0},
	{"She's used to ___ up early.", []string{"waking", "wake", "woken", "wakes"}, 0},
	{"I wish I ___ more time to finish this.", []string{"had", "have", "has", "having"}, 0},
	{"The report ___ by the team next week.", []string{"will be finished", "will finish", "is finished", "finishes"}, 0},
	{"Hardly ___ left when it started raining.", []string{"had we", "we had", "have we", "we have"}, 0},
	{"Choose the word closest in meaning to 'meticulous'.", []string{"careless", "careful", "careful and precise", "quick"}, 2},
	{"___ he apologize, she wouldn't have forgiven him.", []string{"Had", "If", "Unless", "Should"}, 0},
}

// Questions returns the quiz without correct answers, for the client.
func Questions() []Question {
	out := make([]Question, len(bank))
	for i, q := range bank {
		out[i] = Question{ID: i + 1, Text: q.text, Options: q.options}
	}
	return out
}

// Score grades answers (question ID -> chosen option index) against the
// answer key and returns a CEFR band.
func Score(answers map[int]int) string {
	correct := 0
	for i, q := range bank {
		// Two-value lookup — a missing key (unanswered question) must not be
		// confused with an explicit answer of 0 (most questions' correct index).
		chosen, answered := answers[i+1]
		if answered && chosen == q.correct {
			correct++
		}
	}
	switch {
	case correct <= 2:
		return "A1"
	case correct <= 4:
		return "A2"
	case correct <= 6:
		return "B1"
	case correct <= 8:
		return "B2"
	case correct <= 10:
		return "C1"
	default:
		return "C2"
	}
}
