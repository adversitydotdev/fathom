import { ControlDetail } from "@/app/programs/[programId]/controls/[controlId]/control-detail";
import { SidePanel } from "@/components/shell/side-panel";
import { getControl } from "@/lib/data";

/** A control link clicked inside the app opens here; a direct load gets the full page. */
export default async function ControlPanel({
  params,
  searchParams,
}: {
  params: Promise<{ programId: string; controlId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { programId, controlId } = await params;
  const { at } = await searchParams;
  const atParam = typeof at === "string" ? at : undefined;
  const q = atParam ? `?at=${atParam}` : "";
  const control = await getControl(controlId);
  return (
    <SidePanel
      label={`${control.display_id ?? ""} ${control.name}`.trim()}
      fullHref={`/programs/${programId}/controls/${controlId}${q}`}
      fallbackHref={`/programs/${programId}/controls${q}`}
    >
      <ControlDetail programId={programId} controlId={controlId} atParam={atParam} variant="panel" />
    </SidePanel>
  );
}
