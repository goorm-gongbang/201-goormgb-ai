package com.trafficmaster.queue;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ThreadLocalRandom;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.dto.QueueEnterRequest;
import com.trafficmaster.dto.QueueTicketResponse;

import lombok.RequiredArgsConstructor;

/**
 * Mock queue service implementing Stage 2 SSOT logic.
 * 
 * Enter: creates ticket with random position (1000-20000), estimatedWaitMs = 5000.
 * Poll:  each call decreases position by 100-500; transitions to GRANTED when
 *        position <= 0 OR elapsed time >= estimatedWaitMs.
 */
@Service
@RequiredArgsConstructor
public class QueueService {

    private static final Logger log = LoggerFactory.getLogger(QueueService.class);

    private final DecisionAuditLogger auditLogger;
    private final ConcurrentHashMap<String, QueueTicket> ticketStore = new ConcurrentHashMap<>();

    // ─── Enter Queue ───

    public QueueTicketResponse enter(QueueEnterRequest request) {
        String ticketId = UUID.randomUUID().toString();
        int initialPosition = ThreadLocalRandom.current().nextInt(1000, 20001);

        QueueTicket ticket = QueueTicket.builder()
                .queueTicketId(ticketId)
                .sessionId(request.getSessionId())
                .gameId(request.getGameId())
                .mode(parseMode(request.getMode()))
                .position(initialPosition)
                .initialPosition(initialPosition)
                .status(QueueTicket.Status.WAITING)
                .estimatedWaitMs(5000)
                .createdAt(Instant.now())
                .build();

        ticketStore.put(ticketId, ticket);

        // Log STAGE_2_QUEUE_SHOWN event
        auditLogger.logStage1Event(
                request.getSessionId(),
                "STAGE_2_QUEUE_SHOWN",
                Map.of(
                        "queueTicketId", ticketId,
                        "initialPosition", initialPosition,
                        "estimatedWaitMs", 5000,
                        "gameId", request.getGameId()
                ),
                "OK", null
        );

        log.info("Queue ticket created: {} at position {} for session {}",
                ticketId, initialPosition, request.getSessionId());

        return QueueTicketResponse.builder()
                .queueTicketId(ticketId)
                .position(initialPosition)
                .estimatedWaitMs(5000)
                .status("WAITING")
                .progress(0.0)
                .build();
    }

    // ─── Poll Queue Status ───

    public QueueTicketResponse poll(String queueTicketId) {
        QueueTicket ticket = ticketStore.get(queueTicketId);

        if (ticket == null) {
            return QueueTicketResponse.builder()
                    .queueTicketId(queueTicketId)
                    .status("NOT_FOUND")
                    .build();
        }

        // If already granted, return final state
        if (ticket.getStatus() == QueueTicket.Status.GRANTED) {
            return buildGrantedResponse(ticket);
        }

        // Decrease position by random 100-500
        int decrease = ThreadLocalRandom.current().nextInt(100, 501);
        int newPosition = Math.max(0, ticket.getPosition() - decrease);
        ticket.setPosition(newPosition);

        // Check transition conditions (SSOT stateLogic)
        boolean shouldGrant = newPosition <= 0 || ticket.isTimeExpired();

        if (shouldGrant) {
            ticket.setStatus(QueueTicket.Status.GRANTED);
            ticket.setPosition(0);

            // Log QUEUE_ENTRY_GRANTED
            auditLogger.logStage1Event(
                    ticket.getSessionId(),
                    "QUEUE_ENTRY_GRANTED",
                    Map.of(
                            "queueTicketId", queueTicketId,
                            "elapsedMs", Instant.now().toEpochMilli() - ticket.getCreatedAt().toEpochMilli()
                    ),
                    "OK", null
            );

            log.info("Queue ticket GRANTED: {} for session {}", queueTicketId, ticket.getSessionId());
            return buildGrantedResponse(ticket);
        }

        // Log position update
        auditLogger.logStage1Event(
                ticket.getSessionId(),
                "QUEUE_POSITION_UPDATED",
                Map.of(
                        "queueTicketId", queueTicketId,
                        "position", newPosition,
                        "progress", ticket.getProgress()
                ),
                "OK", null
        );

        return QueueTicketResponse.builder()
                .queueTicketId(queueTicketId)
                .position(newPosition)
                .estimatedWaitMs(ticket.getEstimatedWaitMs())
                .status("WAITING")
                .progress(ticket.getProgress())
                .build();
    }

    // ─── Helpers ───

    private QueueTicketResponse buildGrantedResponse(QueueTicket ticket) {
        String mode = ticket.getMode() != null ? ticket.getMode().name() : "RECOMMEND";
        return QueueTicketResponse.builder()
                .queueTicketId(ticket.getQueueTicketId())
                .position(0)
                .estimatedWaitMs(ticket.getEstimatedWaitMs())
                .status("GRANTED")
                .progress(1.0)
                .nextUrl("/seats?mode=" + mode)
                .build();
    }

    private QueueTicket.Mode parseMode(String mode) {
        try {
            return QueueTicket.Mode.valueOf(mode.toUpperCase());
        } catch (Exception e) {
            return QueueTicket.Mode.RECOMMEND;
        }
    }
}
