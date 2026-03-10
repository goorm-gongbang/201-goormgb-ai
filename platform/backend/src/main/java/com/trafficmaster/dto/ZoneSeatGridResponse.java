package com.trafficmaster.dto;

import java.util.List;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ZoneSeatGridResponse {

    private String zoneId;
    private int rows;
    private int cols;
    private List<SeatCellDTO> seats;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class SeatCellDTO {
        private String seatId;
        private String label;
        private String status; // "AVAILABLE" | "HELD_BY_OTHERS" | "UNAVAILABLE"
    }
}
