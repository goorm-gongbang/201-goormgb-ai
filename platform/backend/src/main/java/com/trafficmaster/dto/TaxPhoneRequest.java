package com.trafficmaster.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TaxPhoneRequest {

    @NotBlank(message = "phone is required")
    @Pattern(regexp = "^\\d{10,11}$", message = "phone must be 10-11 digits")
    private String phone;
}
