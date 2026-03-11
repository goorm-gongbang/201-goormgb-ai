package com.trafficmaster.security;

import java.nio.charset.StandardCharsets;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Instant;
import java.time.Duration;
import java.util.Base64;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.dto.ChallengeResponse;
import com.trafficmaster.dto.VerifyRequest;
import com.trafficmaster.dto.VerifyResponse;

import lombok.RequiredArgsConstructor;

/**
 * Stage 3 SSOT Security Challenge service.
 * MVP: Catch-ball VQA 기본, legacy arithmetic fallback 허용.
 * 
 * State Machine:
 *   ACTIVE → PASSED  (verified answer)
 *   ACTIVE → FAILED  (wrong answer, attempt < max)
 *   ACTIVE → BLOCKED (wrong answer, attempt >= max)
 */
@Service
@RequiredArgsConstructor
public class SecurityService {

    private static final Logger log = LoggerFactory.getLogger(SecurityService.class);
    private static final String VQA_PASS_TOKEN = "__VQA_PASS__";
    private final DecisionAuditLogger auditLogger;

    private static final int DEFAULT_ATTEMPT_LIMIT = 2;
    private static final long DEFAULT_CHALLENGE_TTL_MS = 120_000L;
    private static final long DEFAULT_MIN_SOLVE_MS = 2_200L;
    private static final long DEFAULT_ISSUED_AT_SKEW_MS = 30_000L;
    private static final long DEFAULT_TIMING_EDGE_GUARD_MS = 18L;
    private static final boolean DEFAULT_BLOCK_WEBDRIVER = true;
    private static final boolean DEFAULT_BLOCK_HEADLESS_UA = true;
    private static final boolean DEFAULT_BLOCK_WEBDRIVER_OWN_DESCRIPTOR = true;
    private static final boolean DEFAULT_BLOCK_PLUGINS_CLASS_MISMATCH = true;
    private static final String DEFAULT_HMAC_SECRET = "tm-dev-local-secret";
    private static final String DEFAULT_DEFENSE_API_BASE = "http://localhost:8000";
    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(500))
            .build();

    private final ConcurrentHashMap<String, ChallengeState> challenges = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Boolean> sessionVerification = new ConcurrentHashMap<>();
    private final ObjectMapper objectMapper;

    // ─── Issue Challenge ───

    public ChallengeResponse issueChallenge(String sessionId, Integer insertedAtStage) {
        String challengeId = UUID.randomUUID().toString();
        String nonce = UUID.randomUUID().toString();
        int stage = insertedAtStage != null ? insertedAtStage : 2;
        int attemptLimit = getAttemptLimit();
        long issuedAt = Instant.now().toEpochMilli();
        long expiresAt = issuedAt + getChallengeTtlMs();

        ChallengeState state = new ChallengeState(
                challengeId,
                sessionId,
                nonce,
                issuedAt,
                expiresAt,
                attemptLimit
        );
        challenges.put(challengeId, state);
        String challengeToken = signChallengeToken(state);

        // Log SECURITY_CHALLENGE_SHOWN
        auditLogger.logStage1Event(
                sessionId,
                "SECURITY_CHALLENGE_SHOWN",
                Map.of(
                        "challengeId", challengeId,
                        "type", "CATCH_BALL",
                        "insertedAtStage", stage
                ),
                "OK", null
        );

        log.info("Security challenge issued: {} for session {} at stage {}",
                challengeId, sessionId, stage);

        return ChallengeResponse.builder()
                .challengeId(challengeId)
                .type("CATCH_BALL")
                .prompt("Catch the ball with correct timing")
                .imageUrl(null)
                .challengeToken(challengeToken)
                .issuedAt(issuedAt)
                .expiresAt(expiresAt)
                .attemptLimit(attemptLimit)
                .build();
    }

    // ─── Verify Answer ───

    public VerifyResponse verify(VerifyRequest request) {
        String challengeId = request.getChallengeId();
        String sessionId = request.getSessionId();
        String answer = request.getAnswer().trim().toUpperCase();
        ChallengeState state = challenges.get(challengeId);

        if (state == null) {
            return failTerminal(sessionId, challengeId, "CHALLENGE_NOT_FOUND");
        }
        if (!Objects.equals(state.sessionId, sessionId)) {
            return failTerminal(sessionId, challengeId, "SESSION_BINDING_MISMATCH");
        }
        if (state.isExpired()) {
            return failTerminal(sessionId, challengeId, "CHALLENGE_EXPIRED");
        }
        if (state.consumed) {
            return VerifyResponse.builder()
                    .result(state.finalResult)
                    .remainingAttempts(state.remainingAttempts())
                    .reasonCode(state.finalReasonCode)
                    .blocked(state.blocked)
                    .build();
        }
        if (!validateChallengeToken(request.getChallengeToken(), state)) {
            return failTerminal(sessionId, challengeId, "TOKEN_INVALID");
        }

        TelemetryVerdict telemetryVerdict = validateTelemetry(request.getTelemetry(), state);
        boolean passRequested = VQA_PASS_TOKEN.equals(answer);

        if (passRequested && telemetryVerdict.pass) {
            state.consumed = true;
            state.finalResult = "PASS";
            state.finalReasonCode = "OK";
            state.blocked = false;

            sessionVerification.put(sessionId, true);
            log.info("[SecurityService] Marked session {} as VERIFIED", sessionId);
            syncDefenseVqaState(sessionId, true);

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
                            "durationMs", (Instant.now().toEpochMilli() - state.issuedAt)
                    ),
                    "OK", null
            );

            return VerifyResponse.builder()
                    .result("PASS")
                    .remainingAttempts(state.remainingAttempts())
                    .reasonCode("OK")
                    .blocked(false)
                    .build();
        }

        state.attemptsUsed += 1;
        int remaining = state.remainingAttempts();
        String reasonCode = telemetryVerdict.pass ? "WRONG_ANSWER" : telemetryVerdict.reasonCode;

        boolean exhausted = remaining <= 0;
        if (exhausted) {
            state.consumed = true;
            state.finalResult = "FAIL";
            state.finalReasonCode = "RETRY_EXHAUSTED";
            state.blocked = true;
        }

        auditLogger.logStage1Event(
                sessionId,
                "SECURITY_CHALLENGE_FAILED",
                Map.of(
                        "challengeId", challengeId,
                        "reasonCode", reasonCode,
                        "attempt", state.attemptsUsed,
                        "remainingAttempts", remaining
                ),
                "FAIL", reasonCode
        );

        return VerifyResponse.builder()
                .result("FAIL")
                .remainingAttempts(remaining)
                .reasonCode(exhausted ? "RETRY_EXHAUSTED" : reasonCode)
                .blocked(exhausted)
                .build();
    }

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
        syncDefenseVqaState(sessionId, false);
    }

    private VerifyResponse failTerminal(String sessionId, String challengeId, String reasonCode) {
        auditLogger.logStage1Event(
                sessionId,
                "SECURITY_CHALLENGE_FAILED",
                Map.of("challengeId", challengeId, "reasonCode", reasonCode),
                "FAIL", reasonCode
        );
        return VerifyResponse.builder()
                .result("FAIL")
                .remainingAttempts(0)
                .reasonCode(reasonCode)
                .blocked(true)
                .build();
    }

    private String signChallengeToken(ChallengeState state) {
        String payload = String.join("|",
                "v1",
                state.challengeId,
                state.sessionId,
                state.nonce,
                String.valueOf(state.issuedAt),
                String.valueOf(state.expiresAt)
        );
        String payloadB64 = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(payload.getBytes(StandardCharsets.UTF_8));
        String sigB64 = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(hmacSha256(payloadB64.getBytes(StandardCharsets.UTF_8)));
        return payloadB64 + "." + sigB64;
    }

    private boolean validateChallengeToken(String token, ChallengeState state) {
        if (token == null || !token.contains(".")) return false;
        String[] parts = token.split("\\.", 2);
        if (parts.length != 2) return false;

        byte[] expectedSig = hmacSha256(parts[0].getBytes(StandardCharsets.UTF_8));
        byte[] givenSig;
        try {
            givenSig = Base64.getUrlDecoder().decode(parts[1]);
        } catch (IllegalArgumentException e) {
            return false;
        }
        if (!java.security.MessageDigest.isEqual(expectedSig, givenSig)) return false;

        String payload;
        try {
            payload = new String(Base64.getUrlDecoder().decode(parts[0]), StandardCharsets.UTF_8);
        } catch (IllegalArgumentException e) {
            return false;
        }
        String[] values = payload.split("\\|");
        if (values.length != 6) return false;

        return "v1".equals(values[0])
                && state.challengeId.equals(values[1])
                && state.sessionId.equals(values[2])
                && state.nonce.equals(values[3])
                && String.valueOf(state.issuedAt).equals(values[4])
                && String.valueOf(state.expiresAt).equals(values[5]);
    }

    private byte[] hmacSha256(byte[] data) {
        try {
            String secret = System.getenv().getOrDefault("TM_CHALLENGE_HMAC_SECRET", DEFAULT_HMAC_SECRET);
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return mac.doFinal(data);
        } catch (Exception e) {
            throw new IllegalStateException("Failed to sign challenge token", e);
        }
    }

    private int getAttemptLimit() {
        try {
            return Integer.parseInt(System.getenv().getOrDefault("TM_CHALLENGE_ATTEMPT_LIMIT",
                    String.valueOf(DEFAULT_ATTEMPT_LIMIT)));
        } catch (NumberFormatException e) {
            return DEFAULT_ATTEMPT_LIMIT;
        }
    }

    private long getChallengeTtlMs() {
        try {
            return Long.parseLong(System.getenv().getOrDefault("TM_CHALLENGE_TTL_MS",
                    String.valueOf(DEFAULT_CHALLENGE_TTL_MS)));
        } catch (NumberFormatException e) {
            return DEFAULT_CHALLENGE_TTL_MS;
        }
    }

    private TelemetryVerdict validateTelemetry(JsonNode telemetry, ChallengeState state) {
        if (telemetry == null || telemetry.isNull()) {
            return TelemetryVerdict.fail("TELEMETRY_REQUIRED");
        }

        String telemetryChallengeId = telemetry.path("challenge_id").asText("");
        if (!state.challengeId.equals(telemetryChallengeId)) {
            return TelemetryVerdict.fail("CHALLENGE_ID_MISMATCH");
        }

        String telemetrySessionId = telemetry.path("session_id").asText("");
        if (!state.sessionId.equals(telemetrySessionId)) {
            return TelemetryVerdict.fail("SESSION_ID_MISMATCH");
        }

        long telemetryIssuedAt = telemetry.path("issued_at").asLong(0L);
        if (telemetryIssuedAt <= 0L) {
            return TelemetryVerdict.fail("ISSUED_AT_MISSING");
        }
        if (Math.abs(telemetryIssuedAt - state.issuedAt) > getIssuedAtSkewMs()) {
            return TelemetryVerdict.fail("ISSUED_AT_SKEW");
        }

        long startAt = telemetry.path("start_at").asLong(0L);
        if (startAt <= 0L) {
            return TelemetryVerdict.fail("START_AT_MISSING");
        }
        if (startAt < state.issuedAt) {
            return TelemetryVerdict.fail("START_BEFORE_ISSUE");
        }

        int telemetryAttempt = telemetry.path("attempts_used").asInt(-1);
        if (telemetryAttempt <= 0 || telemetryAttempt > state.attemptLimit) {
            return TelemetryVerdict.fail("ATTEMPT_RANGE_INVALID");
        }

        int telemetryRetryLimit = telemetry.path("retry_limit").asInt(-1);
        if (telemetryRetryLimit + 1 != state.attemptLimit) {
            return TelemetryVerdict.fail("RETRY_LIMIT_MISMATCH");
        }

        JsonNode client = telemetry.path("client");
        if (client != null && client.isObject()) {
            boolean webdriver = client.path("webdriver").asBoolean(false);
            String userAgent = client.path("user_agent").asText("");
            int pluginsCount = client.path("plugins_count").asInt(-1);
            String pluginsClass = client.path("plugins_class").asText("");
            boolean webdriverOwnDescriptor = client.path("webdriver_own_descriptor").asBoolean(false);
            if (getBlockWebdriver() && webdriver) {
                return TelemetryVerdict.fail("AUTOMATION_WEBDRIVER");
            }
            if (getBlockHeadlessUa() && userAgent.toLowerCase().contains("headless")) {
                return TelemetryVerdict.fail("AUTOMATION_HEADLESS_UA");
            }
            if (getBlockWebdriverOwnDescriptor() && !webdriver && webdriverOwnDescriptor) {
                return TelemetryVerdict.fail("CLIENT_SPOOF_WEBDRIVER_DESCRIPTOR");
            }
            if (
                getBlockPluginsClassMismatch()
                    && pluginsCount > 0
                    && !pluginsClass.isBlank()
                    && !pluginsClass.contains("PluginArray")
            ) {
                return TelemetryVerdict.fail("CLIENT_SPOOF_PLUGINS_CLASS");
            }
        }

        JsonNode queue = telemetry.path("queue");
        long queueExitAt = queue.path("queue_exit_at").asLong(0L);
        long releaseAt = queue.path("release_at").asLong(0L);
        int queueRank = queue.path("queue_rank").asInt(0);
        if (queueRank <= 0 || queueExitAt <= 0L || releaseAt < queueExitAt) {
            return TelemetryVerdict.fail("QUEUE_META_INVALID");
        }

        boolean positionOk = telemetry.path("position_ok").asBoolean(false);
        boolean timingOk = telemetry.path("timing_ok").asBoolean(false);
        if (!positionOk) return TelemetryVerdict.fail("POSITION_INVALID");
        if (!timingOk) return TelemetryVerdict.fail("TIMING_INVALID");

        double distance = telemetry.path("distance_to_target").asDouble(Double.MAX_VALUE);
        double catchRadius = telemetry.path("position").path("catch_radius").asDouble(38.0);
        if (distance > catchRadius) return TelemetryVerdict.fail("POSITION_MISS");

        JsonNode timing = telemetry.path("timing");
        long enterTs = timing.path("indicator_enter_ts").asLong(0L);
        long exitTs = timing.path("indicator_exit_ts").asLong(0L);
        long clickTs = timing.path("click_ts").asLong(0L);
        if (!(enterTs > 0 && exitTs > enterTs && clickTs >= enterTs && clickTs <= exitTs)) {
            return TelemetryVerdict.fail("TIMING_WINDOW_MISS");
        }
        long timingEdgeGuardMs = getTimingEdgeGuardMs();
        long fromEnterMs = clickTs - enterTs;
        long toExitMs = exitTs - clickTs;
        if (fromEnterMs < timingEdgeGuardMs || toExitMs < timingEdgeGuardMs) {
            return TelemetryVerdict.fail("TIMING_EDGE_HIT");
        }
        if (clickTs - state.issuedAt < getMinSolveMs()) {
            return TelemetryVerdict.fail("SOLVE_TOO_FAST");
        }
        if (clickTs > state.expiresAt) {
            return TelemetryVerdict.fail("CHALLENGE_EXPIRED");
        }
        if (enterTs < startAt) {
            return TelemetryVerdict.fail("TIMING_BEFORE_START");
        }

        JsonNode drag = telemetry.path("drag");
        long dragStartTs = drag.path("drag_start_ts").asLong(0L);
        long dragEndTs = drag.path("drag_end_ts").asLong(0L);
        if (!(dragStartTs > 0 && dragEndTs >= dragStartTs && dragStartTs >= startAt && dragEndTs <= clickTs)) {
            return TelemetryVerdict.fail("DRAG_TIME_INVALID");
        }

        JsonNode holdBeforeClick = drag.path("hold_before_click_ms");
        if (holdBeforeClick.isMissingNode() || holdBeforeClick.isNull()) {
            return TelemetryVerdict.fail("HOLD_BEFORE_CLICK_MISSING");
        }
        if (holdBeforeClick.asLong(-1L) < 0L) {
            return TelemetryVerdict.fail("HOLD_BEFORE_CLICK_INVALID");
        }

        JsonNode path = drag.path("drag_path");
        if (!path.isArray() || path.size() < 5) return TelemetryVerdict.fail("DRAG_PATH_TOO_SHORT");

        double totalDistance = drag.path("total_distance").asDouble(0.0);
        double linearDistance = drag.path("linear_distance").asDouble(0.0);
        double curvature = drag.path("curvature").asDouble(0.0);
        if (totalDistance < 15.0 || linearDistance < 5.0 || curvature < 1.005 || curvature > 18.0) {
            return TelemetryVerdict.fail("DRAG_PATTERN_INVALID");
        }

        long prevT = -1;
        double prevX = 0.0;
        double prevY = 0.0;
        boolean first = true;
        for (JsonNode p : path) {
            long t = p.path("t").asLong(-1L);
            double x = p.path("x").asDouble(Double.NaN);
            double y = p.path("y").asDouble(Double.NaN);
            if (t < 0 || Double.isNaN(x) || Double.isNaN(y)) {
                return TelemetryVerdict.fail("DRAG_POINT_INVALID");
            }
            if (!first) {
                long dt = t - prevT;
                if (dt <= 0) return TelemetryVerdict.fail("TIME_REVERSAL_DETECTED");
                double dist = Math.hypot(x - prevX, y - prevY);
                double speed = dist / dt; // px/ms
                if (speed > 10.0) return TelemetryVerdict.fail("IMPOSSIBLE_SPEED_DETECTED");
            }
            prevT = t;
            prevX = x;
            prevY = y;
            first = false;
        }
        return TelemetryVerdict.pass();
    }

    private long getMinSolveMs() {
        try {
            return Long.parseLong(System.getenv().getOrDefault("TM_VQA_MIN_SOLVE_MS",
                    String.valueOf(DEFAULT_MIN_SOLVE_MS)));
        } catch (NumberFormatException e) {
            return DEFAULT_MIN_SOLVE_MS;
        }
    }

    private long getIssuedAtSkewMs() {
        try {
            return Long.parseLong(System.getenv().getOrDefault("TM_VQA_ISSUED_AT_SKEW_MS",
                    String.valueOf(DEFAULT_ISSUED_AT_SKEW_MS)));
        } catch (NumberFormatException e) {
            return DEFAULT_ISSUED_AT_SKEW_MS;
        }
    }

    private long getTimingEdgeGuardMs() {
        try {
            return Long.parseLong(System.getenv().getOrDefault("TM_VQA_TIMING_EDGE_GUARD_MS",
                    String.valueOf(DEFAULT_TIMING_EDGE_GUARD_MS)));
        } catch (NumberFormatException e) {
            return DEFAULT_TIMING_EDGE_GUARD_MS;
        }
    }

    private boolean getBlockWebdriver() {
        return Boolean.parseBoolean(System.getenv().getOrDefault(
                "TM_VQA_BLOCK_WEBDRIVER",
                String.valueOf(DEFAULT_BLOCK_WEBDRIVER)
        ));
    }

    private boolean getBlockHeadlessUa() {
        return Boolean.parseBoolean(System.getenv().getOrDefault(
                "TM_VQA_BLOCK_HEADLESS_UA",
                String.valueOf(DEFAULT_BLOCK_HEADLESS_UA)
        ));
    }

    private boolean getBlockWebdriverOwnDescriptor() {
        return Boolean.parseBoolean(System.getenv().getOrDefault(
                "TM_VQA_BLOCK_WEBDRIVER_OWN_DESCRIPTOR",
                String.valueOf(DEFAULT_BLOCK_WEBDRIVER_OWN_DESCRIPTOR)
        ));
    }

    private boolean getBlockPluginsClassMismatch() {
        return Boolean.parseBoolean(System.getenv().getOrDefault(
                "TM_VQA_BLOCK_PLUGINS_CLASS_MISMATCH",
                String.valueOf(DEFAULT_BLOCK_PLUGINS_CLASS_MISMATCH)
        ));
    }

    /**
     * Sync backend challenge result into AI runtime state so ext_authz does not
     * re-challenge already-verified sessions.
     */
    private void syncDefenseVqaState(String sessionId, boolean passed) {
        try {
            String base = System.getenv().getOrDefault("TM_DEFENSE_API_BASE", DEFAULT_DEFENSE_API_BASE);
            String payload = objectMapper.writeValueAsString(Map.of(
                    "session_id", sessionId,
                    "vqa_passed", passed,
                    "flow_state", passed ? "S4" : "S3"
            ));

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(base + "/runtime/vqa/mark"))
                    .timeout(Duration.ofMillis(600))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8))
                    .build();

            HttpResponse<String> response = HTTP_CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) {
                log.warn("[SecurityService] defense runtime sync non-2xx: status={}, body={}",
                        response.statusCode(), response.body());
            }
        } catch (Exception e) {
            // Do not fail user flow on defense sync issue; keep verify result primary.
            log.warn("[SecurityService] defense runtime sync failed: {}", e.getMessage());
        }
    }

    private static final class TelemetryVerdict {
        private final boolean pass;
        private final String reasonCode;

        private TelemetryVerdict(boolean pass, String reasonCode) {
            this.pass = pass;
            this.reasonCode = reasonCode;
        }

        static TelemetryVerdict pass() {
            return new TelemetryVerdict(true, "OK");
        }

        static TelemetryVerdict fail(String reasonCode) {
            return new TelemetryVerdict(false, reasonCode);
        }
    }

    private static final class ChallengeState {
        private final String challengeId;
        private final String sessionId;
        private final String nonce;
        private final long issuedAt;
        private final long expiresAt;
        private final int attemptLimit;
        private int attemptsUsed;
        private boolean consumed;
        private String finalResult;
        private String finalReasonCode;
        private boolean blocked;

        private ChallengeState(String challengeId, String sessionId, String nonce, long issuedAt, long expiresAt, int attemptLimit) {
            this.challengeId = challengeId;
            this.sessionId = sessionId;
            this.nonce = nonce;
            this.issuedAt = issuedAt;
            this.expiresAt = expiresAt;
            this.attemptLimit = attemptLimit;
            this.attemptsUsed = 0;
            this.consumed = false;
            this.finalResult = null;
            this.finalReasonCode = null;
            this.blocked = false;
        }

        private int remainingAttempts() {
            return Math.max(0, attemptLimit - attemptsUsed);
        }

        private boolean isExpired() {
            return Instant.now().toEpochMilli() > expiresAt;
        }
    }
}
