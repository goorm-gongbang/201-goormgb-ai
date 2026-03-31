package com.trafficmaster.controller;

import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.trafficmaster.audit.DecisionAuditLogger;

@SpringBootTest
@AutoConfigureMockMvc
class QueueControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private DecisionAuditLogger auditLogger;

    @BeforeEach
    void clearAuditLog() throws Exception {
        Path logPath = auditLogger.getLogPath();
        if (Files.exists(logPath)) {
            Files.writeString(logPath, "");
        }
    }

    // ─── Queue Enter Tests ───

    @Test
    @DisplayName("POST /api/queue/enter - returns ticket with WAITING status")
    void enterQueue_shouldReturnWaitingTicket() throws Exception {
        String body = """
                {
                    "sessionId": "session-q1",
                    "gameId": "game-001",
                    "mode": "RECOMMEND"
                }
                """;

        mockMvc.perform(post("/api/queue/enter")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.queueTicketId").isNotEmpty())
                .andExpect(jsonPath("$.position").isNumber())
                .andExpect(jsonPath("$.position", greaterThanOrEqualTo(1000)))
                .andExpect(jsonPath("$.estimatedWaitMs").value(5000))
                .andExpect(jsonPath("$.status").value("WAITING"))
                .andExpect(jsonPath("$.progress").value(0.0));
    }

    @Test
    @DisplayName("POST /api/queue/enter - logs STAGE_2_QUEUE_SHOWN event")
    void enterQueue_shouldLogEvent() throws Exception {
        String body = """
                {
                    "sessionId": "session-q-audit",
                    "gameId": "game-001",
                    "mode": "RECOMMEND"
                }
                """;

        mockMvc.perform(post("/api/queue/enter")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk());

        String logContent = Files.readString(auditLogger.getLogPath());
        assert logContent.contains("STAGE_2_QUEUE_SHOWN") :
                "Expected STAGE_2_QUEUE_SHOWN in audit log";
    }

    // ─── Polling Tests ───

    @Test
    @DisplayName("GET /api/queue/{id} - position decreases on each poll")
    void pollQueue_shouldDecreasePosition() throws Exception {
        // First, enter the queue
        String body = """
                {
                    "sessionId": "session-q-poll",
                    "gameId": "game-001",
                    "mode": "RECOMMEND"
                }
                """;

        MvcResult enterResult = mockMvc.perform(post("/api/queue/enter")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode enterJson = objectMapper.readTree(enterResult.getResponse().getContentAsString());
        String ticketId = enterJson.get("queueTicketId").asText();
        int initialPosition = enterJson.get("position").asInt();

        // Poll once
        MvcResult pollResult = mockMvc.perform(get("/api/queue/" + ticketId))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode pollJson = objectMapper.readTree(pollResult.getResponse().getContentAsString());
        int newPosition = pollJson.get("position").asInt();

        assert newPosition < initialPosition :
                "Expected position to decrease. Initial: " + initialPosition + ", Current: " + newPosition;
    }

    @Test
    @DisplayName("GET /api/queue/{id} - eventually transitions to GRANTED")
    void pollQueue_shouldEventuallyGrant() throws Exception {
        // Enter queue
        String body = """
                {
                    "sessionId": "session-q-grant",
                    "gameId": "game-001",
                    "mode": "RECOMMEND"
                }
                """;

        MvcResult enterResult = mockMvc.perform(post("/api/queue/enter")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode enterJson = objectMapper.readTree(enterResult.getResponse().getContentAsString());
        String ticketId = enterJson.get("queueTicketId").asText();

        // Poll repeatedly until GRANTED (max 200 iterations to prevent infinite loop)
        String status = "WAITING";
        String nextUrl = null;
        for (int i = 0; i < 200 && "WAITING".equals(status); i++) {
            MvcResult pollResult = mockMvc.perform(get("/api/queue/" + ticketId))
                    .andExpect(status().isOk())
                    .andReturn();
            JsonNode pollJson = objectMapper.readTree(pollResult.getResponse().getContentAsString());
            status = pollJson.get("status").asText();
            if (pollJson.has("nextUrl") && !pollJson.get("nextUrl").isNull()) {
                nextUrl = pollJson.get("nextUrl").asText();
            }
        }

        assert "GRANTED".equals(status) : "Expected GRANTED status but got: " + status;
        assert nextUrl != null && !nextUrl.isEmpty() : "Expected nextUrl to be present";
    }

    @Test
    @DisplayName("GET /api/queue/{id} - GRANTED triggers QUEUE_ENTRY_GRANTED log")
    void pollQueue_grantedShouldLog() throws Exception {
        // Enter
        String body = """
                {
                    "sessionId": "session-q-grantlog",
                    "gameId": "game-001",
                    "mode": "RECOMMEND"
                }
                """;

        MvcResult enterResult = mockMvc.perform(post("/api/queue/enter")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andReturn();

        JsonNode enterJson = objectMapper.readTree(enterResult.getResponse().getContentAsString());
        String ticketId = enterJson.get("queueTicketId").asText();

        // Poll until GRANTED
        String status = "WAITING";
        for (int i = 0; i < 200 && "WAITING".equals(status); i++) {
            MvcResult r = mockMvc.perform(get("/api/queue/" + ticketId)).andReturn();
            status = objectMapper.readTree(r.getResponse().getContentAsString()).get("status").asText();
        }

        String logContent = Files.readString(auditLogger.getLogPath());
        assert logContent.contains("QUEUE_ENTRY_GRANTED") :
                "Expected QUEUE_ENTRY_GRANTED in audit log";
    }

    @Test
    @DisplayName("GET /api/queue/{unknown-id} - returns 404")
    void pollQueue_unknownId_shouldReturn404() throws Exception {
        mockMvc.perform(get("/api/queue/nonexistent-ticket"))
                .andExpect(status().isNotFound());
    }
}
