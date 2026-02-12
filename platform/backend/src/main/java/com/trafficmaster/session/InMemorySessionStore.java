package com.trafficmaster.session;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

/**
 * In-memory session store using ConcurrentHashMap.
 * Suitable for MVP / single-instance deployment only.
 * Replace with Redis-backed implementation for production.
 */
@Component
public class InMemorySessionStore implements SessionStore {

    private final ConcurrentHashMap<String, SessionData> store = new ConcurrentHashMap<>();

    @Override
    public Optional<SessionData> get(String sessionId) {
        return Optional.ofNullable(store.get(sessionId));
    }

    @Override
    public SessionData save(SessionData session) {
        store.put(session.getSessionId(), session);
        return session;
    }

    @Override
    public boolean exists(String sessionId) {
        return store.containsKey(sessionId);
    }
}
