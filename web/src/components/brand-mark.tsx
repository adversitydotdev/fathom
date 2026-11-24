import type { SVGProps } from "react";

export function FathomMark(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <path
        d="M26.2 16V20.2C26.2 23.51 23.51 26.2 20.2 26.2H11.8C8.49 26.2 5.8 23.51 5.8 20.2V11.8C5.8 8.49 8.49 5.8 11.8 5.8H20.2C22.4 5.8 24.32 6.98 25.36 8.75"
        stroke="currentColor"
        strokeWidth="3.8"
        strokeLinecap="butt"
      />
      <path d="M15.2 16H28.1" stroke="currentColor" strokeWidth="3.8" strokeLinecap="butt" />
    </svg>
  );
}
