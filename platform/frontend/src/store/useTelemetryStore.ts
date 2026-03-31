import { create } from 'zustand';
import { TelemetryFeature, BehavioralSensor } from '@/lib/sensor';
import axios from 'axios';

interface TelemetryState {
  sensor: BehavioralSensor;
  features: TelemetryFeature[];
  lastFeature: TelemetryFeature | null;
  addFeature: (feature: TelemetryFeature) => void;
  sendTelemetry: (feature: TelemetryFeature) => Promise<void>;
}

export const useTelemetryStore = create<TelemetryState>((set, get) => ({
  sensor: new BehavioralSensor(),
  features: [],
  lastFeature: null,
  addFeature: (feature) => set((state) => ({ 
    features: [...state.features, feature],
    lastFeature: feature 
  })),
  sendTelemetry: async (feature) => {
    try {
      await axios.post('http://localhost:8080/api/telemetry', feature);
    } catch (error) {
      console.error('Failed to send telemetry:', error);
    }
  }
}));
