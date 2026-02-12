package com.trafficmaster.controller;

import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.trafficmaster.seat.SeatBundle;
import com.trafficmaster.seat.SeatService;

import lombok.RequiredArgsConstructor;

/**
 * Stage 4/5: GET /api/recommendations
 */
@RestController
@RequestMapping("/api/recommendations")
@RequiredArgsConstructor
public class RecommendationController {

    private final SeatService seatService;

    @GetMapping
    public ResponseEntity<List<SeatBundle>> getRecommendations(
            @RequestParam String gameId,
            @RequestParam(defaultValue = "") String sessionId,
            @RequestParam(defaultValue = "2") int partySize,
            @RequestParam(defaultValue = "all") String tab
    ) {
        List<SeatBundle> bundles = seatService.getRecommendations(gameId, partySize, tab);
        return ResponseEntity.ok(bundles);
    }
}
