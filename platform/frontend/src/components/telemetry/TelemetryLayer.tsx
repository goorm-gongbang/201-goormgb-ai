'use client';

import { useEffect, useRef } from 'react';

import { API_PATHS, HTTP_HEADERS, SESSION_STORAGE_KEYS, STORAGE_KEYS } from '@/contracts/http';
import { TELEMETRY_TRIGGERS, type TelemetryTrigger } from '@/contracts/telemetry';
import { BehavioralSensor, type TelemetryFeature, type TelemetrySample } from '@/lib/sensor';

function getSessionId(): string {
  if (typeof window === 'undefined') return 'ssr';
  let sid = localStorage.getItem(STORAGE_KEYS.TM_SESSION_ID);
  if (!sid) {
    sid = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEYS.TM_SESSION_ID, sid);
  }
  return sid;
}

function getCorrelationId(): string {
  if (typeof window === 'undefined') return '';
  return sessionStorage.getItem(SESSION_STORAGE_KEYS.CORRELATION_ID) || '';
}

function shouldCaptureRawTrajectory(): boolean {
  if (typeof window === 'undefined') return false;
  return localStorage.getItem(STORAGE_KEYS.TM_CAPTURE_RAW_TRAJ) === '1';
}

function getTrajectoryDatasetId(): string {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem(STORAGE_KEYS.TM_TRAJ_DATASET_ID) || '';
}

async function sendBehavior(sample: TelemetrySample, trigger: TelemetryTrigger): Promise<void> {
  try {
    const datasetId = sample.points && sample.points.length > 0 ? getTrajectoryDatasetId() : '';
    await fetch(API_PATHS.TELEMETRY_BEHAVIOR, {
      method: 'POST',
      headers: { [HTTP_HEADERS.CONTENT_TYPE]: HTTP_HEADERS.APPLICATION_JSON },
      body: JSON.stringify({
        sessionId: getSessionId(),
        correlationId: getCorrelationId(),
        trigger,
        datasetId,
        features: sample.features satisfies TelemetryFeature,
        points: sample.points,
      }),
      // For beforeunload-like situations.
      keepalive: true,
    });
  } catch {
    // Best-effort: telemetry must never break UX.
  }
}

export default function TelemetryLayer(): null {
  const sensorRef = useRef<BehavioralSensor>(new BehavioralSensor());
  const collectingRef = useRef<boolean>(false);
  const captureRawRef = useRef<boolean>(false);

  useEffect(() => {
    const sensor = sensorRef.current;

    const onPointerDown = (e: PointerEvent) => {
      // Track mouse only to avoid noise from touch/pen.
      if (e.pointerType && e.pointerType !== 'mouse') return;
      if (typeof e.button === 'number' && e.button !== 0) return;
      // Stop the "pre-click movement" segment and send it before the click handler runs.
      // This makes the backend gating decision more likely to see the telemetry in time.
      if (!collectingRef.current) return;
      collectingRef.current = false;
      const sample = sensor.stop(e.timeStamp);
      void sendBehavior(sample, TELEMETRY_TRIGGERS.CLICK);
    };

    const onPointerMove = (e: PointerEvent) => {
      if (e.pointerType && e.pointerType !== 'mouse') return;

      // Only track pre-click movement (ignore drags).
      if (typeof e.buttons === 'number' && e.buttons !== 0) return;

      // Process coalesced events to avoid losing fine-grained movement (important for synthetic inputs).
      const events = typeof e.getCoalescedEvents === 'function' ? e.getCoalescedEvents() : [e];
      for (const evt of events) {
        if (!collectingRef.current) {
          collectingRef.current = true;
          captureRawRef.current = shouldCaptureRawTrajectory();
          sensor.start(evt.clientX, evt.clientY, evt.timeStamp, captureRawRef.current);
          continue;
        }
        sensor.update(evt.clientX, evt.clientY, evt.timeStamp);
      }
    };

    const stopAndSend = (trigger: TelemetryTrigger) => {
      if (!collectingRef.current) return;
      collectingRef.current = false;
      const sample = sensor.stop(performance.now());
      void sendBehavior(sample, trigger);
    };

    const onPointerCancel = () => stopAndSend(TELEMETRY_TRIGGERS.CANCEL);

    const onKeyDown = (e: KeyboardEvent) => {
      sensor.onKeyDown(e.key, e.code, e.timeStamp, e.repeat);
    };

    const onKeyUp = (e: KeyboardEvent) => {
      sensor.onKeyUp(e.code, e.timeStamp);
    };

    const onPaste = () => {
      sensor.onPaste();
    };

    const onBeforeInput = (e: InputEvent) => {
      if (e.inputType === 'insertFromPaste' || e.inputType === 'insertFromPasteAsQuotation') {
        sensor.onPaste();
      }
    };

    const onCompositionStart = () => {
      sensor.onCompositionStart();
    };

    // Capture phase to observe events regardless of component structure.
    window.addEventListener('pointerdown', onPointerDown, true);
    window.addEventListener('pointermove', onPointerMove, true);
    window.addEventListener('pointercancel', onPointerCancel, true);
    window.addEventListener('keydown', onKeyDown, true);
    window.addEventListener('keyup', onKeyUp, true);
    document.addEventListener('paste', onPaste, true);
    document.addEventListener('beforeinput', onBeforeInput, true);
    document.addEventListener('compositionstart', onCompositionStart, true);

    return () => {
      window.removeEventListener('pointerdown', onPointerDown, true);
      window.removeEventListener('pointermove', onPointerMove, true);
      window.removeEventListener('pointercancel', onPointerCancel, true);
      window.removeEventListener('keydown', onKeyDown, true);
      window.removeEventListener('keyup', onKeyUp, true);
      document.removeEventListener('paste', onPaste, true);
      document.removeEventListener('beforeinput', onBeforeInput, true);
      document.removeEventListener('compositionstart', onCompositionStart, true);
    };
  }, []);

  return null;
}
