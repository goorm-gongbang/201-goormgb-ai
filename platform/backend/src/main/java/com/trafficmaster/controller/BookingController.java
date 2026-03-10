package com.trafficmaster.controller;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.dto.BookingRequestDTO;
import com.trafficmaster.dto.BookingResponseDTO;
import com.trafficmaster.session.SessionData;
import com.trafficmaster.session.SessionStore;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

/**
 * Stage 1 SSOT: POST /api/booking/entry
 * 
 * Addendum Level 0 transition rule:
 *   S1 -> S2: "POST /api/booking/entry Success AND queueTicketId exists"
 * 
 * This endpoint mocks queue ticket creation and transitions session to S2.
 */
@RestController
@RequestMapping("/api/booking")
@RequiredArgsConstructor
public class BookingController {

    private final SessionStore sessionStore;
    private final DecisionAuditLogger auditLogger;

    @PostMapping("/entry")
    public ResponseEntity<BookingResponseDTO> enterBooking(
            @Valid @RequestBody BookingRequestDTO request) {

        // Ensure session exists and update stage per Addendum transition rule
        SessionData session = sessionStore.getOrCreate(request.getSessionId());

        // Apply preferences if provided
        if (request.getPreferences() != null) {
            session.setPreferences(request.getPreferences());
        }

        // Transition S1 -> S2 (Addendum: globalFlow.transitions)
        session.setCurrentStage("S2");
        session.setUpdatedAt(Instant.now());
        sessionStore.save(session);

        // Generate mock queue ticket
        String queueTicketId = UUID.randomUUID().toString();

        // Log BOOKING_CLICKED event (Stage 1 telemetry)
        auditLogger.logStage1Event(
                request.getSessionId(),
                "BOOKING_CLICKED",
                Map.of(
                        "gameId", request.getGameId(),
                        "queueTicketId", queueTicketId,
                        "preferences", Map.of(
                                "recommendEnabled", session.getPreferences().isRecommendEnabled(),
                                "partySize", session.getPreferences().getPartySize()
                        )
                ),
                "OK", null
        );

        BookingResponseDTO response = BookingResponseDTO.builder()
                .queueTicketId(queueTicketId)
                .nextUrl("/queue/" + queueTicketId)
                .build();

        return ResponseEntity.ok(response);
    }
}
