package com.trafficmaster.controller;

import java.time.Instant;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.dto.PreferencesDTO;
import com.trafficmaster.session.SessionData;
import com.trafficmaster.session.SessionStore;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

/**
 * Stage 1 SSOT:
 *   GET  /api/sessions/{sessionId}/preferences
 *   POST /api/sessions/{sessionId}/preferences
 */
@RestController
@RequestMapping("/api/sessions")
@RequiredArgsConstructor
public class SessionController {

    private final SessionStore sessionStore;
    private final DecisionAuditLogger auditLogger;

    /**
     * Returns preferences for the session.
     * If session doesn't exist, creates one with default preferences.
     */
    @GetMapping("/{sessionId}/preferences")
    public ResponseEntity<PreferencesDTO> getPreferences(@PathVariable String sessionId) {
        SessionData session = sessionStore.getOrCreate(sessionId);
        return ResponseEntity.ok(session.getPreferences());
    }

    /**
     * Updates preferences for the session.
     * Validates partySize (1-10) and priceRange constraints.
     */
    @PostMapping("/{sessionId}/preferences")
    public ResponseEntity<PreferencesDTO> updatePreferences(
            @PathVariable String sessionId,
            @Valid @RequestBody PreferencesDTO preferences) {

        SessionData session = sessionStore.getOrCreate(sessionId);
        PreferencesDTO oldPrefs = session.getPreferences();
        session.setPreferences(preferences);
        session.setUpdatedAt(Instant.now());
        sessionStore.save(session);

        // Log preference change event
        auditLogger.logStage1Event(
                sessionId, "PREFERENCE_TOGGLE_CHANGED",
                Map.of(
                        "recommendEnabled", preferences.isRecommendEnabled(),
                        "partySize", preferences.getPartySize(),
                        "priceFilterEnabled", preferences.isPriceFilterEnabled(),
                        "priceRange", Map.of(
                                "min", preferences.getPriceRange().getMin(),
                                "max", preferences.getPriceRange().getMax()
                        )
                ),
                "OK", null
        );

        return ResponseEntity.ok(preferences);
    }
}
