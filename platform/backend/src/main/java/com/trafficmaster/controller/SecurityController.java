package com.trafficmaster.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.trafficmaster.dto.ChallengeResponse;
import com.trafficmaster.dto.VerifyRequest;
import com.trafficmaster.dto.VerifyResponse;
import com.trafficmaster.security.SecurityService;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

/**
 * Stage 3 SSOT API contract:
 *   GET  /api/security/challenge  — 챌린지 발급
 *   POST /api/security/verify     — 답안 검증
 */
@RestController
@RequestMapping("/api/security")
@RequiredArgsConstructor
public class SecurityController {

    private final SecurityService securityService;

    @GetMapping("/challenge")
    public ResponseEntity<ChallengeResponse> getChallenge(
            @RequestParam(defaultValue = "") String sessionId,
            @RequestParam(required = false) Integer insertedAtStage) {
        ChallengeResponse response = securityService.issueChallenge(sessionId, insertedAtStage);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/verify")
    public ResponseEntity<VerifyResponse> verify(
            @Valid @RequestBody VerifyRequest request) {
        VerifyResponse response = securityService.verify(request);
        return ResponseEntity.ok(response);
    }
}
