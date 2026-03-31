package com.trafficmaster.dto;

import java.time.Instant;
import java.util.List;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class GameDetailDTO {

    private String gameId;
    private TeamDTO homeTeam;
    private TeamDTO awayTeam;
    private Instant dateTime;
    private VenueDTO venue;
    private SaleStatus saleStatus;
    private int dDay;
    private List<PriceItemDTO> priceTable;

    public enum SaleStatus {
        ON_SALE, SOLD_OUT, CLOSED
    }
}
