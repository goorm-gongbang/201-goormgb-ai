package com.trafficmaster.security;

import static org.junit.jupiter.api.Assertions.*;

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

    @BeforeEach
    void clearAuditLog() throws Exception {
        Path logPath = auditLogger.getLogPath();
        if (Files.exists(logPath)) {
            Files.writeString(logPath, "");
        }
    }

    // ─── Challenge Issuance ───

    @Test
    @DisplayName("Issue challenge - returns valid challengeId and QUIZ type")
    void issueChallenge_shouldReturnValidChallenge() {
        ChallengeResponse response = securityService.issueChallenge("session-sec-1", 2);

        assertNotNull(response.getChallengeId());
        assertFalse(response.getChallengeId().isEmpty());
        assertEquals("QUIZ", response.getType());
        assertEquals("3 + 4 = ?", response.getPrompt());
        assertNull(response.getImageUrl());
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
                        .answer("7")
                        .sessionId("session-sec-pass")
                        .build()
        );

        assertEquals("PASS", response.getResult());
    }

    @Test
    @DisplayName("Verify correct answer - logs PASSED and SUBMITTED events")
    void verify_correctAnswer_shouldLogEvents() throws Exception {
        ChallengeResponse challenge = securityService.issueChallenge("session-sec-passlog", 2);

        securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .answer("7")
                        .sessionId("session-sec-passlog")
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
                        .answer("0")
                        .sessionId("session-sec-fail")
                        .build()
        );

        assertEquals("FAIL", response.getResult());
        assertEquals(2, response.getRemainingAttempts()); // 3 max - 1 attempt = 2 remaining
    }

    @Test
    @DisplayName("Multiple wrong answers - remaining attempts decrease")
    void verify_multipleWrongAnswers_shouldDecrementAttempts() {
        ChallengeResponse challenge = securityService.issueChallenge("session-sec-multi", 2);

        // First wrong answer
        VerifyResponse r1 = securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .answer("1")
                        .sessionId("session-sec-multi")
                        .build()
        );
        assertEquals(2, r1.getRemainingAttempts());

        // Second wrong answer
        VerifyResponse r2 = securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .answer("2")
                        .sessionId("session-sec-multi")
                        .build()
        );
        assertEquals(1, r2.getRemainingAttempts());

        // Third wrong answer
        VerifyResponse r3 = securityService.verify(
                VerifyRequest.builder()
                        .challengeId(challenge.getChallengeId())
                        .answer("3")
                        .sessionId("session-sec-multi")
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
                        .answer("0")
                        .sessionId("session-sec-faillog")
                        .build()
        );

        String logContent = Files.readString(auditLogger.getLogPath());
        assertTrue(logContent.contains("SECURITY_CHALLENGE_FAILED"));
        assertTrue(logContent.contains("WRONG_ANSWER"));
    }
}
