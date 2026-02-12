package com.trafficmaster.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PreferencesDTO {

    @Builder.Default
    private boolean recommendEnabled = false;

    @Min(value = 1, message = "partySize must be at least 1")
    @Max(value = 10, message = "partySize must be at most 10")
    @Builder.Default
    private int partySize = 2;

    @Builder.Default
    private boolean priceFilterEnabled = false;

    @Valid
    @Builder.Default
    private PriceRangeDTO priceRange = PriceRangeDTO.defaultRange();
}
