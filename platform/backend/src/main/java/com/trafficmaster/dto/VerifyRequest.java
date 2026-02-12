package com.trafficmaster.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class VerifyRequest {

    @NotBlank(message = "challengeId is required")
    private String challengeId;

    @NotBlank(message = "answer is required")
    private String answer;

    @NotNull(message = "sessionId is required")
    private String sessionId;
}
