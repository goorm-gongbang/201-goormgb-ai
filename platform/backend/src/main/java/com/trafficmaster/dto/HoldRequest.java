package com.trafficmaster.dto;

import java.util.List;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class HoldRequest {

    @NotNull(message = "sessionId is required")
    private String sessionId;

    @NotBlank(message = "gameId is required")
    private String gameId;

    @Builder.Default
    private String mode = "RECOMMEND";

    private String seatBundleId;

    @NotEmpty(message = "seatIds is required")
    private List<String> seatIds;
}
