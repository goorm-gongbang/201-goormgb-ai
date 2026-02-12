package com.trafficmaster.security;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.dto.ChallengeResponse;
import com.trafficmaster.dto.VerifyRequest;
import com.trafficmaster.dto.VerifyResponse;

import lombok.RequiredArgsConstructor;

/**
 * Stage 3 SSOT Security Challenge service.
 * MVP: fixed quiz "3 + 4 = ?", correct answer = "7".
 * 
 * State Machine:
 *   ACTIVE → PASSED  (correct answer)
 *   ACTIVE → FAILED  (wrong answer, attempt < max)
 *   ACTIVE → BLOCKED (wrong answer, attempt >= max)
 */
@Service
@RequiredArgsConstructor
public class SecurityService {

    private static final Logger log = LoggerFactory.getLogger(SecurityService.class);
    private static final int MAX_ATTEMPTS = 3;
    private static final String CORRECT_ANSWER = "7";

    private final DecisionAuditLogger auditLogger;

    // challengeId → sessionId mapping
    private final ConcurrentHashMap<String, String> challengeSessions = new ConcurrentHashMap<>();
    // challengeId → creation timestamp
    private final ConcurrentHashMap<String, Instant> challengeTimestamps = new ConcurrentHashMap<>();
    // sessionId → attempt count
    private final ConcurrentHashMap<String, AtomicInteger> attemptCounts = new ConcurrentHashMap<>();

    // ─── Issue Challenge ───

    public ChallengeResponse issueChallenge(String sessionId, Integer insertedAtStage) {
        String challengeId = UUID.randomUUID().toString();
        int stage = insertedAtStage != null ? insertedAtStage : 2;

        challengeSessions.put(challengeId, sessionId);
        challengeTimestamps.put(challengeId, Instant.now());

        // Initialize attempt count for session if not present
        attemptCounts.putIfAbsent(sessionId, new AtomicInteger(0));

        // Log SECURITY_CHALLENGE_SHOWN
        auditLogger.logStage1Event(
                sessionId,
                "SECURITY_CHALLENGE_SHOWN",
                Map.of(
                        "challengeId", challengeId,
                        "type", "QUIZ",
                        "insertedAtStage", stage
                ),
                "OK", null
        );

        log.info("Security challenge issued: {} for session {} at stage {}",
                challengeId, sessionId, stage);

        return ChallengeResponse.builder()
                .challengeId(challengeId)
                .type("QUIZ")
                .prompt("3 + 4 = ?")
                .imageUrl(null)
                .build();
    }

    // ─── Verify Answer ───

    public VerifyResponse verify(VerifyRequest request) {
        String challengeId = request.getChallengeId();
        String sessionId = request.getSessionId();
        String answer = request.getAnswer().trim();

        // Get or init attempt counter
        AtomicInteger counter = attemptCounts.computeIfAbsent(sessionId, k -> new AtomicInteger(0));

        if (CORRECT_ANSWER.equals(answer)) {
            // ── PASS ──
            long durationMs = calculateDuration(challengeId);

            auditLogger.logStage1Event(
                    sessionId,
                    "SECURITY_CHALLENGE_PASSED",
                    Map.of("challengeId", challengeId),
                    "OK", null
            );

            auditLogger.logStage1Event(
                    sessionId,
                    "SECURITY_CHALLENGE_SUBMITTED",
                    Map.of(
                            "challengeId", challengeId,
                            "result", "PASS",
                            "durationMs", durationMs
                    ),
                    "OK", null
            );

            log.info("Security challenge PASSED: {} for session {}", challengeId, sessionId);

            // Cleanup
            challengeSessions.remove(challengeId);
            challengeTimestamps.remove(challengeId);
            counter.set(0);
            
            // Mark session as verified (for MapController check)
            sessionVerification.put(sessionId, true);
            log.info("[SecurityService] Marked session {} as VERIFIED", sessionId);

            return VerifyResponse.builder()
                    .result("PASS")
                    .remainingAttempts(MAX_ATTEMPTS)
                    .build();
        } else {
            // ── FAIL ──
            int attempts = counter.incrementAndGet();
            int remaining = Math.max(0, MAX_ATTEMPTS - attempts);

            auditLogger.logStage1Event(
                    sessionId,
                    "SECURITY_CHALLENGE_FAILED",
                    Map.of(
                            "challengeId", challengeId,
                            "reasonCode", "WRONG_ANSWER",
                            "attempt", attempts,
                            "remainingAttempts", remaining
                    ),
                    "FAIL", "Wrong answer submitted"
            );

            log.warn("Security challenge FAILED: {} for session {} (attempt {}/{})",
                    challengeId, sessionId, attempts, MAX_ATTEMPTS);

            return VerifyResponse.builder()
                    .result("FAIL")
                    .remainingAttempts(remaining)
                    .build();
        }
    }

    // sessionId → verified status (simplified for MVP/demo)
    private final ConcurrentHashMap<String, Boolean> sessionVerification = new ConcurrentHashMap<>();

    public boolean isVerified(String sessionId) {
        return sessionVerification.getOrDefault(sessionId, false);
    }

    /**
     * Reset verification so the next seat-entry will require a fresh challenge.
     * Called after a booking cycle completes (e.g. payment success or hold release).
     */
    public void resetVerification(String sessionId) {
        sessionVerification.remove(sessionId);
        log.info("[SecurityService] Reset verification for session {}", sessionId);
    }
    
    // ─── Helpers ───

    private long calculateDuration(String challengeId) {
        Instant created = challengeTimestamps.get(challengeId);
        if (created == null) return 0;
        return Instant.now().toEpochMilli() - created.toEpochMilli();
    }
}
