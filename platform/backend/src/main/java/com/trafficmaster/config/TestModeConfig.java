package com.trafficmaster.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

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

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        log.warn("⚠️ TEST MODE ACTIVE — Test hooks enabled");
        registry.addInterceptor(new TestHookInterceptor(securityService)).addPathPatterns("/api/**");
    }

    /**
     * Interceptor that reads X-TM-* headers and sets them as request attributes.
     * Also enforces Security Challenge if configured.
     */
    @lombok.RequiredArgsConstructor
    static class TestHookInterceptor implements HandlerInterceptor {
        
        private final com.trafficmaster.security.SecurityService securityService;

        @Override
        public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
            // Mark test mode active for controllers
            request.setAttribute("tm.test.mode", true);

            // X-TM-QueueWaitMs → queue wait override
            String queueWait = request.getHeader("X-TM-QueueWaitMs");
            if (queueWait != null) {
                request.setAttribute("tm.test.queueWaitMs", Long.parseLong(queueWait));
            }

            // X-TM-HoldFailRate → hold failure rate
            String holdFail = request.getHeader("X-TM-HoldFailRate");
            if (holdFail != null) {
                request.setAttribute("tm.test.holdFailRate", Double.parseDouble(holdFail));
            }

            // X-TM-PaymentFailRate → payment failure rate
            String payFail = request.getHeader("X-TM-PaymentFailRate");
            if (payFail != null) {
                request.setAttribute("tm.test.paymentFailRate", Double.parseDouble(payFail));
            }

            // X-TM-ForceChallenge → force security challenge
            // Default to TRUE in test mode for S7 demo (unless explicitly disabled)
            String forceChallengeHeader = request.getHeader("X-TM-ForceChallenge");
            boolean forceChallenge = forceChallengeHeader == null || "true".equalsIgnoreCase(forceChallengeHeader);
            
            if (forceChallenge) {
                request.setAttribute("tm.test.forceChallenge", true);
                
                // Enforce challenge on specific Seat-related entry points
                String uri = request.getRequestURI();
                boolean isSeatEntry = uri.startsWith("/api/zones") || uri.startsWith("/api/recommendations");
                
                if (isSeatEntry) {
                    String sessionId = request.getHeader("X-Session-Id");
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
