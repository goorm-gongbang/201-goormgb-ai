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
public class TestModeConfig implements WebMvcConfigurer {

    private static final Logger log = LoggerFactory.getLogger(TestModeConfig.class);

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        log.warn("⚠️ TEST MODE ACTIVE — Test hooks enabled");
        registry.addInterceptor(new TestHookInterceptor()).addPathPatterns("/api/**");
    }

    /**
     * Interceptor that reads X-TM-* headers and sets them as request attributes.
     * Each service reads these attributes and applies the test behavior.
     */
    static class TestHookInterceptor implements HandlerInterceptor {

        @Override
        public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
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
            String forceChallenge = request.getHeader("X-TM-ForceChallenge");
            if ("true".equalsIgnoreCase(forceChallenge)) {
                request.setAttribute("tm.test.forceChallenge", true);
            }

            return true;
        }
    }
}
