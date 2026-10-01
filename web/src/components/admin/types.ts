export interface AdminPlan {
  key: string;
  label: string;
  price_minor: number;
  max_resources: number | null;
  max_bookings_month: number | null;
  custom_domain: boolean;
  remove_branding: boolean;
}
export interface AdminDomain {
  id: number;
  host: string;
  status: "pending" | "active" | "disabled";
}
export interface AdminTenant {
  slug: string;
  name: string;
  business_type: string;
  status: "preview" | "active" | "disabled";
  suspended: boolean;
  notes: string;
  plan: string;
  plan_label: string;
  state: "preview" | "trial" | "active" | "past_due" | "suspended" | "disabled";
  ends_at: number | null;
  days_left: number | null;
  trial_ends_at: number | null;
  paid_until: number | null;
  created_at: number;
  last_booking_at: number | null;
  owners: string[];
  domains: AdminDomain[];
  usage: { bookings_month: number; resources: number };
  limits: { resources: number | null; bookings_month: number | null };
  audit?: { at: number; actor: string; action: string; detail: Record<string, unknown> }[];
}
export interface AdminOverview {
  tenants_total: number;
  by_state: Record<string, number>;
  bookings_30d: number;
  sales_total_minor: number;
  live_total: number;
  tenants: AdminTenant[];
}
export interface DnsCheck {
  host: string;
  resolved: string[];
  expected: string[];
  ok: boolean;
  configured: boolean;
}
