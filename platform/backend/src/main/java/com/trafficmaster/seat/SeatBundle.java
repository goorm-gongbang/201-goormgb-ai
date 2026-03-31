package com.trafficmaster.seat;

import java.util.List;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Stage 4/5 SSOT: SeatBundle — recommended seat grouping.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class SeatBundle {
    private String seatBundleId;
    private String gameId;
    private List<String> seatIds;
    private String sectionLabel;
    private String rowLabel;
    private int totalPrice;
    private int rank;  // 1, 2, or 3
}
