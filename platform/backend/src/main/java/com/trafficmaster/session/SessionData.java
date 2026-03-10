package com.trafficmaster.session;

import java.time.Instant;

import com.trafficmaster.dto.PreferencesDTO;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SessionData {

    private String sessionId;

    @Builder.Default
    private String currentStage = "S1";

    @Builder.Default
    private PreferencesDTO preferences = new PreferencesDTO();

    private Instant createdAt;
    private Instant updatedAt;

    public static SessionData createNew(String sessionId) {
        Instant now = Instant.now();
        return SessionData.builder()
                .sessionId(sessionId)
                .currentStage("S1")
                .preferences(new PreferencesDTO())
                .createdAt(now)
                .updatedAt(now)
                .build();
    }
}
