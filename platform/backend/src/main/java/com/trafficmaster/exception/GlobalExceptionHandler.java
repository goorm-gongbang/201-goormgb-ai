package com.trafficmaster.exception;

import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import com.trafficmaster.audit.AuditEvent;
import com.trafficmaster.audit.DecisionAuditLogger;

import lombok.RequiredArgsConstructor;

/**
 * Stage 7: Global exception handler returning standard { status, reasonCode } format.
 */
@RestControllerAdvice
@RequiredArgsConstructor
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);
    private final DecisionAuditLogger auditLogger;

    @ExceptionHandler(TrafficMasterException.class)
    public ResponseEntity<Map<String, Object>> handleTrafficMaster(TrafficMasterException ex) {
        log.warn("TrafficMasterException: {} - {}", ex.getReasonCode(), ex.getMessage());

        auditLogger.log(AuditEvent.builder()
                .sessionId(MDC.get("sessionId"))
                .requestId(MDC.get("requestId"))
                .correlationId(MDC.get("correlationId"))
                .stage("ERROR")
                .eventType("EXCEPTION")
                .actor(MDC.get("actor") != null ? MDC.get("actor") : "SYSTEM")
                .result(AuditEvent.Result.builder()
                        .status("FAIL")
                        .reasonCode(ex.getReasonCode())
                        .build())
                .payload(Map.of("message", ex.getMessage()))
                .build());

        return ResponseEntity.status(ex.getHttpStatus())
                .body(Map.of(
                        "status", "FAIL",
                        "reasonCode", ex.getReasonCode(),
                        "message", ex.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handleValidation(MethodArgumentNotValidException ex) {
        String detail = ex.getBindingResult().getFieldErrors().stream()
                .map(e -> e.getField() + ": " + e.getDefaultMessage())
                .reduce((a, b) -> a + "; " + b)
                .orElse("Validation failed");

        return ResponseEntity.badRequest()
                .body(Map.of(
                        "status", "FAIL",
                        "reasonCode", "VALIDATION_ERROR",
                        "message", detail));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> handleGeneric(Exception ex) {
        log.error("Unhandled exception: {}", ex.getMessage(), ex);

        auditLogger.log(AuditEvent.builder()
                .sessionId(MDC.get("sessionId"))
                .requestId(MDC.get("requestId") != null ? MDC.get("requestId") : UUID.randomUUID().toString())
                .correlationId(MDC.get("correlationId"))
                .stage("ERROR")
                .eventType("UNHANDLED_EXCEPTION")
                .actor("SYSTEM")
                .result(AuditEvent.Result.builder()
                        .status("FAIL")
                        .reasonCode("INTERNAL_ERROR")
                        .build())
                .payload(Map.of("message", ex.getMessage() != null ? ex.getMessage() : "Unknown error"))
                .build());

        return ResponseEntity.status(500)
                .body(Map.of(
                        "status", "FAIL",
                        "reasonCode", "INTERNAL_ERROR",
                        "message", "서버 내부 오류가 발생했습니다."));
    }
}
