import type {
  FirmwareSummary,
  LabAddressPlan,
  LabProfile,
  LabProfileFeatures,
  LabValidationItem,
  LabValidationSummary,
  ProviderProbeResult,
  ProviderStatus
} from "./types";

export type OperatorHomeDisplayState = "ready" | "needs_attention" | "blocked" | "not_checked";

export type OperatorHomeDeviceSummaryItem = {
  Detail: string;
  Name: string;
  NeedsAttention: boolean;
  Role: string;
  State: string;
  Target: string;
};

export type OperatorHomeAttentionItem = {
  Action: string;
  Device: string;
  Explanation: string;
  Id: string;
  Label: string;
  Severity: "blocking" | "warning" | "info";
};

export type OperatorHomeNextAction = {
  Enabled: boolean;
  Label: string;
  Target: "build" | "details";
};

export type OperatorHomeProgress = {
  Label: string;
  Ready: number;
  Total: number;
};

export type OperatorHomeModel = {
  KitName: string;
  CurrentPhase: string;
  DisplayState: OperatorHomeDisplayState;
  Headline: string;
  SupportingMessage: string;
  DeviceSummary: OperatorHomeDeviceSummaryItem[];
  AttentionItems: OperatorHomeAttentionItem[];
  NextAction: OperatorHomeNextAction;
  Progress: OperatorHomeProgress;
};

export function buildOperatorHomeModel({
  address,
  buildVerification,
  features,
  firmwareSummaries,
  profile,
  providers,
  validation,
  vcenterNetapp
}: {
  address: LabAddressPlan;
  buildVerification: ProviderProbeResult | null;
  features: LabProfileFeatures | null;
  firmwareSummaries: FirmwareSummary[];
  profile: LabProfile | null;
  providers: ProviderStatus[];
  validation: LabValidationSummary | null;
  vcenterNetapp: ProviderProbeResult | null;
}): OperatorHomeModel {
  const rawKitName = profile?.name ?? "No kit selected";
  const kitName = cleanOperatorText(rawKitName.replace(/\bRuntime Lab\b/gi, "Current Lab"));
  const currentPhase = deploymentLabel(features);
  const deviceSummary = buildDeviceSummary({ address, features, firmwareSummaries, providers, validation, vcenterNetapp });
  const attentionItems = buildAttentionItems({ firmwareSummaries, profile, validation });
  const readyCount = deviceSummary.filter((item) => !item.NeedsAttention).length;
  const totalCount = Math.max(deviceSummary.length, 1);
  const displayState = operatorDisplayState({ attentionItems, buildVerification, validation });
  const headline = operatorHeadline({ attentionItems, displayState, profile });
  const supportingMessage = operatorSupportingMessage({
    attentionCount: attentionItems.length,
    currentPhase,
    kitName,
    readyCount,
    subnet: address.subnet,
    totalCount
  });

  return {
    KitName: kitName,
    CurrentPhase: currentPhase,
    DisplayState: displayState,
    Headline: headline,
    SupportingMessage: supportingMessage,
    DeviceSummary: deviceSummary,
    AttentionItems: attentionItems,
    NextAction: {
      Enabled: Boolean(profile),
      Label: profile ? "Review Build Plan" : "Select a kit",
      Target: profile ? "build" : "details"
    },
    Progress: {
      Label: `${readyCount} of ${totalCount} devices ready`,
      Ready: readyCount,
      Total: totalCount
    }
  };
}

function buildDeviceSummary({
  address,
  features,
  firmwareSummaries,
  providers,
  validation,
  vcenterNetapp
}: {
  address: LabAddressPlan;
  features: LabProfileFeatures | null;
  firmwareSummaries: FirmwareSummary[];
  providers: ProviderStatus[];
  validation: LabValidationSummary | null;
  vcenterNetapp: ProviderProbeResult | null;
}): OperatorHomeDeviceSummaryItem[] {
  const netappInScope = features?.netapp_enabled !== false;
  const vcenterInScope = features?.vcenter_enabled === true;
  const rows: OperatorHomeDeviceSummaryItem[] = [
    deviceSummaryRow({
      detail: firmwareIssue(firmwareSummaries, ["cisco"]) || "Switch access and fabric readiness",
      name: "Cisco switch",
      role: "Network",
      status: statusFor({ providers, tokens: ["cisco"], validation }),
      target: displayAddress(address.cisco_management)
    }),
    deviceSummaryRow({
      detail: "Out-of-band server management checks",
      name: "HPE iLO",
      role: "Server management",
      status: statusFor({ providers, tokens: ["ilo", "hpe"], validation }),
      target: displayAddress(address.ilo)
    }),
    deviceSummaryRow({
      detail: "Server management, ESXi, and local storage checks",
      name: "HPE server",
      role: "Server",
      status: strongestStatus([
        statusFor({ providers, tokens: ["ilo", "hpe"], validation }),
        statusFor({ providers, tokens: ["esxi"], validation })
      ]),
      target: displayAddress(address.ilo || address.esxi_management)
    })
  ];

  if (vcenterInScope || netappInScope) {
    rows.push(
      deviceSummaryRow({
        detail: vcenterInScope ? "Central virtualization management" : "Direct host management",
        name: vcenterInScope ? "vCenter" : "ESXi host",
        role: "Virtualization",
        status: stringValue(vcenterNetapp?.status) || statusFor({ providers, tokens: ["vcenter", "esxi"], validation }),
        target: vcenterTarget(vcenterNetapp)
      })
    );
  }

  if (netappInScope) {
    rows.push(
      deviceSummaryRow({
        detail: storageProtocolLabel(features),
        name: "NetApp ONTAP",
        role: "Shared storage",
        status: statusFor({ fallback: stringValue(vcenterNetapp?.status) || "not_checked", providers, tokens: ["netapp", "storage"], validation }),
        target: displayAddress(address.netapp_cluster_mgmt)
      }),
      deviceSummaryRow({
        detail: datastoreDetail(vcenterNetapp),
        name: "Datastore",
        role: "VM storage",
        status: datastoreStatus(vcenterNetapp),
        target: datastoreName(vcenterNetapp)
      })
    );
  }

  if (vcenterInScope && !netappInScope) {
    rows.push(
      deviceSummaryRow({
        detail: "VM inventory and control path",
        name: "vCenter",
        role: "Virtualization",
        status: stringValue(vcenterNetapp?.status) || statusFor({ providers, tokens: ["vcenter"], validation }),
        target: vcenterTarget(vcenterNetapp)
      })
    );
  }

  return rows;
}

function deviceSummaryRow({
  detail,
  name,
  role,
  status,
  target
}: {
  detail: string;
  name: string;
  role: string;
  status: string;
  target: string;
}): OperatorHomeDeviceSummaryItem {
  return {
    Detail: detail || "No detail available yet",
    Name: name,
    NeedsAttention: !statusIsHealthy(status),
    Role: role,
    State: displayStatus(status),
    Target: target || "Not set up"
  };
}

function buildAttentionItems({
  firmwareSummaries,
  profile,
  validation
}: {
  firmwareSummaries: FirmwareSummary[];
  profile: LabProfile | null;
  validation: LabValidationSummary | null;
}): OperatorHomeAttentionItem[] {
  const items: OperatorHomeAttentionItem[] = [];

  if (!profile) {
    items.push({
      Action: "Create or select a lab kit.",
      Device: "Lab kit",
      Explanation: "No active kit is selected, so readiness cannot be trusted yet.",
      Id: "kit-not-selected",
      Label: "Choose a kit",
      Severity: "blocking"
    });
  }

  const topBlocker = validation?.top_blocker;
  if (topBlocker) {
    items.push({
      Action: cleanOperatorAction(topBlocker.recommended_action || topBlocker.where_to_fix || validation?.next_action),
      Device: cleanOperatorText(topBlocker.source || "Lab"),
      Explanation: cleanOperatorText(topBlocker.problem || "One lab prerequisite needs attention."),
      Id: "top-blocker",
      Label: "Next blocker",
      Severity: "blocking"
    });
  }

  for (const item of validation?.validation_items ?? []) {
    if (statusIsHealthy(item.status) || item.status === "not_in_scope") continue;
    items.push(attentionFromValidationItem(item));
  }

  for (const summary of firmwareSummaries) {
    const status = summary.path_status || summary.compliance_status || summary.severity;
    if (statusIsHealthy(status) || status === "not_in_scope") continue;
    items.push({
      Action: cleanOperatorAction(summary.next_action || "Run the firmware check before upgrading."),
      Device: cleanOperatorText(summary.label || "Firmware"),
      Explanation: cleanOperatorText(summary.blocker || summary.disabled_reason || "Firmware readiness still needs proof."),
      Id: `firmware-${summary.device_id}`,
      Label: "Firmware needs proof",
      Severity: status === "blocked" ? "blocking" : "warning"
    });
  }

  return uniqueAttentionItems(items).slice(0, 4);
}

function attentionFromValidationItem(item: LabValidationItem): OperatorHomeAttentionItem {
  const severity: OperatorHomeAttentionItem["Severity"] = item.status === "blocked" ? "blocking" : "warning";
  return {
    Action: cleanOperatorAction(item.next_action || "Open Details and inspect this device."),
    Device: cleanOperatorText(item.label || item.category || "Lab"),
    Explanation: cleanOperatorText(item.setup_summary || item.current_state || "This item needs attention."),
    Id: item.id,
    Label: cleanOperatorText(item.label || "Lab item"),
    Severity: severity
  };
}

function operatorDisplayState({
  attentionItems,
  buildVerification,
  validation
}: {
  attentionItems: OperatorHomeAttentionItem[];
  buildVerification: ProviderProbeResult | null;
  validation: LabValidationSummary | null;
}): OperatorHomeDisplayState {
  if (attentionItems.some((item) => item.Severity === "blocking")) return "blocked";
  if (attentionItems.length > 0) return "needs_attention";
  const status = validation?.overall_status || stringValue(buildVerification?.status);
  if (statusIsHealthy(status)) return "ready";
  return status ? "not_checked" : "not_checked";
}

function operatorHeadline({
  attentionItems,
  displayState,
  profile
}: {
  attentionItems: OperatorHomeAttentionItem[];
  displayState: OperatorHomeDisplayState;
  profile: LabProfile | null;
}): string {
  if (!profile) return "Choose a lab kit before running setup.";
  if (displayState === "blocked") return "The lab is blocked by one actionable item.";
  if (displayState === "needs_attention") {
    return attentionItems.length === 1
      ? "One item needs attention before the next stage."
      : `${attentionItems.length} items need attention before the next stage.`;
  }
  if (displayState === "ready") return "The lab is ready for the next check.";
  return "Readiness has not been checked yet.";
}

function operatorSupportingMessage({
  attentionCount,
  currentPhase,
  kitName,
  readyCount,
  subnet,
  totalCount
}: {
  attentionCount: number;
  currentPhase: string;
  kitName: string;
  readyCount: number;
  subnet: string | null;
  totalCount: number;
}): string {
  const scope = subnet ? `${kitName} on ${subnet}` : kitName;
  const attentionVerb = attentionCount === 1 ? "needs" : "need";
  const attention = attentionCount ? `${attentionCount} item${attentionCount === 1 ? "" : "s"} ${attentionVerb} attention.` : "No actionable blockers are shown.";
  return `${scope} is in ${currentPhase}. ${readyCount} of ${totalCount} devices are ready. ${attention}`;
}

function uniqueAttentionItems(items: OperatorHomeAttentionItem[]): OperatorHomeAttentionItem[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = item.Explanation.toLowerCase() || `${item.Label}|${item.Device}|${item.Action}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function statusFor({
  fallback = "not_checked",
  providers,
  tokens,
  validation
}: {
  fallback?: string;
  providers: ProviderStatus[];
  tokens: string[];
  validation: LabValidationSummary | null;
}): string {
  return validationStatus(validation, tokens) || providerStatus(providers, tokens) || fallback;
}

function validationStatus(validation: LabValidationSummary | null, tokens: string[]): string {
  const item = validation?.validation_items.find((candidate) => textIncludes(candidateText(candidate), tokens));
  return item?.status ?? "";
}

function providerStatus(providers: ProviderStatus[], tokens: string[]): string {
  const provider = providers.find((candidate) => textIncludes(`${candidate.name} ${candidate.kind} ${candidate.id}`, tokens));
  return provider?.status ?? "";
}

function firmwareIssue(summaries: FirmwareSummary[], tokens: string[]): string {
  const summary = summaries.find((candidate) => textIncludes(`${candidate.label} ${candidate.device_id} ${candidate.component_type}`, tokens));
  const status = summary?.path_status || summary?.compliance_status || summary?.severity || "";
  if (summary && !statusIsHealthy(status)) {
    return cleanOperatorText(summary.blocker || summary.next_action || "Firmware proof needs attention");
  }
  return "";
}

function strongestStatus(statuses: string[]): string {
  const normalized = statuses.map((status) => status || "not_checked");
  if (normalized.some((status) => ["blocked", "failed", "critical", "hard_fail", "error"].includes(status))) return "blocked";
  if (normalized.some((status) => ["warning", "partial", "manual_review", "cannot_verify", "needs_credentials", "needs_console", "not_accessible"].includes(status))) return "warning";
  if (normalized.some((status) => ["not_configured", "not_configured_yet", "not_checked", "not_in_scope", "not_setup"].includes(status))) {
    return normalized.find((status) => ["ready", "ok", "completed", "passed", "accessible", "current"].includes(status)) ? "warning" : "not_checked";
  }
  if (normalized.some((status) => ["ready", "ok", "completed", "passed", "accessible", "current"].includes(status))) return "ready";
  return normalized[0] ?? "not_checked";
}

function statusIsHealthy(status: string): boolean {
  return ["accessible", "ready", "ok", "completed", "passed", "success", "current"].includes((status || "").toLowerCase());
}

function displayStatus(status: string): string {
  const labels: Record<string, string> = {
    accessible: "Ready",
    blocked: "Blocked",
    cannot_verify: "Needs review",
    completed: "Ready",
    current: "Current",
    failed: "Needs attention",
    hard_fail: "Blocked",
    needs_console: "Needs console",
    needs_credentials: "Needs credentials",
    not_accessible: "Not accessible",
    not_checked: "Not checked",
    not_configured: "Not set up",
    not_configured_yet: "Not set up",
    not_in_scope: "Not in this setup",
    not_setup: "Not set up",
    ok: "Ready",
    partial: "Partly ready",
    passed: "Ready",
    ready: "Ready",
    scan_needed: "Needs scan",
    warning: "Needs review"
  };
  return labels[status] ?? labelize(status || "not_checked");
}

function deploymentLabel(features: LabProfileFeatures | null): string {
  if (features?.deployment_label) return features.deployment_label;
  if (features?.deployment_mode === "single_server_local_raid" || features?.storage_location === "server_local") {
    return "Single server - local RAID";
  }
  if (features?.netapp_enabled !== false && features?.vcenter_enabled === true) return "Server + NetApp + vCenter";
  if (features?.netapp_enabled !== false) return "Server + NetApp";
  return "Single server";
}

function storageProtocolLabel(features: LabProfileFeatures | null): string {
  if (features?.storage_location === "server_local" || features?.netapp_enabled === false) return "Local RAID storage";
  const protocol = features?.storage_protocol ? labelize(features.storage_protocol) : "Shared storage";
  return `${protocol} shared storage`;
}

function datastoreStatus(probe: ProviderProbeResult | null): string {
  const checks = objectValue(probe?.checks);
  const datastore = objectValue(checks.datastore_mounted ?? checks.datastore_visible);
  if (booleanValue(datastore.mounted) || booleanValue(datastore.visible)) return "ready";
  return stringValue(datastore.status) || "not_checked";
}

function datastoreDetail(probe: ProviderProbeResult | null): string {
  const checks = objectValue(probe?.checks);
  const datastore = objectValue(checks.datastore_mounted ?? checks.datastore_visible);
  if (booleanValue(datastore.mounted) || booleanValue(datastore.visible)) return "Datastore visible to ESXi";
  return "Datastore proof not visible yet";
}

function datastoreName(probe: ProviderProbeResult | null): string {
  const plan = objectValue(probe?.deployment_plan);
  const checks = objectValue(probe?.checks);
  const datastore = objectValue(checks.datastore_mounted ?? checks.datastore_visible);
  return stringValue(plan.datastore_name) || stringValue(datastore.name) || "Not mounted";
}

function vcenterTarget(probe: ProviderProbeResult | null): string {
  const current = objectValue(probe?.current_state);
  const plan = objectValue(probe?.deployment_plan);
  return stringValue(current.vcenter_url) || stringValue(plan.vcenter_url) || "Not attached";
}

function displayAddress(value: unknown): string {
  const text = stringValue(value);
  return text || "Not set up";
}

function cleanOperatorAction(value: unknown): string {
  const text = cleanOperatorText(stringValue(value));
  if (!text || /^no action required\.?$/i.test(text)) return "";
  return text
    .replace(/\bOpen Storage\b/gi, "Open Details, then choose NetApp")
    .replace(/\bOpen Network\b/gi, "Open Details, then choose Cisco switch")
    .replace(/\bOpen Server\b/gi, "Open Details, then choose HPE server")
    .replace(/\bOpen Virtualization\b/gi, "Open Details, then choose vCenter");
}

function cleanOperatorText(value: unknown): string {
  return stringValue(value)
    .replace(/[A-Z0-9]+(?:_[A-Z0-9]+){2,}/g, (match) => labelize(match.toLowerCase()))
    .replace(/\bprovider\b/gi, "device")
    .replace(/\bruntime\b/gi, "lab")
    .replace(/\bworkflow action\b/gi, "action")
    .replace(/\bartifact\b/gi, "proof")
    .replace(/[_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function candidateText(item: LabValidationItem): string {
  return `${item.id} ${item.label} ${item.category} ${item.stage} ${item.setup_summary}`;
}

function textIncludes(value: string, tokens: string[]): boolean {
  const text = value.toLowerCase();
  return tokens.some((token) => text.includes(token.toLowerCase()));
}

function labelize(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function stringValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function booleanValue(value: unknown): boolean {
  return value === true || value === "true" || value === "yes" || value === 1;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
