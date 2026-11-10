/**
 * Client API for LaunchGuard Admin endpoints.
 */

export interface GroupDoc {
  id: string;
  chat_id: number;
  group_name: string;
  active: boolean;
  owner_uid: string | null;
  subscription_status: string;
  scams_blocked: number;
  scam_keywords: string[];
  faq_pairs: Record<string, string>;
  created_at?: string;
  updated_at?: string;
}

export interface AdminStats {
  total_groups: number;
  active_groups: number;
  claimed_groups: number;
  total_blocked: number;
}

export interface AnalyticsSummary {
  total_pageviews: number;
  unique_visitors: number;
  today_pageviews: number;
  today_uniques: number;
  top_paths: { path: string; count: number }[];
  top_referrers: { referrer: string; count: number }[];
  device_breakdown: Record<string, number>;
  daily_trend: { date: string; pageviews: number; uniques: number }[];
  recent_visits: {
    path: string;
    referrer: string;
    device: string;
    timestamp: string;
  }[];
}


export function getAdminBackendUrl(): string {
  if (typeof window !== "undefined") {
    const custom = window.localStorage.getItem("launchguard:admin_backend_url");
    if (custom) return custom.replace(/\/$/, "");
  }
  return (
    process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "") ||
    "https://launchguard-qo47.onrender.com"
  );
}

async function adminRequest<T>(
  path: string,
  adminKey: string,
  options: RequestInit = {}
): Promise<T> {
  const baseUrl = getAdminBackendUrl();
  const url = `${baseUrl}${path}`;
  const headers = new Headers(options.headers || {});
  headers.set("X-Admin-Key", adminKey);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(url, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    throw new Error("Invalid admin key. Access denied.");
  }

  if (!res.ok) {
    let msg = `Request failed with status ${res.status}`;
    try {
      const data = await res.json();
      if (data.message || data.error) {
        msg = data.message || data.error;
      }
    } catch {
      // ignore
    }
    throw new Error(msg);
  }

  return res.json() as Promise<T>;
}

export async function fetchAdminStats(adminKey: string): Promise<AdminStats> {
  return adminRequest<AdminStats>("/api/admin/stats", adminKey);
}

export async function fetchAdminAnalytics(adminKey: string): Promise<AnalyticsSummary> {
  return adminRequest<AnalyticsSummary>("/api/admin/analytics", adminKey);
}


export async function fetchAdminGroups(adminKey: string): Promise<GroupDoc[]> {
  const data = await adminRequest<{ groups: GroupDoc[] }>("/api/admin/groups", adminKey);
  return data.groups;
}

export async function createAdminGroup(
  adminKey: string,
  payload: {
    chat_id: number;
    group_name: string;
    active?: boolean;
    owner_uid?: string | null;
    subscription_status?: string;
  }
): Promise<GroupDoc> {
  const data = await adminRequest<{ ok: boolean; group: GroupDoc }>("/api/admin/groups", adminKey, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data.group;
}

export async function updateAdminGroup(
  adminKey: string,
  chatId: number,
  updates: Partial<GroupDoc>
): Promise<GroupDoc> {
  const data = await adminRequest<{ ok: boolean; group: GroupDoc }>(
    `/api/admin/groups/${chatId}`,
    adminKey,
    {
      method: "PATCH",
      body: JSON.stringify(updates),
    }
  );
  return data.group;
}

export async function deleteAdminGroup(
  adminKey: string,
  chatId: number
): Promise<boolean> {
  const data = await adminRequest<{ ok: boolean; chat_id: number }>(
    `/api/admin/groups/${chatId}`,
    adminKey,
    {
      method: "DELETE",
    }
  );
  return data.ok;
}

