package com.trafficmaster.session;

import java.util.Optional;

/**
 * Session persistence abstraction.
 * MVP uses InMemorySessionStore; production should swap to Redis.
 */
public interface SessionStore {

    Optional<SessionData> get(String sessionId);

    SessionData save(SessionData session);

    boolean exists(String sessionId);

    /**
     * Get existing session or create a new one with defaults.
     */
    default SessionData getOrCreate(String sessionId) {
        return get(sessionId).orElseGet(() -> save(SessionData.createNew(sessionId)));
    }
}
