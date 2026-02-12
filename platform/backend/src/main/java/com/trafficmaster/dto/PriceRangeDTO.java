package com.trafficmaster.dto;

import jakarta.validation.constraints.AssertTrue;
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
public class PriceRangeDTO {

    @Min(value = 20000, message = "min price must be at least 20000")
    @Builder.Default
    private int min = 20000;

    @Max(value = 100000, message = "max price must be at most 100000")
    @Builder.Default
    private int max = 100000;

    @AssertTrue(message = "min must be less than or equal to max")
    public boolean isValidRange() {
        return min <= max;
    }

    public static PriceRangeDTO defaultRange() {
        return PriceRangeDTO.builder().min(20000).max(100000).build();
    }
}
