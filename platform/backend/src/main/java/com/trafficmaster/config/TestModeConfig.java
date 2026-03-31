package com.trafficmaster.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import com.trafficmaster.audit.AuditEvent;
import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.contract.ReasonCodes;
import com.trafficmaster.contract.TmHeaders;
import com.trafficmaster.security.RiskControlService;
import com.trafficmaster.security.RiskDecision;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.util.Map;
import java.util.UUID;

/**
 * Stage 7: Test mode hooks — activated only when TM_TEST_MODE=true.
 * Intercepts test headers and stores them as request attributes for services to read.
 */
@Configuration
@ConditionalOnProperty(name = "trafficmaster.test-mode.enabled", havingValue = "true", matchIfMissing = false)
@lombok.RequiredArgsConstructor
public class TestModeConfig implements WebMvcConfigurer {

    private static final Logger log = LoggerFactory.getLogger(TestModeConfig.class);
    private final com.trafficmaster.security.SecurityService securityService;
    private final RiskControlService riskControlService;
    private final DecisionAuditLogger auditLogger;

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        log.warn("⚠️ TEST MODE ACTIVE — Test hooks enabled");
        registry.addInterceptor(new TestHookInterceptor(securityService, riskControlService, auditLogger))
                .addPathPatterns("/api/**");
    }

    /**
     * Interceptor that reads X-TM-* headers and sets them as request attributes.
     * Also enforces Security Challenge if configured.
     */
    @lombok.RequiredArgsConstructor
    static class TestHookInterceptor implements HandlerInterceptor {
        
        private final com.trafficmaster.security.SecurityService securityService;
        private final RiskControlService riskControlService;
        private final DecisionAuditLogger auditLogger;

        @Override
        public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
            // Mark test mode active for controllers
            request.setAttribute("tm.test.mode", true);

            // X-TM-QueueWaitMs → queue wait override
            String queueWait = request.getHeader(TmHeaders.X_TM_QUEUE_WAIT_MS);
            if (queueWait != null) {
                request.setAttribute("tm.test.queueWaitMs", Long.parseLong(queueWait));
            }

            // X-TM-HoldFailRate → hold failure rate
            String holdFail = request.getHeader(TmHeaders.X_TM_HOLD_FAIL_RATE);
            if (holdFail != null) {
                request.setAttribute("tm.test.holdFailRate", Double.parseDouble(holdFail));
            }

            // X-TM-PaymentFailRate → payment failure rate
            String payFail = request.getHeader(TmHeaders.X_TM_PAYMENT_FAIL_RATE);
            if (payFail != null) {
                request.setAttribute("tm.test.paymentFailRate", Double.parseDouble(payFail));
            }

            // X-TM-ForceChallenge → force security challenge
            // Default to TRUE in test mode for S7 demo (unless explicitly disabled)
            String forceChallengeHeader = request.getHeader(TmHeaders.X_TM_FORCE_CHALLENGE);
            boolean forceChallenge = forceChallengeHeader == null || "true".equalsIgnoreCase(forceChallengeHeader);
            
            String uri = request.getRequestURI();
            boolean isSeatEntry = uri.startsWith("/api/zones")
                    || uri.startsWith("/api/recommendations")
                    || uri.startsWith("/api/holds");

            // Defense gating: telemetry-based risk decision (AC-4).
            if (isSeatEntry) {
                String sessionId = request.getHeader(TmHeaders.X_SESSION_ID);
                if (sessionId != null && !sessionId.isBlank()) {
                    RiskDecision decision = riskControlService.decide(sessionId);
                    if (decision == RiskDecision.BLOCKED) {
                        auditLogger.log(AuditEvent.builder()
                                .sessionId(sessionId)
                                .stage("DEFENSE")
                                .eventType("DEF_BLOCKED")
                                .actor("SERVER")
                                .requestId(UUID.randomUUID().toString())
                                .payload(Map.of(
                                        "uri", uri,
                                        "decision", decision.name()
                                ))
                                .serverDecision(AuditEvent.ServerDecision.builder()
                                        .riskTier("T3")
                                        .action("BLOCK")
                                        .build())
                                .result(AuditEvent.Result.builder()
                                        .status("FAIL")
                                        .reasonCode(ReasonCodes.BLOCKED)
                                        .build())
                                .build());

                        throw com.trafficmaster.exception.TrafficMasterException.blocked();
                    }

                    if (decision == RiskDecision.CHALLENGE_REQUIRED) {
                        auditLogger.log(AuditEvent.builder()
                                .sessionId(sessionId)
                                .stage("DEFENSE")
                                .eventType("DEF_CHALLENGE_FORCED")
                                .actor("SERVER")
                                .requestId(UUID.randomUUID().toString())
                                .payload(Map.of(
                                        "uri", uri,
                                        "decision", decision.name()
                                ))
                                .serverDecision(AuditEvent.ServerDecision.builder()
                                        .riskTier("T2")
                                        .action("CHALLENGE")
                                        .build())
                                .result(AuditEvent.Result.builder()
                                        .status("FAIL")
                                        .reasonCode(ReasonCodes.CHALLENGE_REQUIRED)
                                        .build())
                                .build());

                        // Force a fresh challenge even if the session passed previously.
                        securityService.resetVerification(sessionId);
                        throw com.trafficmaster.exception.TrafficMasterException.challengeRequired();
                    }
                }
            }

            if (forceChallenge) {
                request.setAttribute("tm.test.forceChallenge", true);
                
                // Enforce challenge on specific Seat-related entry points
                if (isSeatEntry) {
                    String sessionId = request.getHeader(TmHeaders.X_SESSION_ID);
                    boolean verified = sessionId != null && securityService.isVerified(sessionId);
                    
                    log.info("[TestMode] Checking verification for session {}: {}", sessionId, verified);
                    
                    if (sessionId != null && !verified) {
                         // Not verified yet -> throw 428 to trigger modal
                         throw com.trafficmaster.exception.TrafficMasterException.challengeRequired();
                    }
                }
            }

            return true;
        }
    }
}
