package com.trafficmaster.controller;

import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trafficmaster.audit.DecisionAuditLogger;

@SpringBootTest
@AutoConfigureMockMvc
class BookingControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private DecisionAuditLogger auditLogger;

    @BeforeEach
    void clearAuditLog() throws Exception {
        // Clear audit log before each test
        Path logPath = auditLogger.getLogPath();
        if (Files.exists(logPath)) {
            Files.writeString(logPath, "");
        }
    }

    // ─── GameController Tests ───

    @Test
    @DisplayName("GET /api/games/{gameId} - returns mock GameDetail with 200")
    void getGame_shouldReturnGameDetail() throws Exception {
        mockMvc.perform(get("/api/games/game-001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.gameId").value("game-001"))
                .andExpect(jsonPath("$.homeTeam.name").isNotEmpty())
                .andExpect(jsonPath("$.awayTeam.name").isNotEmpty())
                .andExpect(jsonPath("$.venue.name").isNotEmpty())
                .andExpect(jsonPath("$.saleStatus").value("ON_SALE"))
                .andExpect(jsonPath("$.priceTable").isArray())
                .andExpect(jsonPath("$.priceTable", hasSize(greaterThan(0))));
    }

    // ─── SessionController Tests ───

    @Test
    @DisplayName("GET /preferences - unknown session returns default values")
    void getPreferences_unknownSession_shouldReturnDefaults() throws Exception {
        mockMvc.perform(get("/api/sessions/unknown-session-123/preferences"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.recommendEnabled").value(false))
                .andExpect(jsonPath("$.partySize").value(2))
                .andExpect(jsonPath("$.priceFilterEnabled").value(false))
                .andExpect(jsonPath("$.priceRange.min").value(20000))
                .andExpect(jsonPath("$.priceRange.max").value(100000));
    }

    @Test
    @DisplayName("POST /preferences - valid update returns 200")
    void updatePreferences_valid_shouldReturn200() throws Exception {
        String body = """
                {
                    "recommendEnabled": true,
                    "partySize": 4,
                    "priceFilterEnabled": true,
                    "priceRange": { "min": 30000, "max": 80000 }
                }
                """;

        mockMvc.perform(post("/api/sessions/session-abc/preferences")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.recommendEnabled").value(true))
                .andExpect(jsonPath("$.partySize").value(4))
                .andExpect(jsonPath("$.priceRange.min").value(30000));
    }

    @Test
    @DisplayName("POST /preferences - partySize=11 returns 400 (validation)")
    void updatePreferences_invalidPartySize_shouldReturn400() throws Exception {
        String body = """
                {
                    "recommendEnabled": false,
                    "partySize": 11,
                    "priceFilterEnabled": false,
                    "priceRange": { "min": 20000, "max": 100000 }
                }
                """;

        mockMvc.perform(post("/api/sessions/session-xyz/preferences")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("POST /preferences - partySize=0 returns 400 (validation)")
    void updatePreferences_partySizeZero_shouldReturn400() throws Exception {
        String body = """
                {
                    "partySize": 0,
                    "priceRange": { "min": 20000, "max": 100000 }
                }
                """;

        mockMvc.perform(post("/api/sessions/session-xyz/preferences")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest());
    }

    // ─── BookingController Tests ───

    @Test
    @DisplayName("POST /api/booking/entry - valid request returns queueTicketId")
    void enterBooking_valid_shouldReturnQueueTicket() throws Exception {
        String body = """
                {
                    "sessionId": "session-booking-test",
                    "gameId": "game-001",
                    "preferences": {
                        "recommendEnabled": true,
                        "partySize": 2,
                        "priceFilterEnabled": false,
                        "priceRange": { "min": 20000, "max": 100000 }
                    }
                }
                """;

        mockMvc.perform(post("/api/booking/entry")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.queueTicketId").isNotEmpty())
                .andExpect(jsonPath("$.nextUrl").isNotEmpty());
    }

    @Test
    @DisplayName("POST /api/booking/entry - missing sessionId returns 400")
    void enterBooking_missingSessionId_shouldReturn400() throws Exception {
        String body = """
                {
                    "gameId": "game-001"
                }
                """;

        mockMvc.perform(post("/api/booking/entry")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest());
    }

    // ─── Audit Log Verification ───

    @Test
    @DisplayName("POST /api/booking/entry - writes BOOKING_CLICKED to audit log")
    void enterBooking_shouldWriteAuditLog() throws Exception {
        String body = """
                {
                    "sessionId": "session-audit-test",
                    "gameId": "game-001",
                    "preferences": {
                        "recommendEnabled": false,
                        "partySize": 3,
                        "priceFilterEnabled": false,
                        "priceRange": { "min": 20000, "max": 100000 }
                    }
                }
                """;

        mockMvc.perform(post("/api/booking/entry")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk());

        // Verify audit log contains the BOOKING_CLICKED event
        Path logPath = auditLogger.getLogPath();
        List<String> lines = Files.readAllLines(logPath);

        boolean found = lines.stream()
                .anyMatch(line -> line.contains("BOOKING_CLICKED")
                        && line.contains("session-audit-test")
                        && line.contains("game-001"));

        assert found : "Expected BOOKING_CLICKED event in audit log but not found. Log contents: " + lines;
    }
}
