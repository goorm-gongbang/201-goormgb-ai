package com.trafficmaster.controller;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.trafficmaster.audit.DecisionAuditLogger;
import com.trafficmaster.dto.GameDetailDTO;
import com.trafficmaster.dto.PriceItemDTO;
import com.trafficmaster.dto.TeamDTO;
import com.trafficmaster.dto.VenueDTO;

import lombok.RequiredArgsConstructor;

/**
 * Stage 1 SSOT: GET /api/games/{gameId}
 * Returns mock game detail data for MVP.
 */
@RestController
@RequestMapping("/api/games")
@RequiredArgsConstructor
public class GameController {

    private final DecisionAuditLogger auditLogger;

    @GetMapping("/{gameId}")
    public ResponseEntity<GameDetailDTO> getGame(@PathVariable String gameId) {
        GameDetailDTO game = buildMockGame(gameId);

        auditLogger.logStage1Event(
                null, "STAGE_1_ENTRY_VIEWED",
                Map.of("gameId", gameId),
                "OK", null
        );

        return ResponseEntity.ok(game);
    }

    private GameDetailDTO buildMockGame(String gameId) {
        return GameDetailDTO.builder()
                .gameId(gameId)
                .homeTeam(TeamDTO.builder()
                        .name("KIA 타이거즈")
                        .logo("/images/kia.png")
                        .build())
                .awayTeam(TeamDTO.builder()
                        .name("두산 베어스")
                        .logo("/images/doosan.png")
                        .build())
                .dateTime(Instant.now().plus(7, ChronoUnit.DAYS))
                .venue(VenueDTO.builder()
                        .name("광주-기아 챔피언스 필드")
                        .location("광주광역시 북구 서림로 10")
                        .build())
                .saleStatus(GameDetailDTO.SaleStatus.ON_SALE)
                .dDay(7)
                .priceTable(List.of(
                        PriceItemDTO.builder().grade("VIP").price(80000).color("#FFD700").build(),
                        PriceItemDTO.builder().grade("테이블").price(60000).color("#C0C0C0").build(),
                        PriceItemDTO.builder().grade("중앙 지정석").price(25000).color("#4169E1").build(),
                        PriceItemDTO.builder().grade("외야 자유석").price(13000).color("#32CD32").build(),
                        PriceItemDTO.builder().grade("외야 잔디석").price(8000).color("#90EE90").build()
                ))
                .build();
    }
}
