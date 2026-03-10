package com.trafficmaster.security;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.dto.ChallengeResponse;
import com.trafficmaster.dto.VerifyRequest;
import com.trafficmaster.dto.VerifyResponse;

import java.nio.file.Files;
import java.nio.file.Path;

@SpringBootTest
class SecurityServiceTest {

    @Autowired
    private SecurityService securityService;

    @Autowired
    private DecisionAuditLogger auditLogger;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void clearAuditLog() throws Exception {
        Path logPath = auditLogger.getLogPath();
        if (Files.exists(logPath)) {
            Files.writeString(logPath, "");
        }
    }

    // ─── Challenge Issuance ───

    @Test
    @DisplayName("Issue challenge - returns valid challengeId and CATCH_BALL type")
    void issueChallenge_shouldReturnValidChallenge() {
        ChallengeResponse response = securityService.issueChallenge("session-sec-1", 2);

        assertNotNull(response.getChallengeId());
        assertFalse(response.getChallengeId().isEmpty());
        assertEquals("CATCH_BALL", response.getType());
        assertEquals("Catch the ball with correct timing", response.getPrompt());
        assertNull(response.getImageUrl());
        assertNotNull(response.getChallengeToken());
        assertNotNull(response.getExpiresAt());
        assertNotNull(response.getAttemptLimit());
    }

    @Test
    @DisplayName("Issue challenge - logs SECURITY_CHALLENGE_SHOWN event")
    void issueChallenge_shouldLogEvent() throws Exception {
        securityService.issueChallenge("session-sec-log", 2);

        String logContent = Files.readString(auditLogger.getLogPath());
        assertTrue(logContent.contains("SECURITY_CHALLENGE_SHOWN"),
                "Expected SECURITY_CHALLENGE_SHOWN in audit log");
    }

    // ─── Verify - Correct Answer ───

    @Test
    @DisplayName("Verify correct answer - returns PASS")
    void verify_correctAnswer_shouldReturnPass() {
        ChallengeResponse challenge = securityService.issueChallenge("session-sec-pass", 2);

        VerifyResponse response = securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .challengeToken(challenge.getChallengeToken())
                        .answer("__VQA_PASS__")
                        .sessionId("session-sec-pass")
                        .telemetry(validTelemetry(challenge.getChallengeId(), "session-sec-pass", 1))
                        .build()
        );

        assertEquals("PASS", response.getResult());
        assertEquals("OK", response.getReasonCode());
    }

    @Test
    @DisplayName("Verify correct answer - logs PASSED and SUBMITTED events")
    void verify_correctAnswer_shouldLogEvents() throws Exception {
        ChallengeResponse challenge = securityService.issueChallenge("session-sec-passlog", 2);

        securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .challengeToken(challenge.getChallengeToken())
                        .answer("__VQA_PASS__")
                        .sessionId("session-sec-passlog")
                        .telemetry(validTelemetry(challenge.getChallengeId(), "session-sec-passlog", 1))
                        .build()
        );

        String logContent = Files.readString(auditLogger.getLogPath());
        assertTrue(logContent.contains("SECURITY_CHALLENGE_PASSED"));
        assertTrue(logContent.contains("SECURITY_CHALLENGE_SUBMITTED"));
    }

    // ─── Verify - Wrong Answer ───

    @Test
    @DisplayName("Verify wrong answer - returns FAIL with decreased remaining attempts")
    void verify_wrongAnswer_shouldReturnFail() {
        ChallengeResponse challenge = securityService.issueChallenge("session-sec-fail", 2);

        VerifyResponse response = securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .challengeToken(challenge.getChallengeToken())
                        .answer("__VQA_FAIL__")
                        .sessionId("session-sec-fail")
                        .telemetry(validTelemetry(challenge.getChallengeId(), "session-sec-fail", 1))
                        .build()
        );

        assertEquals("FAIL", response.getResult());
        assertEquals(1, response.getRemainingAttempts()); // 2 max - 1 attempt = 1 remaining
    }

    @Test
    @DisplayName("Multiple wrong answers - remaining attempts decrease")
    void verify_multipleWrongAnswers_shouldDecrementAttempts() {
        ChallengeResponse challenge = securityService.issueChallenge("session-sec-multi", 2);

        // First wrong answer
        VerifyResponse r1 = securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .challengeToken(challenge.getChallengeToken())
                        .answer("__VQA_FAIL__")
                        .sessionId("session-sec-multi")
                        .telemetry(validTelemetry(challenge.getChallengeId(), "session-sec-multi", 1))
                        .build()
        );
        assertEquals(1, r1.getRemainingAttempts());

        // Second wrong answer
        VerifyResponse r2 = securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .challengeToken(challenge.getChallengeToken())
                        .answer("__VQA_FAIL__")
                        .sessionId("session-sec-multi")
                        .telemetry(validTelemetry(challenge.getChallengeId(), "session-sec-multi", 2))
                        .build()
        );
        assertEquals(0, r2.getRemainingAttempts());
        assertTrue(Boolean.TRUE.equals(r2.getBlocked()));

        // Third wrong answer (keeps 0)
        VerifyResponse r3 = securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .challengeToken(challenge.getChallengeToken())
                        .answer("__VQA_FAIL__")
                        .sessionId("session-sec-multi")
                        .telemetry(validTelemetry(challenge.getChallengeId(), "session-sec-multi", 3))
                        .build()
        );
        assertEquals(0, r3.getRemainingAttempts());
    }

    @Test
    @DisplayName("Verify wrong answer - logs SECURITY_CHALLENGE_FAILED event")
    void verify_wrongAnswer_shouldLogFailEvent() throws Exception {
        ChallengeResponse challenge = securityService.issueChallenge("session-sec-faillog", 2);

        securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .challengeToken(challenge.getChallengeToken())
                        .answer("__VQA_FAIL__")
                        .sessionId("session-sec-faillog")
                        .telemetry(validTelemetry(challenge.getChallengeId(), "session-sec-faillog", 1))
                        .build()
        );

        String logContent = Files.readString(auditLogger.getLogPath());
        assertTrue(logContent.contains("SECURITY_CHALLENGE_FAILED"));
        assertTrue(logContent.contains("WRONG_ANSWER"));
    }

    @Test
    @DisplayName("Verify pass token with timing edge hit - returns TIMING_EDGE_HIT")
    void verify_passTokenAtTimingWindowEdge_shouldFail() {
        ChallengeResponse challenge = securityService.issueChallenge("session-sec-edge", 2);

        JsonNode telemetry = validTelemetry(challenge.getChallengeId(), "session-sec-edge", 1);
        ObjectNode timing = ((ObjectNode) telemetry).withObject("/timing");
        long enterTs = timing.path("indicator_enter_ts").asLong();
        timing.put("click_ts", enterTs + 2L); // too close to edge for guardrail

        VerifyResponse response = securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .challengeToken(challenge.getChallengeToken())
                        .answer("__VQA_PASS__")
                        .sessionId("session-sec-edge")
                        .telemetry(telemetry)
                        .build()
        );

        assertEquals("FAIL", response.getResult());
        assertEquals("TIMING_EDGE_HIT", response.getReasonCode());
    }

    @Test
    @DisplayName("Verify pass token with webdriver signal - returns AUTOMATION_WEBDRIVER")
    void verify_passTokenWithWebdriverSignal_shouldFail() {
        ChallengeResponse challenge = securityService.issueChallenge("session-sec-webdriver", 2);

        JsonNode telemetry = validTelemetry(challenge.getChallengeId(), "session-sec-webdriver", 1);
        ObjectNode client = ((ObjectNode) telemetry).withObject("/client");
        client.put("webdriver", true);

        VerifyResponse response = securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .challengeToken(challenge.getChallengeToken())
                        .answer("__VQA_PASS__")
                        .sessionId("session-sec-webdriver")
                        .telemetry(telemetry)
                        .build()
        );

        assertEquals("FAIL", response.getResult());
        assertEquals("AUTOMATION_WEBDRIVER", response.getReasonCode());
    }

    @Test
    @DisplayName("Verify pass token with spoofed webdriver descriptor - returns CLIENT_SPOOF_WEBDRIVER_DESCRIPTOR")
    void verify_passTokenWithSpoofedWebdriverDescriptor_shouldFail() {
        ChallengeResponse challenge = securityService.issueChallenge("session-sec-webdriver-own-desc", 2);

        JsonNode telemetry = validTelemetry(challenge.getChallengeId(), "session-sec-webdriver-own-desc", 1);
        ObjectNode client = ((ObjectNode) telemetry).withObject("/client");
        client.put("webdriver", false);
        client.put("webdriver_own_descriptor", true);

        VerifyResponse response = securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .challengeToken(challenge.getChallengeToken())
                        .answer("__VQA_PASS__")
                        .sessionId("session-sec-webdriver-own-desc")
                        .telemetry(telemetry)
                        .build()
        );

        assertEquals("FAIL", response.getResult());
        assertEquals("CLIENT_SPOOF_WEBDRIVER_DESCRIPTOR", response.getReasonCode());
    }

    private JsonNode validTelemetry(String challengeId, String sessionId, int attemptsUsed) {
        long now = System.currentTimeMillis();
        long startAt = now + 100L;
        long dragStartTs = startAt + 40L;
        long dragEndTs = dragStartTs + 180L;
        long indicatorEnterTs = startAt + 2_300L;
        long indicatorExitTs = indicatorEnterTs + 220L;
        long clickTs = indicatorEnterTs + 110L;
        long queueExitAt = now - 100L;
        long releaseAt = queueExitAt + 8_000L;
        return objectMapper.valueToTree(java.util.Map.ofEntries(
                java.util.Map.entry("challenge_id", challengeId),
                java.util.Map.entry("session_id", sessionId),
                java.util.Map.entry("issued_at", now),
                java.util.Map.entry("start_at", startAt),
                java.util.Map.entry("attempts_used", attemptsUsed),
                java.util.Map.entry("retry_limit", 1),
                java.util.Map.entry("position_ok", true),
                java.util.Map.entry("timing_ok", true),
                java.util.Map.entry("distance_to_target", 10.0),
                java.util.Map.entry("timing", java.util.Map.of(
                        "indicator_enter_ts", indicatorEnterTs,
                        "indicator_exit_ts", indicatorExitTs,
                        "click_ts", clickTs
                )),
                java.util.Map.entry("position", java.util.Map.of("catch_radius", 38.0)),
                java.util.Map.entry("drag", java.util.Map.of(
                        "drag_start_ts", dragStartTs,
                        "drag_end_ts", dragEndTs,
                        "hold_before_click_ms", 10L,
                        "total_distance", 120.0,
                        "linear_distance", 80.0,
                        "curvature", 1.5,
                        "drag_path", java.util.List.of(
                                java.util.Map.of("x", 10, "y", 10, "t", 10),
                                java.util.Map.of("x", 20, "y", 14, "t", 30),
                                java.util.Map.of("x", 30, "y", 20, "t", 50),
                                java.util.Map.of("x", 40, "y", 28, "t", 70),
                                java.util.Map.of("x", 50, "y", 30, "t", 90)
                        )
                )),
                java.util.Map.entry("queue", java.util.Map.of(
                        "queue_rank", 1200,
                        "queue_exit_at", queueExitAt,
                        "release_at", releaseAt,
                        "released_for_booking", false
                )),
                java.util.Map.entry("client", java.util.Map.of(
                        "webdriver", false,
                        "user_agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
                        "plugins_count", 5,
                        "plugins_class", "[object PluginArray]",
                        "webdriver_own_descriptor", false
                ))
        ));
    }
}
