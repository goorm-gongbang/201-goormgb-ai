package com.trafficmaster.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.trafficmaster.dto.ZoneResponse;
import com.trafficmaster.dto.ZoneSeatGridResponse;
import com.trafficmaster.seat.MapService;

import lombok.RequiredArgsConstructor;

/**
 * Stage 5 MAP mode: Zone and seat grid APIs.
 *   GET /api/zones           — list zones grouped by floor
 *   GET /api/zones/{id}/seats — seat grid for a specific zone
 */
@RestController
@RequestMapping("/api/zones")
@RequiredArgsConstructor
public class MapController {

    private final MapService mapService;

    @GetMapping
    public ResponseEntity<ZoneResponse> getZones(
            @RequestParam(defaultValue = "game-001") String gameId) {
        return ResponseEntity.ok(mapService.getZones(gameId));
    }

    @GetMapping("/{zoneId}/seats")
    public ResponseEntity<ZoneSeatGridResponse> getSeatGrid(
            @PathVariable String zoneId,
            @RequestParam(defaultValue = "game-001") String gameId) {
        return ResponseEntity.ok(mapService.getSeatGrid(zoneId, gameId));
    }
}
