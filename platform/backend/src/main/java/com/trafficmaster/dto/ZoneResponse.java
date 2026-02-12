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
public class ZoneResponse {

    private List<ZoneDTO> zones;
    private List<ZoneGroupDTO> groups;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ZoneDTO {
        private String zoneId;
        private String label;
        private String groupId;
        private int remaining;
        private boolean disabled;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ZoneGroupDTO {
        private String groupId;
        private String label;
    }
}
