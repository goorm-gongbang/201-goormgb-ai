// ─── Domain Types (matching Stage 1 SSOT dataModels) ───

export type SaleStatus = 'ON_SALE' | 'SOLD_OUT' | 'CLOSED';

export interface Team {
  name: string;
  logo: string;
}

export interface Venue {
  name: string;
  location: string;
}

export interface PriceItem {
  grade: string;
  price: number;
  color: string;
}

export interface GameDetail {
  gameId: string;
  homeTeam: Team;
  awayTeam: Team;
  dateTime: string; // ISO 8601
  venue: Venue;
  saleStatus: SaleStatus;
  dDay: number;
  priceTable: PriceItem[];
}

export interface PriceRange {
  min: number;
  max: number;
}

export interface Preferences {
  recommendEnabled: boolean;
  partySize: number;
  priceFilterEnabled: boolean;
  priceRange: PriceRange;
}

export interface BookingRequest {
  sessionId: string;
  gameId: string;
  preferences: Preferences;
}

export interface BookingResponse {
  queueTicketId: string;
  nextUrl: string;
}

// ─── Default Values (matching SSOT defaults) ───

export const DEFAULT_PREFERENCES: Preferences = {
  recommendEnabled: false,
  partySize: 2,
  priceFilterEnabled: false,
  priceRange: { min: 20000, max: 100000 },
};
