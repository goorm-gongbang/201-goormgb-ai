package com.trafficmaster.core;

import java.io.IOException;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;

import com.trafficmaster.audit.AuditEvent;
import com.trafficmaster.audit.DecisionAuditLogger;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;

/**
 * Stage 7: HTTP filter that sets MDC context and logs request/response with latency.
 * MDC keys: sessionId, requestId, correlationId
 */
@Component
@RequiredArgsConstructor
public class LogFilter implements Filter {

    private static final Logger log = LoggerFactory.getLogger(LogFilter.class);
    private final DecisionAuditLogger auditLogger;

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest req = (HttpServletRequest) request;
        HttpServletResponse res = (HttpServletResponse) response;

        long start = System.currentTimeMillis();

        // 1. Set MDC
        String requestId = UUID.randomUUID().toString();
        String correlationId = req.getHeader("X-Correlation-Id");
        if (correlationId == null || correlationId.isBlank()) {
            correlationId = UUID.randomUUID().toString();
        }
        String sessionId = req.getHeader("X-Session-Id");
        if (sessionId == null) sessionId = "anonymous";

        String actor = req.getHeader("X-TM-Actor");
        if (actor == null) actor = "USER";

        MDC.put("requestId", requestId);
        MDC.put("correlationId", correlationId);
        MDC.put("sessionId", sessionId);
        MDC.put("actor", actor);

        // Set correlation ID on response for tracing
        res.setHeader("X-Correlation-Id", correlationId);
        res.setHeader("X-Request-Id", requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            long latency = System.currentTimeMillis() - start;

            // Log request completion
            auditLogger.log(AuditEvent.builder()
                    .sessionId(sessionId)
                    .requestId(requestId)
                    .correlationId(correlationId)
                    .stage("INFRA")
                    .eventType("HTTP_REQUEST")
                    .actor(actor)
                    .result(AuditEvent.Result.builder()
                            .status(res.getStatus() < 400 ? "OK" : "FAIL")
                            .reasonCode(res.getStatus() >= 400 ? String.valueOf(res.getStatus()) : null)
                            .build())
                    .payload(java.util.Map.of(
                            "method", req.getMethod(),
                            "uri", req.getRequestURI(),
                            "status", res.getStatus(),
                            "latencyMs", latency))
                    .build());

            MDC.clear();
        }
    }
}
