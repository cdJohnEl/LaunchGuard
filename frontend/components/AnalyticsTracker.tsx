"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { getAdminBackendUrl } from "@/lib/adminApi";

export function AnalyticsTracker() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const lastLoggedPathRef = useRef<string | null>(null);

  useEffect(() => {
    if (!pathname) return;

    // Do not track admin portal visits to keep analytics clean
    if (pathname.startsWith("/admin")) return;

    const currentPath = pathname;
    if (lastLoggedPathRef.current === currentPath) return;
    lastLoggedPathRef.current = currentPath;

    // Get or create persistent anonymous visitor ID
    let visitorId = "";
    try {
      visitorId = window.localStorage.getItem("lg_visitor_id") || "";
      if (!visitorId) {
        visitorId =
          "v_" + Math.random().toString(36).substring(2, 11) + "_" + Date.now().toString(36);
        window.localStorage.setItem("lg_visitor_id", visitorId);
      }
    } catch {
      visitorId = "anon_" + Math.random().toString(36).substring(2, 10);
    }

    // Determine device category
    const width = typeof window !== "undefined" ? window.innerWidth : 1200;
    const device = width < 768 ? "mobile" : width < 1024 ? "tablet" : "desktop";

    const payload = {
      path: currentPath,
      referrer: typeof document !== "undefined" ? document.referrer || "" : "",
      visitor_id: visitorId,
      device,
    };

    const backendUrl = getAdminBackendUrl();
    const endpoint = `${backendUrl}/api/analytics/collect`;

    try {
      if (typeof navigator !== "undefined" && navigator.sendBeacon) {
        const blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
        navigator.sendBeacon(endpoint, blob);
      } else {
        fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          keepalive: true,
        }).catch(() => { });
      }
    } catch {
      // Analytics must never throw or block UI
    }
  }, [pathname, searchParams]);

  return null;
}

