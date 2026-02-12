package com.trafficmaster.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class QueueTicketResponse {

    private String queueTicketId;
    private int position;
    private long estimatedWaitMs;
    private String status;
    private double progress;
    private String nextUrl;
}
