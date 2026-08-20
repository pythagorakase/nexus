import type { BackstageTurnResponse } from "@/types/backstage";

export async function getBackstageTurn(
  slot: number,
): Promise<BackstageTurnResponse> {
  const response = await fetch(`/api/dev/backstage/${slot}/turn`);
  if (!response.ok) {
    const detail = (await response.text()) || response.statusText;
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json();
}
