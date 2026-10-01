export type Money = number; // minor units (kopecks/cents)

export interface ServiceOffer {
  resource_id: number;
  price_minor: Money;
  duration_min: number;
}

export interface ServicePublic {
  id: number;
  name: string;
  description: string;
  price_minor: Money; // lowest price among the resources that perform it
  price_varies: boolean; // masters charge different prices -> show "from"
  duration_min: number;
  duration_varies: boolean;
  bookable: boolean;
  offers?: ServiceOffer[]; // only where customers pick a master
}

export type Requirement = "required" | "optional" | "hidden";

export interface Profile {
  type: "auto" | "wash" | "beauty_master" | "beauty_studio";
  label: string;
  kind: "vehicle" | "person";
  features: {
    choose_resource: boolean;
    per_resource_hours: boolean;
    resource_profiles: boolean;
    multi_day: boolean;
    vehicle_fields: boolean;
    per_resource_prices: boolean;
  };
  vocab: Record<string, string>;
  contact: { car: Requirement; plate: Requirement; note: Requirement };
  home: string[];
}

export interface MasterPublic {
  id: number;
  name: string;
  description: string;
  photo_url: string | null;
}

export interface HoursDay {
  weekday: number; // 0 = Monday
  closed: boolean;
  open: string | null;
  close: string | null;
}

export interface InfoCard {
  title: string;
  text: string;
  icon: string;
}

export interface GalleryItem {
  id: number;
  url: string;
  caption: string;
}

export interface TenantPublic {
  slug: string;
  status: "preview" | "active" | "disabled";
  is_preview: boolean;
  booking_enabled: boolean;
  subscription_state: "preview" | "trial" | "active" | "past_due" | "suspended" | "disabled";
  branding: { show: boolean; name: string; url: string };
  resources_count: number;
  business_type: Profile["type"];
  profile: Profile;
  resources: MasterPublic[];
  name: string;
  tagline: string;
  description: string;
  phone: string;
  address: string;
  map_url: string;
  timezone: string;
  currency: string;
  accent: string;
  logo_url: string | null;
  hero_url: string | null;
  info_cards: InfoCard[];
  rules: { cancel_before_hours: number; lead_time_min: number; max_advance_days: number; slot_step_min: number; reminder_hours: number };
  hours: HoursDay[];
  services: ServicePublic[];
  gallery: GalleryItem[];
  pwa: {
    icon192: string;
    icon512: string;
    maskable512: string;
    apple_touch: string;
    startup: { url: string; dw: number; dh: number; ratio: number }[];
  };
}

export interface SlotItem {
  start_min: number;
  available: boolean;
  resource_ids?: number[]; // only where customers pick a master
}
export interface SlotsResponse {
  service_id: number;
  bookable: boolean;
  days: Record<string, SlotItem[]>;
}

export type BookingStatus = "booked" | "accepted" | "ready" | "cancelled";

export interface ClientBooking {
  id: number;
  status: BookingStatus;
  service_name: string;
  price_minor: Money;
  start_min: number;
  end_min: number;
  car: string;
  plate: string;
  post_name: string;
  can_cancel: boolean;
  cancel_deadline_min: number;
  cancel_before_hours: number;
}

export interface CreatedBooking {
  booking: ClientBooking;
  access_token: string;
  replayed: boolean;
}

export interface OwnerBooking {
  id: number;
  status: BookingStatus;
  service_id: number;
  service_name: string;
  price_minor: Money;
  start_min: number;
  end_min: number;
  buffer_min: number;
  resource_id: number;
  post_name: string;
  client_name: string;
  client_phone: string;
  car: string;
  plate: string;
  note: string;
  source: "client" | "owner";
  is_demo: boolean;
  cancelled_by: string | null;
  paid_minor: Money;
  refunded_minor: Money;
  net_minor: Money;
  due_minor: Money;
}

export interface OwnerBlock {
  id: number;
  resource_id: number;
  start_min: number;
  end_min: number;
  note: string;
}

export interface OwnerSchedule {
  from: string;
  days: number;
  timezone: string;
  resources: { id: number; name: string }[];
  bookings: OwnerBooking[];
  blocks: OwnerBlock[];
}

export interface OwnerStats {
  period: string;
  currency: string;
  from: string;
  to: string;
  visits: number;
  completed: number;
  cancelled: number;
  scheduled_value_minor: Money;
  received_minor: Money;
  payments_minor: Money;
  refunds_minor: Money;
}

export interface OwnerOffer {
  resource_id: number;
  price_minor: Money | null; // null = the service's own price
  duration_min: number | null;
}

export interface OwnerService {
  id: number;
  name: string;
  description: string;
  price_minor: Money;
  duration_min: number;
  buffer_min: number;
  keywords: string[];
  is_active: boolean;
  resource_ids: number[];
  offers: OwnerOffer[];
}

export interface DayEdit {
  weekday: number;
  is_closed: boolean;
  open_min: number;
  close_min: number;
}
export interface ExceptionEdit {
  date: string;
  is_closed: boolean;
  open_min: number | null;
  close_min: number | null;
  note: string;
}

export interface OwnerResource {
  id: number;
  name: string;
  description: string;
  photo_url: string | null;
  is_active: boolean;
  has_own_hours: boolean;
  hours_edit: DayEdit[];
  exceptions: ExceptionEdit[];
}

export interface OwnerCatalog {
  profile: Profile;
  services: OwnerService[];
  resources: OwnerResource[];
}

export interface OwnerSettings extends TenantPublic {
  hours_edit: { weekday: number; is_closed: boolean; open_min: number; close_min: number }[];
  exceptions: { date: string; is_closed: boolean; open_min: number | null; close_min: number | null; note: string }[];
}

export interface AssistantOption {
  label: string;
  text: string;
  context?: Record<string, string | number>;
  /** a free time: tapping it opens the booking form with the service and time already chosen */
  action?: { type: "book"; service_id: number; start_min?: number };
}
export interface AssistantReply {
  status: "answered" | "clarify" | "unknown";
  text: string;
  intent?: string;
  options?: AssistantOption[];
  items?: unknown[];
  action?: { type: "book"; service_id: number; start_min?: number };
}

export interface PushConfig {
  enabled: boolean;
  public_key: string | null;
  preview: boolean;
}
