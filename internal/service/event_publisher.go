package service

import (
	"context"
	"time"

	"anki/internal/ai"

	"go.uber.org/zap"
)

const (
	publishInterval    = 3 * time.Second
	publishBatchSize   = 20
	publishMaxAttempts = 10
)

// RunEventPublisher periodically drains the event_outbox and relays unpublished
// events to repetitor. It never blocks the review hot path: SubmitReview/
// SubmitAdvancedReview only enqueue locally, this loop does the network I/O.
func RunEventPublisher(ctx context.Context, repo Repository, client *ai.Client, logger *zap.Logger) {
	ticker := time.NewTicker(publishInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if client == nil || !client.Ready() {
				continue
			}
			drainOutbox(ctx, repo, client, logger)
		}
	}
}

func drainOutbox(ctx context.Context, repo Repository, client *ai.Client, logger *zap.Logger) {
	events, err := repo.FetchUnpublishedEvents(ctx, publishBatchSize, publishMaxAttempts)
	if err != nil {
		logger.Warn("fetch unpublished events failed", zap.Error(err))
		return
	}
	for _, event := range events {
		responseTimeMs := 0
		if event.ResponseTimeMS != nil {
			responseTimeMs = *event.ResponseTimeMS
		}
		err := client.PublishEvent(ctx, event.Word, event.Correct, responseTimeMs, 1, string(event.CardType), "")
		if err != nil {
			logger.Warn("publish event failed", zap.Int64("event_id", event.ID), zap.Error(err))
			if markErr := repo.MarkEventFailed(ctx, event.ID); markErr != nil {
				logger.Warn("mark event failed failed", zap.Int64("event_id", event.ID), zap.Error(markErr))
			}
			continue
		}
		if markErr := repo.MarkEventPublished(ctx, event.ID); markErr != nil {
			logger.Warn("mark event published failed", zap.Int64("event_id", event.ID), zap.Error(markErr))
		}
	}
}
