package com.trafficmaster.seat;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

import org.springframework.stereotype.Service;

import com.trafficmaster.dto.ZoneResponse;
import com.trafficmaster.dto.ZoneResponse.ZoneDTO;
import com.trafficmaster.dto.ZoneResponse.ZoneGroupDTO;
import com.trafficmaster.dto.ZoneSeatGridResponse;
import com.trafficmaster.dto.ZoneSeatGridResponse.SeatCellDTO;

/**
 * Stage 5 MAP mode: mock zone and seat grid data.
 * ~20% of seats are HELD_BY_OTHERS or UNAVAILABLE for realistic UI testing.
 */
@Service
public class MapService {

    private static final String[][] ZONE_DATA = {
            // groupId, zoneId, label
            {"floor-1", "zone-1a", "1층 A구역"},
            {"floor-1", "zone-1b", "1층 B구역"},
            {"floor-1", "zone-1c", "1층 C구역"},
            {"floor-1", "zone-1d", "1층 D구역"},
            {"floor-2", "zone-2a", "2층 A구역"},
            {"floor-2", "zone-2b", "2층 B구역"},
            {"floor-2", "zone-2c", "2층 C구역"},
            {"floor-3", "zone-3a", "3층 A구역"},
            {"floor-3", "zone-3b", "3층 B구역"},
    };

    // ─── Get Zones ───

    public ZoneResponse getZones(String gameId) {
        List<ZoneDTO> zones = new ArrayList<>();
        for (String[] z : ZONE_DATA) {
            int remaining = ThreadLocalRandom.current().nextInt(0, 80);
            zones.add(ZoneDTO.builder()
                    .zoneId(z[1])
                    .label(z[2])
                    .groupId(z[0])
                    .remaining(remaining)
                    .disabled(remaining == 0)
                    .build());
        }

        List<ZoneGroupDTO> groups = Arrays.asList(
                ZoneGroupDTO.builder().groupId("floor-1").label("1층").build(),
                ZoneGroupDTO.builder().groupId("floor-2").label("2층").build(),
                ZoneGroupDTO.builder().groupId("floor-3").label("3층").build()
        );

        return ZoneResponse.builder()
                .zones(zones)
                .groups(groups)
                .build();
    }

    // ─── Get Seat Grid ───

    public ZoneSeatGridResponse getSeatGrid(String zoneId, String gameId) {
        int rows = 10;
        int cols = 15;
        List<SeatCellDTO> seats = new ArrayList<>();

        String rowPrefix = zoneId.replace("zone-", "").toUpperCase();

        for (int r = 1; r <= rows; r++) {
            for (int c = 1; c <= cols; c++) {
                String seatId = rowPrefix + "-" + r + "-" + c;
                String label = r + "열 " + c + "번";
                String status = randomStatus();

                seats.add(SeatCellDTO.builder()
                        .seatId(seatId)
                        .label(label)
                        .status(status)
                        .build());
            }
        }

        return ZoneSeatGridResponse.builder()
                .zoneId(zoneId)
                .rows(rows)
                .cols(cols)
                .seats(seats)
                .build();
    }

    private String randomStatus() {
        int roll = ThreadLocalRandom.current().nextInt(100);
        if (roll < 10) return "HELD_BY_OTHERS";
        if (roll < 20) return "UNAVAILABLE";
        return "AVAILABLE";
    }
}
