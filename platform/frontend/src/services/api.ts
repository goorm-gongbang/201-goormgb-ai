import axios from 'axios';
import type { BookingRequest, BookingResponse, GameDetail, Preferences } from '@/types';

// ─── Session ID Management (SSOT: TM_SESSION_ID in LocalStorage) ───

const SESSION_STORAGE_KEY = 'TM_SESSION_ID';

export function getOrCreateSessionId(): string {
  if (typeof window === 'undefined') return '';

  let sessionId = localStorage.getItem(SESSION_STORAGE_KEY);
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  }
  return sessionId;
}

// ─── Axios Instance (all requests carry X-Session-Id header) ───

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const sessionId = getOrCreateSessionId();
  if (sessionId) {
    config.headers['X-Session-Id'] = sessionId;
  }
  return config;
});

// ─── API Functions (Stage 1 SSOT endpoints) ───

export async function getGame(gameId: string): Promise<GameDetail> {
  const { data } = await api.get<GameDetail>(`/games/${gameId}`);
  return data;
}

export async function getPreferences(sessionId: string): Promise<Preferences> {
  const { data } = await api.get<Preferences>(`/sessions/${sessionId}/preferences`);
  return data;
}

export async function postPreferences(sessionId: string, prefs: Preferences): Promise<Preferences> {
  const { data } = await api.post<Preferences>(`/sessions/${sessionId}/preferences`, prefs);
  return data;
}

export async function postBookingEntry(request: BookingRequest): Promise<BookingResponse> {
  const { data } = await api.post<BookingResponse>('/booking/entry', request);
  return data;
}

// ─── Stage 2: Queue API ───

export interface QueueEnterRequest {
  sessionId: string;
  gameId: string;
  mode: string;
}

export interface QueueTicketResponse {
  queueTicketId: string;
  position: number;
  estimatedWaitMs: number;
  status: string;
  progress: number;
  nextUrl?: string;
}

export async function postQueueEnter(request: QueueEnterRequest): Promise<QueueTicketResponse> {
  const { data } = await api.post<QueueTicketResponse>('/queue/enter', request);
  return data;
}

export default api;
