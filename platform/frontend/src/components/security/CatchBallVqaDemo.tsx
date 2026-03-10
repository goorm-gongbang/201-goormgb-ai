'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type Phase =
  | 'INSTRUCTION'
  | 'COUNTDOWN'
  | 'ACTIVE_PLAY'
  | 'PASSED_WAIT'
  | 'SUCCESS'
  | 'FAIL'
  | 'BLOCKED';

type CountdownLabel = 'READY' | 'GO';

type Point = {
  x: number;
  y: number;
  t: number;
};

type TelemetryPayload = {
  challenge_id: string;
  session_id: string;
  variant_id: string;
  policy_version: string;
  issued_at: number;
  start_at: number | null;
  result: 'SUCCESS' | 'FAIL' | 'BLOCKED' | 'PASSED_WAIT' | 'PENDING';
  fail_reason: 'POSITION' | 'TIMING' | 'TIMEOUT' | 'RETRY_EXHAUSTED' | null;
  position_ok: boolean;
  timing_ok: boolean;
  distance_to_target: number | null;
  click_offset_ms: number | null;
  attempts_used: number;
  retry_limit: number;
  drag: {
    drag_start_ts: number | null;
    drag_end_ts: number | null;
    drag_path: Point[];
    total_distance: number;
    linear_distance: number;
    curvature: number;
    overshoot_count: number;
    correction_count: number;
    hold_before_click_ms: number | null;
  };
  timing: {
    indicator_enter_ts: number | null;
    indicator_exit_ts: number | null;
    click_ts: number | null;
  };
  position: {
    final_glove_center: { x: number; y: number };
    ball_landing_point: { x: number; y: number };
    catch_radius: number;
  };
  queue: {
    queue_rank: number;
    queue_exit_at: number;
    release_at: number;
    vqa_passed_at: number | null;
    released_for_booking: boolean;
  };
  client: {
    webdriver: boolean;
    user_agent: string;
    plugins_count: number;
    plugins_class: string;
    webdriver_own_descriptor: boolean;
  };
};

const CFG = {
  boardWidth: 980,
  boardHeight: 560,
  playWidth: 710,
  playHeight: 460,
  readyDurationMs: 1000,
  goDurationMs: 1000,
  goToPitchDelayMs: 250,
  activePlayDurationMs: 3000,
  pitchDurationMs: 1300,
  indicatorDurationMs: 1600,
  timingWindowMs: 260,
  timingTargetJitterMs: 0,
  timingAlignOffsetMs: 40,
  queueReleaseDelayMs: 8000,
  catchRadius: 38,
  safetyMargin: 18,
  retryLimit: 1,
  sampleEveryMs: 20,
  policyVersion: 'vqa-catch-ball-v1-demo',
};

const STRIKE_ZONE = {
  x: 260,
  y: 152,
  width: 150,
  height: 170,
};

const MOVEMENT_ZONE = {
  x: STRIKE_ZONE.x - (CFG.catchRadius + CFG.safetyMargin),
  y: STRIKE_ZONE.y - (CFG.catchRadius + CFG.safetyMargin),
  width: STRIKE_ZONE.width + (CFG.catchRadius + CFG.safetyMargin) * 2,
  height: STRIKE_ZONE.height + (CFG.catchRadius + CFG.safetyMargin) * 2,
};

const INDICATOR_TRACK = {
  x: 42,
  y: 18,
  width: 620,
  height: 22,
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function rand(min: number, max: number): number {
  return Math.random() * (max - min) + min;
}

function makeId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function makeLandingPoint(): { x: number; y: number } {
  const baseX = rand(STRIKE_ZONE.x + 12, STRIKE_ZONE.x + STRIKE_ZONE.width - 12);
  const baseY = rand(STRIKE_ZONE.y + 12, STRIKE_ZONE.y + STRIKE_ZONE.height - 12);

  return {
    x: clamp(baseX + rand(-6, 6), STRIKE_ZONE.x + 10, STRIKE_ZONE.x + STRIKE_ZONE.width - 10),
    y: clamp(baseY + rand(-6, 6), STRIKE_ZONE.y + 10, STRIKE_ZONE.y + STRIKE_ZONE.height - 10),
  };
}

function makeTimingWindowStartMs(): number {
  // Align success window center around ball landing time (with small jitter),
  // and keep enough track tail so the indicator does not feel too early.
  const targetMs =
    CFG.pitchDurationMs + CFG.timingAlignOffsetMs + rand(-CFG.timingTargetJitterMs, CFG.timingTargetJitterMs);
  const minStart = 90;
  const maxStart = CFG.indicatorDurationMs - CFG.timingWindowMs - 10;
  const start = targetMs - CFG.timingWindowMs / 2;
  return Math.floor(clamp(start, minStart, maxStart));
}

function initialGlovePosition(): { x: number; y: number } {
  // Start from far bottom-right so the user must actively drag into target area.
  return {
    x: MOVEMENT_ZONE.x + MOVEMENT_ZONE.width - 24,
    y: MOVEMENT_ZONE.y + MOVEMENT_ZONE.height - 26,
  };
}

function toOneDigit(value: number): number {
  return Math.round(value * 10) / 10;
}

function calcPathMetrics(path: Point[], target: { x: number; y: number }): {
  totalDistance: number;
  linearDistance: number;
  curvature: number;
  overshootCount: number;
  correctionCount: number;
} {
  if (path.length < 2) {
    return {
      totalDistance: 0,
      linearDistance: 0,
      curvature: 0,
      overshootCount: 0,
      correctionCount: 0,
    };
  }

  let totalDistance = 0;
  const distancesToTarget: number[] = [];
  let correctionCount = 0;

  for (let i = 1; i < path.length; i += 1) {
    const prev = path[i - 1];
    const current = path[i];
    const dx = current.x - prev.x;
    const dy = current.y - prev.y;
    totalDistance += Math.hypot(dx, dy);

    if (i >= 2) {
      const before = path[i - 2];
      const prevDx = prev.x - before.x;
      const prevDy = prev.y - before.y;
      const turnDot = prevDx * dx + prevDy * dy;
      if (turnDot < 0) correctionCount += 1;
    }
  }

  for (const p of path) {
    distancesToTarget.push(Math.hypot(p.x - target.x, p.y - target.y));
  }

  let overshootCount = 0;
  for (let i = 2; i < distancesToTarget.length; i += 1) {
    const d0 = distancesToTarget[i - 2];
    const d1 = distancesToTarget[i - 1];
    const d2 = distancesToTarget[i];
    if (d1 < d0 && d2 > d1) overshootCount += 1;
  }

  const first = path[0];
  const last = path[path.length - 1];
  const linearDistance = Math.hypot(last.x - first.x, last.y - first.y);
  const curvature = linearDistance <= 0.01 ? 0 : totalDistance / linearDistance;

  return {
    totalDistance: toOneDigit(totalDistance),
    linearDistance: toOneDigit(linearDistance),
    curvature: toOneDigit(curvature),
    overshootCount,
    correctionCount,
  };
}

type CatchBallVqaDemoProps = {
  embedded?: boolean;
  challengeId?: string;
  sessionId?: string;
  issuedAt?: number;
  onSuccess?: (telemetry: TelemetryPayload) => void | Promise<void>;
  onBlocked?: (telemetry: TelemetryPayload) => void | Promise<void>;
};

export default function CatchBallVqaDemo({
  embedded = false,
  challengeId: challengeIdProp,
  sessionId: sessionIdProp,
  issuedAt: issuedAtProp,
  onSuccess,
  onBlocked,
}: CatchBallVqaDemoProps = {}) {
  const [phase, setPhase] = useState<Phase>('INSTRUCTION');
  const [statusMessage, setStatusMessage] = useState('Start를 누르면 챌린지가 시작됩니다.');
  const [attempt, setAttempt] = useState(0);

  const [challengeId] = useState(() => challengeIdProp ?? makeId('CH'));
  const [sessionId] = useState(() => sessionIdProp ?? makeId('SESS'));
  const [issuedAt] = useState(() => issuedAtProp ?? Date.now());
  const [queueRank] = useState(() => Math.floor(rand(200, 12000)));
  const [queueExitAtMs, setQueueExitAtMs] = useState(() => Date.now());
  const [releaseAtMs, setReleaseAtMs] = useState(() => Date.now() + CFG.queueReleaseDelayMs);
  const [vqaPassedAtMs, setVqaPassedAtMs] = useState<number | null>(null);

  const [countdownStartMs, setCountdownStartMs] = useState<number | null>(null);
  const [activeStartMs, setActiveStartMs] = useState<number | null>(null);
  const [pitchStartMs, setPitchStartMs] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState<number>(() => Date.now());

  const [landingPoint, setLandingPoint] = useState<{ x: number; y: number }>(makeLandingPoint);
  const [timingWindowStartMs, setTimingWindowStartMs] = useState<number>(makeTimingWindowStartMs);

  const [glove, setGlove] = useState<{ x: number; y: number }>(initialGlovePosition);
  const [dragPath, setDragPath] = useState<Point[]>([]);
  const [dragStartTs, setDragStartTs] = useState<number | null>(null);
  const [dragEndTs, setDragEndTs] = useState<number | null>(null);

  const [positionOk, setPositionOk] = useState(false);
  const [timingOk, setTimingOk] = useState(false);
  const [distanceToTarget, setDistanceToTarget] = useState<number | null>(null);
  const [clickTs, setClickTs] = useState<number | null>(null);
  const [clickOffsetMs, setClickOffsetMs] = useState<number | null>(null);
  const [failReason, setFailReason] = useState<TelemetryPayload['fail_reason']>(null);

  const [variantId, setVariantId] = useState<string>(() => makeId('VAR'));
  const clientSignals = useMemo(() => {
    if (typeof navigator === 'undefined') {
      return {
        webdriver: false,
        user_agent: '',
        plugins_count: -1,
        plugins_class: '',
        webdriver_own_descriptor: false,
      };
    }
    const pluginsCount = navigator.plugins?.length ?? -1;
    const pluginsClass = Object.prototype.toString.call(navigator.plugins);
    const webdriverOwnDescriptor = Boolean(Object.getOwnPropertyDescriptor(navigator, 'webdriver'));
    return {
      webdriver: Boolean(navigator.webdriver),
      user_agent: navigator.userAgent ?? '',
      plugins_count: pluginsCount,
      plugins_class: pluginsClass,
      webdriver_own_descriptor: webdriverOwnDescriptor,
    };
  }, []);

  const playRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);
  const suppressDragReleaseClickRef = useRef(false);
  const pointerDownRef = useRef<{ x: number; y: number } | null>(null);
  const lastSampleTsRef = useRef(0);
  const completionNotifiedRef = useRef<Phase | null>(null);

  const finalize = useCallback(
    (
      resolvedPositionOk: boolean,
      resolvedTimingOk: boolean,
      resolvedDistance: number | null,
      resolvedClickOffset: number | null,
      reason: TelemetryPayload['fail_reason'],
    ): void => {
      setPositionOk(resolvedPositionOk);
      setTimingOk(resolvedTimingOk);
      setDistanceToTarget(resolvedDistance);
      setClickOffsetMs(resolvedClickOffset);
      setFailReason(reason);

      const passed = resolvedPositionOk && resolvedTimingOk;
      if (passed) {
        const passedAt = Date.now();
        setVqaPassedAtMs(passedAt);

        if (passedAt < releaseAtMs) {
          setPhase('PASSED_WAIT');
          setStatusMessage('검증 통과. 대기열 순번 기준 진입 시각까지 대기합니다.');
          return;
        }

        setPhase('SUCCESS');
        setStatusMessage('성공: VQA 통과 및 release_at 충족. 티켓팅 플로우로 진행됩니다.');
        return;
      }

      if (attempt < CFG.retryLimit) {
        setPhase('FAIL');
        setStatusMessage('실패: 한 번 더 재시도할 수 있습니다.');
        return;
      }

      setPhase('BLOCKED');
      setStatusMessage('실패: 재시도 한도를 초과하여 차단 상태입니다.');
      setFailReason('RETRY_EXHAUSTED');
    },
    [attempt, releaseAtMs],
  );

  useEffect(() => {
    if (phase !== 'COUNTDOWN' && phase !== 'ACTIVE_PLAY' && phase !== 'PASSED_WAIT') return;
    const tick = window.setInterval(() => setNowMs(Date.now()), 16);
    return () => window.clearInterval(tick);
  }, [phase]);

  useEffect(() => {
    if (phase !== 'COUNTDOWN' || !countdownStartMs) return;
    const finishAt = countdownStartMs + CFG.readyDurationMs + CFG.goDurationMs;
    const delay = Math.max(0, finishAt - Date.now());

    const timer = window.setTimeout(() => {
      const activeStart = Date.now();
      setPhase('ACTIVE_PLAY');
      setActiveStartMs(activeStart);
      setPitchStartMs(activeStart + CFG.goToPitchDelayMs);
      setStatusMessage('글러브를 공 예상 지점으로 이동하고, 빨간 타이밍에 글러브를 클릭하세요.');
      setNowMs(activeStart);
    }, delay);

    return () => window.clearTimeout(timer);
  }, [phase, countdownStartMs]);

  useEffect(() => {
    if (phase !== 'ACTIVE_PLAY' || !activeStartMs) return;
    const finishAt = activeStartMs + CFG.activePlayDurationMs;
    const delay = Math.max(0, finishAt - Date.now());

    const timer = window.setTimeout(() => {
      finalize(false, false, null, null, 'TIMEOUT');
    }, delay);

    return () => window.clearTimeout(timer);
  }, [phase, activeStartMs, finalize]);

  useEffect(() => {
    if (phase !== 'PASSED_WAIT') return;
    const delay = Math.max(0, releaseAtMs - Date.now());
    const timer = window.setTimeout(() => {
      setPhase('SUCCESS');
      setStatusMessage('release_at 도달. 티켓팅 플로우로 진행됩니다.');
    }, delay);
    return () => window.clearTimeout(timer);
  }, [phase, releaseAtMs]);

  const countdownLabel: CountdownLabel | null = useMemo(() => {
    if (phase !== 'COUNTDOWN' || !countdownStartMs) return null;
    const elapsed = nowMs - countdownStartMs;
    return elapsed < CFG.readyDurationMs ? 'READY' : 'GO';
  }, [phase, countdownStartMs, nowMs]);

  const indicatorProgress = useMemo(() => {
    if (!pitchStartMs) return 0;
    const elapsed = nowMs - pitchStartMs;
    if (elapsed <= 0) return 0;
    return clamp(elapsed / CFG.indicatorDurationMs, 0, 1);
  }, [nowMs, pitchStartMs]);

  const ballProgress = useMemo(() => {
    if (!pitchStartMs) return 0;
    const elapsed = nowMs - pitchStartMs;
    if (elapsed <= 0) return 0;
    return clamp(elapsed / CFG.pitchDurationMs, 0, 1);
  }, [nowMs, pitchStartMs]);

  const indicatorX = INDICATOR_TRACK.x + indicatorProgress * INDICATOR_TRACK.width;
  const timingWindowStartX =
    INDICATOR_TRACK.x + (timingWindowStartMs / CFG.indicatorDurationMs) * INDICATOR_TRACK.width;
  const timingWindowWidth = (CFG.timingWindowMs / CFG.indicatorDurationMs) * INDICATOR_TRACK.width;

  const pitcher = { x: 346, y: 132 };
  const ballArc = Math.sin(ballProgress * Math.PI) * 92;
  const ballPos = {
    x: pitcher.x + (landingPoint.x - pitcher.x) * ballProgress,
    y: pitcher.y + (landingPoint.y - pitcher.y) * ballProgress - ballArc,
  };
  const ballDiameter = 12 + 20 * Math.pow(ballProgress, 1.45);
  const ballGroundY = pitcher.y + (landingPoint.y - pitcher.y) * ballProgress + 14;
  const ballShadowW = ballDiameter * (0.9 + ballProgress * 0.65);
  const ballShadowH = ballDiameter * (0.32 + ballProgress * 0.2);
  const ballShadowOpacity = 0.12 + ballProgress * 0.25;

  const telemetry = useMemo<TelemetryPayload>(() => {
    const metrics = calcPathMetrics(dragPath, landingPoint);
    const result: TelemetryPayload['result'] =
      phase === 'SUCCESS'
        ? 'SUCCESS'
        : phase === 'PASSED_WAIT'
          ? 'PASSED_WAIT'
        : phase === 'BLOCKED'
          ? 'BLOCKED'
          : phase === 'FAIL'
            ? 'FAIL'
            : 'PENDING';

    return {
      challenge_id: challengeId,
      session_id: sessionId,
      variant_id: variantId,
      policy_version: CFG.policyVersion,
      issued_at: issuedAt,
      start_at: activeStartMs,
      result,
      fail_reason: failReason,
      position_ok: positionOk,
      timing_ok: timingOk,
      distance_to_target: distanceToTarget,
      click_offset_ms: clickOffsetMs,
      attempts_used: attempt + (phase === 'SUCCESS' || phase === 'FAIL' || phase === 'BLOCKED' ? 1 : 0),
      retry_limit: CFG.retryLimit,
      drag: {
        drag_start_ts: dragStartTs,
        drag_end_ts: dragEndTs,
        drag_path: dragPath,
        total_distance: metrics.totalDistance,
        linear_distance: metrics.linearDistance,
        curvature: metrics.curvature,
        overshoot_count: metrics.overshootCount,
        correction_count: metrics.correctionCount,
        hold_before_click_ms: dragEndTs && clickTs ? Math.max(0, clickTs - dragEndTs) : null,
      },
      timing: {
        indicator_enter_ts: pitchStartMs ? pitchStartMs + timingWindowStartMs : null,
        indicator_exit_ts: pitchStartMs ? pitchStartMs + timingWindowStartMs + CFG.timingWindowMs : null,
        click_ts: clickTs,
      },
      position: {
        final_glove_center: glove,
        ball_landing_point: landingPoint,
        catch_radius: CFG.catchRadius,
      },
      queue: {
        queue_rank: queueRank,
        queue_exit_at: queueExitAtMs,
        release_at: releaseAtMs,
        vqa_passed_at: vqaPassedAtMs,
        released_for_booking: nowMs >= releaseAtMs,
      },
      client: clientSignals,
    };
  }, [
    activeStartMs,
    attempt,
    challengeId,
    clickOffsetMs,
    clickTs,
    distanceToTarget,
    dragEndTs,
    dragPath,
    dragStartTs,
    failReason,
    glove,
    issuedAt,
    landingPoint,
    phase,
    pitchStartMs,
    positionOk,
    sessionId,
    timingOk,
    timingWindowStartMs,
    variantId,
    queueRank,
    queueExitAtMs,
    releaseAtMs,
    vqaPassedAtMs,
    nowMs,
    clientSignals,
  ]);

  useEffect(() => {
    if (phase === completionNotifiedRef.current) return;
    if (phase === 'SUCCESS') {
      completionNotifiedRef.current = phase;
      void onSuccess?.(telemetry);
    } else if (phase === 'BLOCKED') {
      completionNotifiedRef.current = phase;
      void onBlocked?.(telemetry);
    }
  }, [phase, onSuccess, onBlocked, telemetry]);

  function resetRound(nextAttempt: number): void {
    setPhase('INSTRUCTION');
    setStatusMessage('Start를 누르면 챌린지가 시작됩니다.');

    setCountdownStartMs(null);
    setActiveStartMs(null);
    setPitchStartMs(null);
    setNowMs(Date.now());
    const queueExitTs = Date.now();
    setQueueExitAtMs(queueExitTs);
    setReleaseAtMs(queueExitTs + CFG.queueReleaseDelayMs);
    setVqaPassedAtMs(null);

    setLandingPoint(makeLandingPoint());
    setTimingWindowStartMs(makeTimingWindowStartMs());
    setVariantId(makeId('VAR'));
    completionNotifiedRef.current = null;

    setGlove(initialGlovePosition());
    setDragPath([]);
    setDragStartTs(null);
    setDragEndTs(null);
    draggingRef.current = false;
    suppressDragReleaseClickRef.current = false;
    pointerDownRef.current = null;
    lastSampleTsRef.current = 0;

    setPositionOk(false);
    setTimingOk(false);
    setDistanceToTarget(null);
    setClickTs(null);
    setClickOffsetMs(null);
    setFailReason(null);

    setAttempt(nextAttempt);
  }

  function startChallenge(): void {
    setPhase('COUNTDOWN');
    setCountdownStartMs(Date.now());
    setNowMs(Date.now());
    setStatusMessage('READY... GO...');
  }

  function handlePointerDown(): void {
    if (phase !== 'ACTIVE_PLAY') return;
    draggingRef.current = true;
    suppressDragReleaseClickRef.current = false;
    pointerDownRef.current = { x: glove.x, y: glove.y };

    const ts = Date.now();
    lastSampleTsRef.current = ts;
    if (!dragStartTs) setDragStartTs(ts);
  }

  function handlePointerUp(): void {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    setDragEndTs(Date.now());
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>): void {
    if (phase !== 'ACTIVE_PLAY' || !draggingRef.current || !playRef.current) return;

    const rect = playRef.current.getBoundingClientRect();
    const nextX = clamp(event.clientX - rect.left, MOVEMENT_ZONE.x, MOVEMENT_ZONE.x + MOVEMENT_ZONE.width);
    const nextY = clamp(event.clientY - rect.top, MOVEMENT_ZONE.y, MOVEMENT_ZONE.y + MOVEMENT_ZONE.height);
    const ts = Date.now();
    const down = pointerDownRef.current;
    if (down && Math.hypot(nextX - down.x, nextY - down.y) >= 6) {
      suppressDragReleaseClickRef.current = true;
    }

    setGlove({ x: nextX, y: nextY });

    if (activeStartMs && (lastSampleTsRef.current === 0 || ts - lastSampleTsRef.current >= CFG.sampleEveryMs)) {
      const t = ts - activeStartMs;
      setDragPath((prev) => [...prev, { x: Math.round(nextX), y: Math.round(nextY), t }]);
      lastSampleTsRef.current = ts;
    }
  }

  function evaluateCatchClick(): void {
    if (phase !== 'ACTIVE_PLAY' || !pitchStartMs) return;
    if (suppressDragReleaseClickRef.current) {
      suppressDragReleaseClickRef.current = false;
      return;
    }

    const ts = Date.now();
    setClickTs(ts);

    const distance = Math.hypot(glove.x - landingPoint.x, glove.y - landingPoint.y);
    const resolvedPositionOk = distance <= CFG.catchRadius;

    const elapsedFromPitch = ts - pitchStartMs;
    const timingStart = timingWindowStartMs;
    const timingEnd = timingWindowStartMs + CFG.timingWindowMs;
    const resolvedTimingOk = elapsedFromPitch >= timingStart && elapsedFromPitch <= timingEnd;

    const timingCenter = timingStart + CFG.timingWindowMs / 2;
    const offset = Math.round(elapsedFromPitch - timingCenter);

    let reason: TelemetryPayload['fail_reason'] = null;
    if (!resolvedPositionOk) reason = 'POSITION';
    if (resolvedPositionOk && !resolvedTimingOk) reason = 'TIMING';

    finalize(resolvedPositionOk, resolvedTimingOk, toOneDigit(distance), offset, reason);
  }

  const canRetry = phase === 'FAIL' && attempt < CFG.retryLimit;
  const canRestart = phase === 'SUCCESS';
  const remainingReleaseSec =
    phase === 'PASSED_WAIT' ? Math.max(0, Math.ceil((releaseAtMs - nowMs) / 1000)) : 0;

  const content = (
    <div className="mx-auto max-w-[1080px] space-y-5">
      {!embedded && (
        <header>
          <h1 className="text-2xl font-bold tracking-tight">Catch the Ball VQA Demo</h1>
          <p className="mt-1 text-sm text-slate-400">
            팀 데모 로컬 화면: 공 도착 타이밍과 인디케이터 성공 구간을 동기화한 야구형 VQA.
          </p>
        </header>
      )}

      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
          <div
            className="relative mx-auto rounded-xl border border-slate-700 bg-slate-900"
            style={{ width: CFG.boardWidth, height: CFG.boardHeight }}
          >
            <div className="absolute inset-0 p-4">
              <div className="grid h-full grid-cols-[710px_1fr] gap-4">
                <div
                  ref={playRef}
                  className="relative overflow-hidden rounded-lg border border-slate-700"
                  style={{ width: CFG.playWidth, height: CFG.playHeight }}
                  data-testid="catchball-playfield"
                  onPointerMove={handlePointerMove}
                  onPointerUp={handlePointerUp}
                  onPointerLeave={handlePointerUp}
                >
                  <div className="absolute inset-0 bg-gradient-to-b from-sky-300 via-sky-400 to-sky-500" />

                  <div className="absolute left-[-10%] right-[-10%] top-[8%] h-[190px] rounded-[50%] border border-slate-500/45 bg-gradient-to-b from-slate-500 via-slate-700 to-slate-900 shadow-[inset_0_24px_58px_rgba(255,255,255,0.11)]" />
                  <div className="absolute left-[-11%] right-[-11%] top-[11%] h-[174px] rounded-[50%] border border-slate-500/35 bg-[repeating-linear-gradient(90deg,rgba(203,213,225,0.2)_0_3px,rgba(148,163,184,0.2)_3px_6px,rgba(71,85,105,0.26)_6px_10px)] opacity-95" />
                  <div className="absolute left-[-9%] right-[-9%] top-[14%] h-[158px] rounded-[50%] border border-slate-600/30 bg-[repeating-linear-gradient(90deg,rgba(226,232,240,0.14)_0_2px,rgba(100,116,139,0.24)_2px_7px)]" />
                  <div className="absolute left-[39%] top-[10%] h-[52px] w-[134px] rounded-md border border-slate-200/45 bg-gradient-to-b from-indigo-200/70 to-indigo-500/70 shadow-[0_8px_24px_rgba(15,23,42,0.55)]" />
                  <div className="absolute left-[18%] top-[17%] h-[18px] w-[102px] rounded-sm bg-slate-100/25" />
                  <div className="absolute right-[20%] top-[17%] h-[18px] w-[102px] rounded-sm bg-slate-100/25" />

                  <div
                    className="absolute left-0 right-0 bottom-0 h-[66%]"
                    style={{
                      clipPath: 'polygon(0% 18%, 100% 18%, 82% 100%, 18% 100%)',
                      background: 'linear-gradient(180deg, #5faa5f 0%, #32753d 58%, #1f4f2d 100%)',
                    }}
                  />
                  <div
                    className="absolute bottom-[8%] left-[16%] h-[43%] w-[68%] rounded-[50%] opacity-80"
                    style={{
                      background:
                        'radial-gradient(ellipse at center, rgba(192,145,102,0.95) 0%, rgba(182,129,84,0.9) 58%, rgba(151,104,65,0.8) 100%)',
                    }}
                  />

                  <div
                    className="absolute left-[294px] top-[334px] h-[92px] w-[116px]"
                    style={{
                      clipPath: 'polygon(0% 0%, 100% 0%, 100% 56%, 50% 100%, 0% 56%)',
                      background:
                        'linear-gradient(180deg, #f8fafc 0%, #e2e8f0 62%, #cbd5e1 100%)',
                      boxShadow:
                        'inset 0 3px 0 rgba(255,255,255,0.75), 0 0 0 2px rgba(255,255,255,0.55), 0 10px 16px rgba(15,23,42,0.45)',
                    }}
                  />

                  <div className="absolute left-[330px] top-[82px] h-[150px] w-[86px] opacity-95">
                    <svg viewBox="0 0 86 150" className="h-full w-full">
                      <ellipse cx="44" cy="24" rx="11" ry="13" fill="#f8fafc" />
                      <path d="M28 40 L56 40 L62 92 L24 92 Z" fill="#f1f5f9" />
                      <path d="M56 48 L74 60 L69 70 L56 62 Z" fill="#f1f5f9" />
                      <path d="M28 48 L14 61 L18 69 L30 60 Z" fill="#f1f5f9" />
                      <path d="M24 92 L39 140 L49 140 L62 92 Z" fill="#e2e8f0" />
                      <path d="M39 139 L44 148 L49 139 Z" fill="#0f172a" />
                      <path d="M59 44 L78 19 L81 22 L62 49 Z" fill="#9a6a3d" />
                      <circle cx="61" cy="56" r="3" fill="#dc2626" />
                    </svg>
                  </div>

                  <div className="absolute bottom-[18px] left-[26px] right-[26px] h-[58px] rounded-md border border-slate-600 bg-slate-900/78 backdrop-blur-[1px]">
                    <div
                      className="absolute rounded bg-red-500/75"
                      style={{
                        left: timingWindowStartX,
                        top: INDICATOR_TRACK.y,
                        width: timingWindowWidth,
                        height: INDICATOR_TRACK.height,
                      }}
                      data-testid="catchball-window"
                    />
                    <div
                      className="absolute rounded-full border border-white/60 bg-emerald-300 shadow-[0_0_18px_rgba(52,211,153,0.75)]"
                      style={{ left: indicatorX - 9, top: INDICATOR_TRACK.y - 3, width: 18, height: 18 }}
                      data-testid="catchball-indicator"
                    />
                    <div
                      className="absolute rounded border border-slate-500"
                      style={{
                        left: INDICATOR_TRACK.x,
                        top: INDICATOR_TRACK.y,
                        width: INDICATOR_TRACK.width,
                        height: INDICATOR_TRACK.height,
                      }}
                    />
                  </div>

                  <div
                    className="absolute rounded border-2 border-white/75"
                    style={{ left: STRIKE_ZONE.x, top: STRIKE_ZONE.y, width: STRIKE_ZONE.width, height: STRIKE_ZONE.height }}
                  />

                  <div
                    className="absolute rounded border border-cyan-200/60"
                    style={{
                      left: landingPoint.x - CFG.catchRadius,
                      top: landingPoint.y - CFG.catchRadius,
                      width: CFG.catchRadius * 2,
                      height: CFG.catchRadius * 2,
                    }}
                  />
                  <div
                    className="absolute rounded-full border border-cyan-100 bg-cyan-300/70"
                    style={{ left: landingPoint.x - 10, top: landingPoint.y - 10, width: 20, height: 20 }}
                    data-testid="catchball-landing-marker"
                  />

                  {phase === 'ACTIVE_PLAY' && nowMs >= (pitchStartMs ?? Number.MAX_SAFE_INTEGER) && (
                    <>
                      <div
                        className="absolute rounded-full bg-black/50 blur-[2px]"
                        style={{
                          left: ballPos.x - ballShadowW / 2,
                          top: ballGroundY - ballShadowH / 2,
                          width: ballShadowW,
                          height: ballShadowH,
                          opacity: ballShadowOpacity,
                        }}
                      />
                      <div
                        className="absolute"
                        style={{
                          left: ballPos.x - ballDiameter / 2,
                          top: ballPos.y - ballDiameter / 2,
                          width: ballDiameter,
                          height: ballDiameter,
                          filter: 'drop-shadow(0 6px 8px rgba(15,23,42,0.45))',
                        }}
                      >
                        <svg viewBox="0 0 100 100" className="h-full w-full">
                          <defs>
                            <radialGradient id="baseballGrad" cx="30%" cy="30%" r="70%">
                              <stop offset="0%" stopColor="#ffffff" />
                              <stop offset="55%" stopColor="#f8fafc" />
                              <stop offset="100%" stopColor="#dbe3ef" />
                            </radialGradient>
                          </defs>
                          <circle cx="50" cy="50" r="46" fill="url(#baseballGrad)" stroke="#d7dee9" strokeWidth="3" />
                          <path d="M24 18 C40 36, 40 64, 24 82" stroke="#dc2626" strokeWidth="4" fill="none" strokeLinecap="round" />
                          <path d="M76 18 C60 36, 60 64, 76 82" stroke="#dc2626" strokeWidth="4" fill="none" strokeLinecap="round" />
                          <path d="M28 30 L33 35 M26 42 L31 47 M26 54 L31 59 M28 66 L33 71" stroke="#dc2626" strokeWidth="2.3" strokeLinecap="round" />
                          <path d="M72 30 L67 35 M74 42 L69 47 M74 54 L69 59 M72 66 L67 71" stroke="#dc2626" strokeWidth="2.3" strokeLinecap="round" />
                        </svg>
                      </div>
                    </>
                  )}

                  <button
                    type="button"
                    className="absolute"
                    style={{ left: glove.x - 46, top: glove.y - 34, width: 92, height: 68 }}
                    onPointerDown={handlePointerDown}
                    onClick={evaluateCatchClick}
                    aria-label="glove catch"
                    data-testid="catchball-glove"
                  >
                    <svg viewBox="0 0 92 68" className="h-full w-full drop-shadow-[0_7px_10px_rgba(0,0,0,0.45)]">
                      <path
                        d="M10 58 C8 40, 13 22, 26 13 C34 8, 43 8, 50 11 C57 8, 67 9, 74 15 C84 24, 86 40, 83 57 C76 60, 67 61, 58 60 C53 58, 47 58, 42 60 C31 61, 20 61, 10 58 Z"
                        fill="url(#gloveFill)"
                        stroke="#7c4a23"
                        strokeWidth="2.2"
                      />
                      <path d="M36 18 L27 48 M45 16 L42 50 M55 16 L58 49 M66 19 L72 46" stroke="#8b5a2b" strokeWidth="2" strokeLinecap="round" />
                      <path d="M15 43 C25 47, 33 47, 40 44" stroke="#5b3718" strokeWidth="2.2" strokeLinecap="round" />
                      <defs>
                        <linearGradient id="gloveFill" x1="0%" y1="0%" x2="100%" y2="100%">
                          <stop offset="0%" stopColor="#f4bf72" />
                          <stop offset="52%" stopColor="#d7924a" />
                          <stop offset="100%" stopColor="#b67135" />
                        </linearGradient>
                      </defs>
                    </svg>
                  </button>

                  {(phase === 'INSTRUCTION' || phase === 'COUNTDOWN') && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/50 backdrop-blur-[2px]">
                      {phase === 'INSTRUCTION' && (
                        <div className="w-[420px] rounded-xl border border-slate-500 bg-slate-900/95 p-6 text-center">
                          <h2 className="text-2xl font-bold">VQA Challenge</h2>
                          <p className="mt-3 text-left text-sm leading-6 text-slate-300">
                            1. 공의 도착 위치로 글러브를 이동합니다.<br />
                            2. 하단 바의 빨간 영역 타이밍에 글러브를 클릭하면 성공입니다.
                          </p>
                          <button
                            type="button"
                            className="mt-5 h-14 w-14 rounded-full border-2 border-rose-200 bg-rose-300 text-xl font-bold text-rose-900"
                            onClick={startChallenge}
                            data-testid="catchball-start"
                          >
                            Start
                          </button>
                        </div>
                      )}

                      {phase === 'COUNTDOWN' && (
                        <div className="text-center">
                          <p
                            className={`text-7xl font-black tracking-wide ${countdownLabel === 'READY' ? 'text-cyan-200' : 'text-rose-200'}`}
                          >
                            {countdownLabel}
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {(phase === 'PASSED_WAIT' || phase === 'SUCCESS' || phase === 'FAIL' || phase === 'BLOCKED') && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/55 backdrop-blur-[2px]">
                      <div className="w-[460px] rounded-xl border border-slate-500 bg-slate-900/95 p-6 text-center">
                        <h3
                          className={`text-2xl font-bold ${phase === 'SUCCESS' ? 'text-emerald-300' : phase === 'PASSED_WAIT' ? 'text-cyan-300' : phase === 'BLOCKED' ? 'text-red-300' : 'text-amber-300'}`}
                        >
                          {phase === 'SUCCESS'
                            ? 'SUCCESS'
                            : phase === 'PASSED_WAIT'
                              ? 'PASSED'
                              : phase === 'BLOCKED'
                                ? 'BLOCKED'
                                : 'FAIL'}
                        </h3>
                        <p className="mt-3 text-sm text-slate-300">{statusMessage}</p>
                        {phase === 'PASSED_WAIT' && (
                          <p className="mt-2 text-xs text-slate-400">
                            형평성 보호: 모든 사용자는 release_at 이후에만 다음 단계 진입 가능 (남은 시간 {remainingReleaseSec}s)
                          </p>
                        )}

                        <div className="mt-5 flex items-center justify-center gap-3">
                          {canRetry && (
                            <button
                              type="button"
                              onClick={() => resetRound(attempt + 1)}
                              className="rounded-lg bg-amber-400 px-4 py-2 text-sm font-semibold text-black"
                              data-testid="catchball-retry"
                            >
                              Retry
                            </button>
                          )}
                          {canRestart && (
                            <button
                              type="button"
                              onClick={() => resetRound(0)}
                              className="rounded-lg border border-slate-500 px-4 py-2 text-sm"
                            >
                              Restart
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                <aside className="rounded-lg border border-slate-700 bg-slate-900/90 p-4">
                  <div className="rounded-md bg-slate-700 px-3 py-2 text-center text-sm font-semibold">설명판</div>
                  <div className="mt-4 space-y-3 text-sm text-slate-300">
                    <p>1. 우측 글러브를 공 예상 위치로 이동</p>
                    <p>2. 하단 인디케이터 빨간 구간에서 글러브 클릭</p>
                    <p>3. 위치 + 타이밍 동시 만족 시 통과</p>
                  </div>

                  <div className="mt-4 space-y-2 rounded-md border border-slate-700 bg-slate-950/70 p-3 text-xs text-slate-400">
                    <p>
                      Phase: <span className="text-slate-100">{phase}</span>
                    </p>
                    <p>
                      Attempt: <span className="text-slate-100">{attempt + 1}/{CFG.retryLimit + 1}</span>
                    </p>
                    <p>
                      Status: <span className="text-slate-100">{statusMessage}</span>
                    </p>
                    <p>
                      Queue Rank: <span className="text-slate-100">{queueRank}</span>
                    </p>
                    <p>
                      release_at: <span className="text-slate-100">{new Date(releaseAtMs).toLocaleTimeString()}</span>
                    </p>
                    <p>
                      release gate: <span className="text-slate-100">{nowMs >= releaseAtMs ? 'OPEN' : 'WAIT'}</span>
                    </p>
                    <p>
                      Landing: <span className="text-slate-100">({Math.round(landingPoint.x)}, {Math.round(landingPoint.y)})</span>
                    </p>
                    <p>
                      Glove: <span className="text-slate-100">({Math.round(glove.x)}, {Math.round(glove.y)})</span>
                    </p>
                    <p>
                      Distance: <span className="text-slate-100">{distanceToTarget ?? '-'}</span>
                    </p>
                    <p>
                      Timing Offset: <span className="text-slate-100">{clickOffsetMs ?? '-'}</span>
                    </p>
                  </div>
                </aside>
              </div>
            </div>
          </div>
      </section>

      {!embedded && (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
          <h2 className="text-sm font-semibold">Telemetry Preview (Demo)</h2>
          <p className="mt-1 text-xs text-slate-400">팀 공유용 확인 패널이며, 현재는 서버 전송 없이 로컬 렌더링만 수행합니다.</p>
          <pre className="mt-3 max-h-[360px] overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-3 text-[11px] leading-4 whitespace-pre-wrap break-all">
{JSON.stringify(telemetry, null, 2)}
          </pre>
        </section>
      )}
    </div>
  );

  if (embedded) {
    return <div className="text-slate-100">{content}</div>;
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 py-8 px-6">
      {content}
    </div>
  );
}
