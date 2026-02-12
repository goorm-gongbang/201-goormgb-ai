package com.trafficmaster.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.trafficmaster.dto.QueueEnterRequest;
import com.trafficmaster.dto.QueueTicketResponse;
import com.trafficmaster.queue.QueueService;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

/**
 * Stage 2 SSOT API contract:
 *   POST /api/queue/enter     — 대기열 진입 요청
 *   GET  /api/queue/{ticketId} — 대기열 상태 폴링
 */
@RestController
@RequestMapping("/api/queue")
@RequiredArgsConstructor
public class QueueController {

    private final QueueService queueService;

    @PostMapping("/enter")
    public ResponseEntity<QueueTicketResponse> enterQueue(
            @Valid @RequestBody QueueEnterRequest request) {
        QueueTicketResponse response = queueService.enter(request);
        return ResponseEntity.ok(response);
    }

    @GetMapping("/{queueTicketId}")
    public ResponseEntity<QueueTicketResponse> pollQueue(
            @PathVariable String queueTicketId) {
        QueueTicketResponse response = queueService.poll(queueTicketId);
        if ("NOT_FOUND".equals(response.getStatus())) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(response);
    }
}
