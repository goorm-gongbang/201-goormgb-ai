package com.trafficmaster.queue;

import java.time.Instant;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Stage 2 SSOT domain model: QueueTicket
 * Tracks a user's position in the virtual queue.
 * 
 * State Machine (Addendum + Stage 2):
 *   WAITING → GRANTED  (elapsedTime >= estimatedWaitMs OR position <= 0)
 *   WAITING → BLOCKED  (Defense Policy Triggered)
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class QueueTicket {

    private String queueTicketId;
    private String sessionId;
    private String gameId;

    @Builder.Default
    private Mode mode = Mode.RECOMMEND;

    private int position;
    private int initialPosition;

    @Builder.Default
    private Status status = Status.WAITING;

    @Builder.Default
    private long estimatedWaitMs = 5000;

    private Instant createdAt;

    public enum Mode {
        RECOMMEND, MAP
    }

    public enum Status {
        WAITING, GRANTED, BLOCKED
    }

    /**
     * Calculate progress as ratio of position reduction.
     * Returns 0.0 (just entered) to 1.0 (ready).
     */
    public double getProgress() {
        if (initialPosition <= 0) return 1.0;
        double progress = 1.0 - ((double) Math.max(0, position) / initialPosition);
        return Math.min(1.0, Math.max(0.0, progress));
    }

    /**
     * Check if elapsed time exceeds estimated wait.
     */
    public boolean isTimeExpired() {
        if (createdAt == null) return false;
        long elapsed = Instant.now().toEpochMilli() - createdAt.toEpochMilli();
        return elapsed >= estimatedWaitMs;
    }
}
