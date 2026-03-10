export const TELEMETRY_TRIGGERS = {
  CLICK: 'click',
  CANCEL: 'cancel',
} as const;

export type TelemetryTrigger = (typeof TELEMETRY_TRIGGERS)[keyof typeof TELEMETRY_TRIGGERS];

