"use client";

import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { useEffect, useLayoutEffect, useRef } from "react";

import { useListLocation } from "@/components/shell/side-panel";

/** Set after the first hydration, so count-ups skip the initial page load. */
let booted = false;
export function MotionBoot() {
  useEffect(() => {
    booted = true;
  }, []);
  return null;
}

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * A number that counts up when it first appears after an in-app navigation,
 * and eases to new values after a refresh. The server renders the final
 * value, so a full page load shows it straight away (no flash of 0).
 */
export function CountUp({ value, suffix = "", className }: { value: number; suffix?: string; className?: string }) {
  const reduced = useReducedMotion();
  // After boot there is no hydration to match, so start at 0 and avoid a
  // one-frame flash of the final value.
  const mv = useMotionValue(booted && value !== 0 && !prefersReducedMotion() ? 0 : value);
  const text = useTransform(mv, (v) => `${Math.round(v)}${suffix}`);
  const first = useRef(true);

  useLayoutEffect(() => {
    if (reduced) {
      mv.jump(value);
      return;
    }
    if (first.current) {
      first.current = false;
      if (mv.get() === value) return;
    }
    const controls = animate(mv, value, { duration: 0.8, ease: [0.2, 0.7, 0.2, 1] });
    return () => controls.stop();
  }, [value, reduced, mv]);

  return (
    <motion.span className={className}>{text}</motion.span>
  );
}

/** Re-runs the content's entrance when the page (not the side panel) changes. */
export function PageTransition({ children }: { children: React.ReactNode }) {
  const { pathname } = useListLocation();
  return (
    <div key={pathname} className="motion-fade">
      {children}
    </div>
  );
}
