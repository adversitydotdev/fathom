import type { Metadata } from "next";

import { getControl } from "@/lib/data";

import { ControlDetail } from "./control-detail";

export async function generateMetadata({ params }: PageProps<"/programs/[programId]/controls/[controlId]">): Promise<Metadata> {
  const { controlId } = await params;
  const control = await getControl(controlId);
  return { title: `${control.display_id ?? ""} ${control.name}`.trim() };
}

export default async function ControlPage({ params, searchParams }: PageProps<"/programs/[programId]/controls/[controlId]">) {
  const { programId, controlId } = await params;
  const { at } = await searchParams;
  return <ControlDetail programId={programId} controlId={controlId} atParam={typeof at === "string" ? at : undefined} variant="page" />;
}
