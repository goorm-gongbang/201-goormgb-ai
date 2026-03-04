package com.trafficmaster.exception;

import com.trafficmaster.contract.ReasonCodes;

import lombok.Getter;

/**
 * Stage 7: Standard exception with reasonCode for all Traffic-Master failures.
 * Conforms to Addendum §6 reasonCode standardization.
 */
@Getter
public class TrafficMasterException extends RuntimeException {

    private final String reasonCode;
    private final int httpStatus;

    public TrafficMasterException(String reasonCode, String message) {
        super(message);
        this.reasonCode = reasonCode;
        this.httpStatus = 400;
    }

    public TrafficMasterException(String reasonCode, String message, int httpStatus) {
        super(message);
        this.reasonCode = reasonCode;
        this.httpStatus = httpStatus;
    }

    // Common factory methods per §6
    public static TrafficMasterException heldByOthers() {
        return new TrafficMasterException(ReasonCodes.HELD_BY_OTHERS, "선택한 좌석이 이미 다른 사용자에 의해 선점되었습니다.", 409);
    }

    public static TrafficMasterException expired() {
        return new TrafficMasterException(ReasonCodes.EXPIRED, "세션 또는 결제 시간이 만료되었습니다.", 410);
    }

    public static TrafficMasterException blocked() {
        return new TrafficMasterException(ReasonCodes.BLOCKED, "보안 정책에 의해 차단되었습니다.", 403);
    }

    public static TrafficMasterException challengeRequired() {
        return new TrafficMasterException(ReasonCodes.CHALLENGE_REQUIRED, "보안 검증이 필요합니다.", 428); // 428 Precondition Required
    }

    public static TrafficMasterException paymentFailed(String detail) {
        return new TrafficMasterException(ReasonCodes.PAYMENT_FAILED, "결제 처리에 실패했습니다: " + detail, 502);
    }

    public static TrafficMasterException invalidHold() {
        return new TrafficMasterException(ReasonCodes.INVALID_HOLD, "유효하지 않은 홀드입니다.", 400);
    }

    public static TrafficMasterException notFound(String entity) {
        return new TrafficMasterException(ReasonCodes.NOT_FOUND, entity + "을 찾을 수 없습니다.", 404);
    }
}
