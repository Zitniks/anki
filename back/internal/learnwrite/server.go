package learnwrite

import (
	"context"
	"errors"
	"strings"

	tutorpb "anki/internal/ai/pb/tutor/v1"
	"anki/internal/model"
	"anki/internal/service"

	"go.uber.org/zap"
)

// Server implements the reverse channel (Epic 2): llm-service is
// the gRPC CLIENT here, calling back into a specific Anki Lite user's own
// vocabulary deck on behalf of the chat agent. The opposite direction from
// TutorService, where ankis (back/) is the client.
type Server struct {
	tutorpb.UnimplementedLearnWriteServiceServer
	service *service.WordService
	logger  *zap.Logger
}

func NewServer(s *service.WordService, logger *zap.Logger) *Server {
	return &Server{service: s, logger: logger}
}

func (s *Server) AddWords(ctx context.Context, req *tutorpb.AddWordsRequest) (*tutorpb.AddWordsResponse, error) {
	results := make([]*tutorpb.AddWordResult, 0, len(req.Words))
	for _, draft := range req.Words {
		_, err := s.service.AddWord(ctx, req.UserId, model.Word{
			Word:          draft.Word,
			Translation:   draft.Translation,
			Example:       draft.Example,
			Transcription: draft.Transcription,
		})
		switch {
		case err == nil:
			results = append(results, &tutorpb.AddWordResult{Word: draft.Word, Added: true})
		case errors.Is(err, service.ErrConflict):
			results = append(results, &tutorpb.AddWordResult{Word: draft.Word, Added: false, Reason: "already exists"})
		case errors.Is(err, service.ErrInvalidInput):
			results = append(results, &tutorpb.AddWordResult{Word: draft.Word, Added: false, Reason: "invalid word or translation"})
		default:
			s.logger.Warn("learnwrite.add_word failed",
				zap.Int64("user_id", req.UserId), zap.String("word", draft.Word), zap.Error(err))
			results = append(results, &tutorpb.AddWordResult{Word: draft.Word, Added: false, Reason: "internal error"})
		}
	}
	return &tutorpb.AddWordsResponse{Results: results}, nil
}

func (s *Server) DeleteWord(ctx context.Context, req *tutorpb.DeleteWordRequest) (*tutorpb.DeleteWordResponse, error) {
	deleted, err := s.service.DeleteWordByText(ctx, req.UserId, req.Word)
	if err != nil {
		s.logger.Warn("learnwrite.delete_word failed",
			zap.Int64("user_id", req.UserId), zap.String("word", req.Word), zap.Error(err))
		return nil, err
	}
	return &tutorpb.DeleteWordResponse{Deleted: deleted}, nil
}

func (s *Server) CheckWordsExist(ctx context.Context, req *tutorpb.CheckWordsExistRequest) (*tutorpb.CheckWordsExistResponse, error) {
	matches, err := s.service.GetWordsByText(ctx, req.UserId, req.Words)
	if err != nil {
		s.logger.Warn("learnwrite.check_words_exist failed", zap.Int64("user_id", req.UserId), zap.Error(err))
		return nil, err
	}
	byLower := make(map[string]model.Word, len(matches))
	for _, w := range matches {
		byLower[strings.ToLower(w.Word)] = w
	}
	results := make([]*tutorpb.WordExistCheck, 0, len(req.Words))
	for _, word := range req.Words {
		if match, ok := byLower[strings.ToLower(word)]; ok {
			results = append(results, &tutorpb.WordExistCheck{Word: word, Exists: true, Translation: match.Translation})
		} else {
			results = append(results, &tutorpb.WordExistCheck{Word: word, Exists: false})
		}
	}
	return &tutorpb.CheckWordsExistResponse{Results: results}, nil
}
