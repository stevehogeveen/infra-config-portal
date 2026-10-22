export type ContractItem = {
  id: string; title: string; step: string; device_id: string; href: string;
  desired: Record<string, unknown>; observed?: Record<string, unknown>; state?: string;
  verified?: Record<string, unknown> | null; verified_at?: string | null;
};
export type Contract = { profile_id: string; kit: string; digest: string; network: Record<string, unknown>; items: ContractItem[] };
export type Progress = { state: "unapproved" | "converging" | "blocked" | "converged"; item: string | null; message: string; href?: string; items: ContractItem[] };
export type Certificate = { digest: string; generated_at: string; state: string; items: ContractItem[] };

// apiRequest is private to api.ts. Keep its base URL, actor and error convention here.
async function request<T>(profile: string, action = "", body?: unknown): Promise<T> {
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? ""}/api/v1/rack-plans/${encodeURIComponent(profile)}/contract${action}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", "X-Local-User": "local-operator" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(error.detail || `Contract request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}
export const contractApi = {
  get: (p: string) => request<Contract>(p),
  approve: (p: string, digest: string) => request<{ state: string }>(p, "/approve", { digest }),
  reconcile: (p: string) => request<Progress>(p, "/reconcile", {}),
  certificate: (p: string) => request<Certificate>(p, "/certificate"),
};
