"use client";

import { useEffect } from "react";

/**
 * Sets `<html data-hydrated>` once React owns the page. Playwright and agents
 * wait on it before clicking, since a click before hydration is dropped.
 */
export function HydratedMarker() {
  useEffect(() => {
    document.documentElement.dataset.hydrated = "true";
  }, []);
  return null;
}
