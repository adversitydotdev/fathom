/**
 * One organization's program, as the API would return it. Acme runs one
 * system (`acme-platform`) on AWS with Okta for identity, under two programs:
 * NIST SP 800-171 r3 and an SP 800-53 r5 moderate subset.
 *
 * Control state is written here by hand. It stands in for the kernel's
 * section 8 computation; the UI never derives it.
 */
import type {
  Baseline,
  Component,
  ControlState,
  Control,
  Evidence,
  Exception,
  Finding,
  Framework,
  Implementation,
  Job,
  Mapping,
  Party,
  Program,
  Result,
  Risk,
  System,
  Test,
} from "@/lib/api/types";

/** The fixtures' "today". Every relative date below is measured from it. */
export const FIXTURE_NOW = "2026-11-09T12:00:00Z";

const LIB_TS = "2026-10-22T11:30:00Z";
const SPEC = "0.1.0" as const;

function day(offset: number): string {
  const d = new Date(FIXTURE_NOW);
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
}
function at(offset: number, time = "09:00:00Z"): string {
  return `${day(offset)}T${time}`;
}
function envelope<T extends string>(type: T, slug: string, created = at(-120), modified?: string) {
  return { type, id: `${type}--${slug}`, spec_version: SPEC, created, modified: modified ?? created };
}

// Parties ------------------------------------------------------------------

export const parties: Party[] = [
  { ...envelope("party", "jordan-lee"), name: "Jordan Lee", kind: "person" },
  { ...envelope("party", "priya-shah"), name: "Priya Shah", kind: "person" },
  { ...envelope("party", "sam-okafor"), name: "Sam Okafor", kind: "person" },
  { ...envelope("party", "secops"), name: "Security operations", kind: "team" },
  { ...envelope("party", "platform"), name: "Platform engineering", kind: "team" },
  { ...envelope("party", "compliance-agent"), name: "Compliance agent", kind: "role", tags: ["agent"] },
  { ...envelope("party", "harness"), name: "Test harness", kind: "role" },
  { ...envelope("party", "okta"), name: "Okta, Inc.", kind: "organization" },
  { ...envelope("party", "aws"), name: "Amazon Web Services", kind: "organization" },
];
const P = (slug: string) => `party--${slug}`;
export const AGENT_PARTY = P("compliance-agent");

// Components and system ----------------------------------------------------

export const components: Component[] = [
  { ...envelope("component", "okta"), name: "Okta Workforce Identity", kind: "service", party_ref: P("okta") },
  { ...envelope("component", "aws"), name: "AWS (us-east-1)", kind: "service", party_ref: P("aws") },
];

export const systems: System[] = [
  {
    ...envelope("system", "acme-platform", at(-200), at(-12, "16:20:04.118Z")),
    name: "Acme Platform",
    function: "Multi-tenant SaaS that stores and processes customer engineering data, including CUI.",
    boundary: "Production AWS account 4471, the Okta tenant, and the CI/CD pipeline that deploys to them.",
    component_refs: components.map((c) => c.id),
    information_types: [
      { name: "Controlled unclassified information", confidentiality: "moderate", integrity: "moderate", availability: "low" },
    ],
    parties: [
      { party_ref: P("aws"), role: "subservice", function: "Hosting and physical security" },
      { party_ref: P("okta"), role: "subservice", function: "Workforce identity" },
      { party_ref: P("platform"), role: "operator" },
    ],
  },
];
export const SYSTEM_ID = systems[0].id;

// Frameworks ---------------------------------------------------------------

export const frameworks: Framework[] = [
  {
    type: "framework", id: "framework--nist-sp-800-171-r3", spec_version: SPEC, created: LIB_TS, modified: LIB_TS,
    name: "NIST SP 800-171 Revision 3", publisher: "NIST", version: "1.1.0", reproduction: "permitted",
  },
  {
    type: "framework", id: "framework--nist-sp-800-53-r5", spec_version: SPEC, created: LIB_TS, modified: LIB_TS,
    name: "NIST SP 800-53 Revision 5", publisher: "NIST", version: "5.1.1", reproduction: "permitted",
  },
];

// Controls -----------------------------------------------------------------

type Rel = Mapping["relationship"];
type ControlSpec = {
  slug: string;
  display: string;
  name: string;
  family: string;
  type: Control["control_type"];
  frequency: Control["frequency"];
  origin?: Control["origin"];
  statement: string;
  params?: Record<string, { label: string; value?: string }>;
  state: ControlState;
  failed?: string[];
  impl: {
    status: Implementation["status"];
    responsibility: Implementation["responsibility"];
    owner: string;
    narrative: string;
    byAgent?: boolean;
    paramValues?: Record<string, string>;
  };
  /** [requirement id suffix, relationship, reviewed] */
  maps: [string, Rel, boolean][];
};

const R171 = "requirement--nist-sp-800-171-r3-";
const R53 = "requirement--nist-sp-800-53-r5-";

const specs: ControlSpec[] = [
  {
    slug: "account-lifecycle", display: "IAM-01", name: "Account lifecycle management", family: "Identity and access",
    type: "preventive", frequency: "quarterly",
    statement: "Provision, review, and remove accounts through the identity provider, and review privileged accounts every {{ review_period }}.",
    params: { review_period: { label: "review period" } },
    state: "gap", failed: ["Parameter review_period has no value"],
    impl: { status: "partial", responsibility: "provider", owner: "jordan-lee", narrative: "Joiner, mover, and leaver events in the HRIS drive Okta provisioning. Quarterly access reviews are run in Okta Access Certifications." },
    maps: [[R171 + "03-01-01", "equivalent-to", true], [R53 + "ac-2", "equivalent-to", true]],
  },
  {
    slug: "mfa-privileged", display: "IAM-02", name: "Multi-factor authentication for privileged access", family: "Identity and access",
    type: "preventive", frequency: "continuous",
    statement: "Require {{ authenticator }} for every privileged account, enrolled within {{ enrollment_window }} of account creation.",
    params: { authenticator: { label: "authenticator type" }, enrollment_window: { label: "enrollment window" } },
    state: "gap", failed: ["Required test mfa-enforced is not passing (latest result: fail)"],
    impl: {
      status: "implemented", responsibility: "shared", owner: "jordan-lee", byAgent: true,
      paramValues: { authenticator: "phishing-resistant authenticators (WebAuthn)", enrollment_window: "24 hours" },
      narrative: "Okta enforces WebAuthn for the Admins and Break-glass groups through an authentication policy. Break-glass credentials are sealed in the vault and their use pages Security operations.",
    },
    maps: [[R171 + "03-05-03", "subset-of", true], [R53 + "ia-2-1", "equal-to", true]],
  },
  {
    slug: "least-privilege", display: "IAM-03", name: "Least privilege", family: "Identity and access",
    type: "preventive", frequency: "quarterly", state: "met",
    statement: "Grant users and services only the access their role requires, and review role definitions quarterly.",
    impl: { status: "implemented", responsibility: "provider", owner: "jordan-lee", narrative: "Production access is granted through time-boxed AWS IAM Identity Center permission sets requested in Slack and approved by a second engineer." },
    maps: [[R171 + "03-01-05", "equivalent-to", true], [R53 + "ac-6", "equivalent-to", true], [R171 + "03-01-02", "intersects-with", false]],
  },
  {
    slug: "remote-access", display: "IAM-04", name: "Remote access", family: "Identity and access",
    type: "preventive", frequency: "continuous", state: "met",
    statement: "Route administrative remote access through the identity-aware proxy. Direct SSH and RDP from the internet are blocked.",
    impl: { status: "implemented", responsibility: "provider", owner: "platform", narrative: "All administrative sessions go through AWS Systems Manager Session Manager. Security groups deny 22 and 3389 from 0.0.0.0/0." },
    maps: [[R171 + "03-01-12", "equivalent-to", true], [R53 + "ac-17", "equivalent-to", true]],
  },
  {
    slug: "authenticator-management", display: "IAM-05", name: "Password and authenticator management", family: "Identity and access",
    type: "preventive", frequency: "annual", state: "met",
    statement: "Screen new passwords against a compromised-password list and enforce a minimum length of 14 characters.",
    impl: { status: "implemented", responsibility: "provider", owner: "jordan-lee", narrative: "Okta password policy enforces 14 characters and blocks common and breached passwords." },
    maps: [[R171 + "03-05-07", "equivalent-to", true], [R53 + "ia-5", "subset-of", true]],
  },
  {
    slug: "event-logging", display: "LOG-01", name: "Event logging", family: "Logging and monitoring",
    type: "detective", frequency: "continuous", state: "met",
    statement: "Log authentication, authorization, administrative, and data-access events from every production component.",
    impl: { status: "implemented", responsibility: "provider", owner: "secops", narrative: "CloudTrail organization trail, VPC flow logs, and Okta System Log stream to the security data lake." },
    maps: [[R171 + "03-03-01", "equivalent-to", true], [R53 + "au-2", "equivalent-to", true]],
  },
  {
    slug: "audit-review", display: "LOG-02", name: "Audit log review", family: "Logging and monitoring",
    type: "detective", frequency: "weekly",
    statement: "Review high-risk audit events {{ review_frequency }} and record the review.",
    params: { review_frequency: { label: "review frequency" } },
    state: "gap", failed: ["Evidence weekly-log-review-2026-w43 expired on 2026-10-31"],
    impl: { status: "implemented", responsibility: "provider", owner: "secops", paramValues: { review_frequency: "weekly" }, narrative: "The on-call analyst reviews the high-risk events dashboard every Monday and attaches the signed review." },
    maps: [[R171 + "03-03-05", "equivalent-to", true], [R53 + "au-6", "equivalent-to", true]],
  },
  {
    slug: "security-monitoring", display: "LOG-03", name: "Security monitoring", family: "Logging and monitoring",
    type: "detective", frequency: "continuous", state: "met",
    statement: "Monitor the system for attacks and indicators of compromise and alert Security operations.",
    impl: { status: "implemented", responsibility: "provider", owner: "secops", narrative: "GuardDuty and the SIEM detection rules page the on-call analyst through PagerDuty." },
    maps: [[R171 + "03-14-06", "equivalent-to", true], [R53 + "si-4", "equivalent-to", true]],
  },
  {
    slug: "change-control", display: "CHG-01", name: "Configuration change control", family: "Change management",
    type: "preventive", frequency: "event-driven",
    statement: "Every change to production is reviewed by a second engineer and deployed through the pipeline.",
    state: "gap", failed: ["Required test change-review-enforced has no methodology defined"],
    impl: { status: "planned", responsibility: "provider", owner: "platform", byAgent: true, narrative: "GitHub branch protection on main requires one approving review and passing CI. Terraform applies run only from the pipeline role." },
    maps: [[R171 + "03-04-03", "equivalent-to", true], [R53 + "cm-3", "subset-of", true]],
  },
  {
    slug: "least-functionality", display: "CHG-02", name: "Least functionality", family: "Change management",
    type: "preventive", frequency: "quarterly", state: "met",
    statement: "Production images contain only the packages and ports the service needs.",
    impl: { status: "implemented", responsibility: "provider", owner: "platform", narrative: "Distroless base images, and a CI check that fails on unexpected listening ports." },
    maps: [[R171 + "03-04-06", "equivalent-to", true], [R53 + "cm-7", "equivalent-to", true]],
  },
  {
    slug: "encryption-at-rest", display: "DAT-01", name: "Encryption at rest", family: "Data protection",
    type: "preventive", frequency: "continuous", state: "met",
    statement: "Encrypt customer data at rest with keys held in the cloud key management service.",
    impl: { status: "implemented", responsibility: "provider", owner: "platform", narrative: "RDS, S3, and EBS use KMS customer-managed keys. An SCP denies creating unencrypted volumes." },
    maps: [[R171 + "03-13-08", "subset-of", true], [R53 + "sc-28", "equivalent-to", true]],
  },
  {
    slug: "encryption-in-transit", display: "DAT-02", name: "Encryption in transit", family: "Data protection",
    type: "preventive", frequency: "continuous", state: "met",
    statement: "Use TLS 1.2 or later on every external and internal connection that carries customer data.",
    impl: { status: "implemented", responsibility: "provider", owner: "platform", narrative: "ALB security policy ELBSecurityPolicy-TLS13-1-2-2021-06. Service mesh enforces mTLS." },
    maps: [[R171 + "03-13-08", "subset-of", true], [R53 + "sc-8", "equivalent-to", true]],
  },
  {
    slug: "crypto-modules", display: "DAT-03", name: "Validated cryptography", family: "Data protection",
    type: "preventive", frequency: "annual", state: "met",
    statement: "Use FIPS 140-validated modules where cryptography protects CUI.",
    impl: { status: "implemented", responsibility: "provider", owner: "platform", narrative: "FIPS endpoints are configured for KMS and S3. Application TLS terminates on FIPS-mode load balancers." },
    maps: [[R171 + "03-13-11", "equivalent-to", true], [R53 + "sc-13", "equivalent-to", true]],
  },
  {
    slug: "media-sanitization", display: "DAT-04", name: "Media sanitization", family: "Data protection",
    type: "corrective", frequency: "event-driven", state: "out_of_scope",
    statement: "Sanitize media that held customer data before disposal or reuse.",
    impl: { status: "not-applicable", responsibility: "provider", owner: "platform", narrative: "The system has no organization-owned storage media. Cloud media is the subservice provider's responsibility." },
    maps: [[R171 + "03-08-03", "equivalent-to", true], [R53 + "mp-6", "equivalent-to", true]],
  },
  {
    slug: "backups", display: "RES-01", name: "Encrypted backups", family: "Resilience",
    type: "corrective", frequency: "daily", state: "waived",
    statement: "Back up production data daily to a separate account, encrypted, and test a restore quarterly.",
    impl: { status: "exception", responsibility: "provider", owner: "platform", narrative: "Daily AWS Backup plans copy to the backup account. Cross-account restore testing is waived until the Q1 migration." },
    maps: [[R171 + "03-08-09", "intersects-with", true], [R53 + "cp-9", "equivalent-to", true]],
  },
  {
    slug: "incident-handling", display: "INC-01", name: "Incident handling", family: "Incident response",
    type: "corrective", frequency: "annual", state: "met",
    statement: "Maintain an incident response plan and exercise it at least annually.",
    impl: { status: "implemented", responsibility: "provider", owner: "secops", narrative: "The incident response plan is in the policy repository. The 2026 tabletop covered a credential-stuffing scenario." },
    maps: [[R171 + "03-06-01", "equivalent-to", true], [R53 + "ir-4", "equivalent-to", true]],
  },
  {
    slug: "incident-reporting", display: "INC-02", name: "Incident reporting", family: "Incident response",
    type: "corrective", frequency: "event-driven", state: "gap",
    failed: ["Required test ir-reporting-drill is not passing (latest result: error)"],
    statement: "Report suspected incidents to the incident response team within one hour, and to customers as contracts require.",
    impl: { status: "implemented", responsibility: "provider", owner: "secops", narrative: "#sec-incident in Slack and security@ page on-call. Customer notification templates are kept in the runbook." },
    maps: [[R171 + "03-06-02", "equivalent-to", true], [R53 + "ir-6", "equivalent-to", true]],
  },
  {
    slug: "physical-access", display: "PHY-01", name: "Physical access", family: "Physical",
    type: "preventive", frequency: "annual", state: "out_of_scope",
    statement: "Restrict physical access to facilities that house system components.",
    impl: { status: "implemented", responsibility: "subservice", owner: "platform", narrative: "Carried by AWS data centers. See the AWS SOC 2 report in the provider bundle." },
    maps: [[R171 + "03-10-01", "equivalent-to", true], [R53 + "pe-3", "equivalent-to", true]],
  },
  {
    slug: "vulnerability-scanning", display: "VUL-01", name: "Vulnerability scanning", family: "Vulnerability management",
    type: "detective", frequency: "weekly", state: "met",
    statement: "Scan hosts, containers, and dependencies at least weekly and when new vulnerabilities are announced.",
    impl: { status: "implemented", responsibility: "provider", owner: "secops", narrative: "Inspector scans hosts and ECR images. Dependabot covers application dependencies." },
    maps: [[R171 + "03-11-02", "equivalent-to", true], [R53 + "ra-5", "equivalent-to", true]],
  },
  {
    slug: "flaw-remediation", display: "VUL-02", name: "Flaw remediation", family: "Vulnerability management",
    type: "corrective", frequency: "weekly", state: "gap",
    failed: ["Required test critical-cves-patched is not passing (latest result: fail)"],
    statement: "Remediate critical vulnerabilities within {{ critical_sla }} and high within {{ high_sla }}.",
    params: { critical_sla: { label: "critical remediation time" }, high_sla: { label: "high remediation time" } },
    impl: { status: "implemented", responsibility: "provider", owner: "platform", paramValues: { critical_sla: "15 days", high_sla: "30 days" }, narrative: "Findings open Jira tickets with due dates from the SLA. Weekly triage in the platform sync." },
    maps: [[R171 + "03-14-01", "equivalent-to", true], [R53 + "si-2", "equivalent-to", true]],
  },
  {
    slug: "malware-protection", display: "VUL-03", name: "Malware protection", family: "Vulnerability management",
    type: "preventive", frequency: "continuous", state: "met",
    statement: "Run malware protection on endpoints and scan uploaded files.",
    impl: { status: "implemented", responsibility: "provider", owner: "secops", narrative: "EDR on every laptop through MDM. Uploads are scanned before they reach the customer bucket." },
    maps: [[R171 + "03-14-02", "equivalent-to", true], [R53 + "si-3", "equivalent-to", true]],
  },
  {
    slug: "risk-assessment", display: "RSK-01", name: "Risk assessment", family: "Risk management",
    type: "detective", frequency: "annual", state: "met",
    statement: "Assess risk to the system annually and after significant change, and record it in the risk register.",
    impl: { status: "implemented", responsibility: "provider", owner: "priya-shah", narrative: "The 2026 assessment is recorded as risks in OpenGRC. Owners review treatments monthly." },
    maps: [[R171 + "03-11-01", "equivalent-to", true], [R53 + "ra-3", "equivalent-to", true]],
  },
  {
    slug: "vendor-review", display: "VEN-01", name: "External service providers", family: "Third parties", origin: "custom",
    type: "preventive", frequency: "annual", state: "met",
    statement: "Review the security posture of providers that process customer data before onboarding and annually.",
    impl: { status: "implemented", responsibility: "provider", owner: "priya-shah", narrative: "Provider bundles for AWS and Okta are imported. Their SOC 2 reports are reviewed each year." },
    maps: [[R171 + "03-16-03", "equivalent-to", true], [R53 + "sa-9", "equivalent-to", true]],
  },
  {
    slug: "security-training", display: "HR-01", name: "Security awareness training", family: "People",
    type: "preventive", frequency: "annual", state: "met",
    statement: "Train every workforce member on security at onboarding and annually.",
    impl: { status: "implemented", responsibility: "provider", owner: "sam-okafor", narrative: "Training is assigned in the LMS at onboarding and every October. Completion exports are attached as evidence." },
    maps: [[R171 + "03-02-01", "equivalent-to", true], [R53 + "at-2", "subset-of", true]],
  },
  {
    slug: "security-policies", display: "GOV-01", name: "Security policies", family: "Governance", origin: "custom",
    type: "preventive", frequency: "annual", state: "met",
    statement: "Maintain adopted security policies and procedures, and review them annually.",
    impl: { status: "implemented", responsibility: "provider", owner: "priya-shah", narrative: "Policies are adopted in OpenGRC and reviewed each January." },
    maps: [[R171 + "03-15-01", "subset-of", true]],
  },
];

export const controls: Control[] = specs.map((s) => ({
  ...envelope("control", s.slug, LIB_TS),
  display_id: s.display,
  name: s.name,
  origin: s.origin ?? "standard",
  family: s.family,
  control_type: s.type,
  frequency: s.frequency,
  statement: s.statement,
  objective: `${s.name} is in place and operating.`,
  parameters: s.params,
}));

export const implementations: Implementation[] = specs.map((s, i) => ({
  ...envelope("implementation", `acme-platform-${s.slug}`, at(-90 + i), at(-3 - (i % 9), `14:02:${String(10 + i).padStart(2, "0")}.482Z`)),
  system_ref: SYSTEM_ID,
  control_ref: `control--${s.slug}`,
  status: s.impl.status,
  responsibility: s.impl.responsibility,
  origin: "organization",
  owner_ref: P(s.impl.owner),
  narrative: s.impl.narrative,
  parameter_values: s.impl.paramValues,
  created_by_ref: s.impl.byAgent ? AGENT_PARTY : P("jordan-lee"),
  customer_responsibility: undefined,
}));

// The provider's half of the shared MFA control (RFC 0001 section 8).
implementations.push({
  ...envelope("implementation", "okta-mfa-privileged", LIB_TS),
  component_ref: "component--okta",
  control_ref: "control--mfa-privileged",
  status: "implemented",
  responsibility: "shared",
  origin: "provider",
  narrative: "Okta provides phishing-resistant authenticators and policy enforcement.",
  customer_responsibility: "Assign privileged groups to an authentication policy that requires phishing-resistant authenticators.",
});

const implFor = (slug: string) => `implementation--acme-platform-${slug}`;

// Mappings -----------------------------------------------------------------

export const mappings: Mapping[] = specs.flatMap((s) =>
  s.maps.map(([target, relationship, reviewed]) => ({
    ...envelope("mapping", `${s.slug}_to_${target.replace("requirement--", "")}`, LIB_TS),
    source_ref: `control--${s.slug}`,
    target_ref: target,
    relationship,
    rationale: "functional" as const,
    review_status: reviewed ? ("reviewed" as const) : ("draft" as const),
    confidence: reviewed ? ("high" as const) : ("medium" as const),
  })),
);

// Tests, results, evidence -------------------------------------------------

type TestSpec = {
  slug: string;
  control: string;
  name: string;
  method: Test["method"];
  interval: Test["interval"];
  outcome?: Result["outcome"];
  observed?: number;
  summary?: string;
  noRun?: boolean;
};

const testSpecs: TestSpec[] = [
  { slug: "access-review-complete", control: "account-lifecycle", name: "Quarterly access review completed", method: "manual", interval: "quarterly", outcome: "pass", observed: -40 },
  { slug: "mfa-enforced", control: "mfa-privileged", name: "Privileged groups require phishing-resistant MFA", method: "automated", interval: "daily", outcome: "fail", observed: -1, summary: "2 of 14 privileged users can sign in with SMS." },
  { slug: "mfa-config-review", control: "mfa-privileged", name: "Okta authentication policy reviewed", method: "manual", interval: "quarterly", outcome: "pass", observed: -56 },
  { slug: "jit-access-only", control: "least-privilege", name: "No standing admin permission sets", method: "automated", interval: "daily", outcome: "pass", observed: 0 },
  { slug: "no-public-admin-ports", control: "remote-access", name: "No security group allows 22 or 3389 from anywhere", method: "automated", interval: "continuous", outcome: "pass", observed: 0 },
  { slug: "password-policy", control: "authenticator-management", name: "Okta password policy meets minimums", method: "automated", interval: "weekly", outcome: "pass", observed: -2 },
  { slug: "cloudtrail-enabled", control: "event-logging", name: "Organization CloudTrail is on and immutable", method: "automated", interval: "daily", outcome: "pass", observed: 0 },
  { slug: "weekly-log-review", control: "audit-review", name: "Weekly high-risk event review signed", method: "manual", interval: "weekly", outcome: "pass", observed: -16 },
  { slug: "guardduty-enabled", control: "security-monitoring", name: "GuardDuty enabled in all regions", method: "automated", interval: "daily", outcome: "pass", observed: 0 },
  { slug: "change-review-enforced", control: "change-control", name: "Branch protection requires review", method: "automated", interval: "daily", noRun: true },
  { slug: "image-ports", control: "least-functionality", name: "Images expose only declared ports", method: "automated", interval: "daily", outcome: "pass", observed: 0 },
  { slug: "storage-encrypted", control: "encryption-at-rest", name: "All volumes and buckets use KMS keys", method: "automated", interval: "daily", outcome: "pass", observed: 0 },
  { slug: "tls-policy", control: "encryption-in-transit", name: "Load balancers use TLS 1.2+ policy", method: "automated", interval: "daily", outcome: "pass", observed: 0 },
  { slug: "fips-endpoints", control: "crypto-modules", name: "FIPS endpoints configured", method: "automated", interval: "weekly", outcome: "pass", observed: -3 },
  { slug: "backup-plan", control: "backups", name: "Backup plan covers production resources", method: "automated", interval: "daily", outcome: "pass", observed: 0 },
  { slug: "ir-tabletop", control: "incident-handling", name: "Annual tabletop exercise held", method: "manual", interval: "annual", outcome: "pass", observed: -62 },
  { slug: "ir-reporting-drill", control: "incident-reporting", name: "Paging drill reaches on-call in 15 minutes", method: "automated", interval: "monthly", outcome: "error", observed: -4, summary: "PagerDuty API returned 401. The integration key was rotated." },
  { slug: "inspector-scans", control: "vulnerability-scanning", name: "Inspector scanned all hosts in 7 days", method: "automated", interval: "weekly", outcome: "pass", observed: -1 },
  { slug: "critical-cves-patched", control: "flaw-remediation", name: "No critical CVE open past SLA", method: "automated", interval: "daily", outcome: "fail", observed: 0, summary: "3 critical findings past 15 days on ECR image api:2026.10.3." },
  { slug: "edr-coverage", control: "malware-protection", name: "EDR installed on every managed laptop", method: "automated", interval: "daily", outcome: "pass", observed: 0 },
  { slug: "risk-register-reviewed", control: "risk-assessment", name: "Risk register reviewed this year", method: "manual", interval: "annual", outcome: "pass", observed: -100 },
  { slug: "provider-reports-current", control: "vendor-review", name: "Provider SOC 2 reports current", method: "manual", interval: "annual", outcome: "pass", observed: -30 },
  { slug: "training-completion", control: "security-training", name: "Training completion at 100%", method: "manual", interval: "annual", outcome: "pass", observed: -20 },
  { slug: "policy-review", control: "security-policies", name: "Policies reviewed this year", method: "manual", interval: "annual", outcome: "pass", observed: -280 },
];

export const tests: Test[] = testSpecs.map((t) => ({
  ...envelope("test", t.slug, at(-150)),
  name: t.name,
  control_ref: `control--${t.control}`,
  method: t.method,
  interval: t.interval,
  required: true,
  run: t.method === "automated" && !t.noRun ? { runner: "shell", command: `./checks/${t.slug}.sh` } : undefined,
}));

export const results: Result[] = testSpecs
  .filter((t) => t.outcome)
  .map((t) => ({
    ...envelope("result", `${t.slug}-latest`, at(t.observed ?? 0, "06:00:00Z")),
    test_ref: `test--${t.slug}`,
    implementation_ref: implFor(t.control),
    observed: at(t.observed ?? 0, "06:00:00Z"),
    outcome: t.outcome!,
    summary: t.summary,
    evidence_refs: [`evidence--${t.slug}-output`],
    created_by_ref: t.method === "automated" ? "party--harness" : P("secops"),
  }));

function evidence(
  slug: string,
  control: string,
  name: string,
  method: Evidence["method"],
  collected: number,
  validUntil: number,
  media = "application/json",
): Evidence {
  return {
    ...envelope("evidence", slug, at(collected)),
    name,
    method,
    collected: at(collected),
    valid_from: day(collected),
    valid_until: day(validUntil),
    implementation_ref: implFor(control),
    resource: {
      uri: `s3://acme-opengrc-evidence/${slug}`,
      media_type: media,
      digest: { algorithm: "sha-256", value: "9f2c4e1ab0d73f5e8c61a2b4d07e9f13c5a8b6d2e4f1a3c7b9d0e2f4a6c8b1d3" },
    },
  };
}

export const evidenceItems: Evidence[] = [
  ...testSpecs
    .filter((t) => t.outcome)
    .map((t) => {
      const window = { continuous: 1, daily: 1, weekly: 7, monthly: 30, quarterly: 90, annual: 365, "event-driven": 30 }[t.interval ?? "daily"];
      const e = evidence(`${t.slug}-output`, t.control, `${t.slug} output`, t.method === "automated" ? "automated" : "attestation", t.observed ?? 0, (t.observed ?? 0) + window);
      return { ...e, result_ref: `result--${t.slug}-latest` };
    }),
  evidence("weekly-log-review-2026-w43", "audit-review", "Weekly log review, 2026-W43", "upload", -24, -9, "application/pdf"),
  evidence("okta-soc2-2026", "mfa-privileged", "Okta SOC 2 Type II report", "upload", -60, 142, "application/pdf"),
  evidence("break-glass-attestation", "mfa-privileged", "Break-glass account attestation", "attestation", -78, 12, "text/markdown"),
  evidence("training-export-2026", "security-training", "LMS completion export, October 2026", "upload", -20, 18, "text/csv"),
  evidence("dr-runbook-link", "backups", "Disaster recovery runbook", "link", -40, 25, "text/html"),
];

// Exceptions, findings, risks ----------------------------------------------

export const exceptions: Exception[] = [
  {
    ...envelope("exception", "backups-restore-test", at(-35)),
    implementation_ref: implFor("backups"),
    justification: "Cross-account restore testing resumes after the Q1 database migration. Daily backups continue.",
    expires: day(22),
    approver_ref: P("priya-shah"),
    risk_ref: "risk--untested-restore",
  },
];

export const findings: Finding[] = [
  {
    ...envelope("finding", "2026-assessment-au-6", at(-14)),
    name: "Audit review records incomplete for October",
    system_ref: SYSTEM_ID,
    objective_ref: `${R171}03-03-05#a`,
    determination: "not-satisfied",
    observed: day(-14),
    narrative: "Two weekly reviews in October were not signed.",
    implementation_ref: implFor("audit-review"),
  },
];

export const risks: Risk[] = [
  {
    ...envelope("risk", "untested-restore", at(-35)), name: "Restore from backup not recently tested", system_ref: SYSTEM_ID,
    statement: "A restore could fail or exceed the recovery time objective because it has not been exercised since the migration began.",
    likelihood: 3, impact: 4, residual_likelihood: 2, residual_impact: 4, treatment: "mitigate", status: "treating",
    owner_ref: P("platform"), control_refs: ["control--backups"],
    milestones: [{ name: "Finish database migration", due: day(30) }, { name: "Run cross-account restore", due: day(45) }],
  },
  {
    ...envelope("risk", "sms-mfa-admins", at(-2)), name: "Privileged users can fall back to SMS", system_ref: SYSTEM_ID,
    statement: "Two administrators still have SMS enrolled, so a SIM swap could take over a privileged session.",
    likelihood: 2, impact: 5, treatment: "mitigate", status: "open", owner_ref: P("jordan-lee"), control_refs: ["control--mfa-privileged"],
  },
  {
    ...envelope("risk", "stale-images", at(-10)), name: "Container images carry unpatched critical CVEs", system_ref: SYSTEM_ID,
    statement: "Images older than the remediation SLA are still serving traffic.",
    likelihood: 3, impact: 3, treatment: "mitigate", status: "open", owner_ref: P("platform"), control_refs: ["control--flaw-remediation"],
  },
];

// Baselines and programs ---------------------------------------------------

const allControlRefs = controls.map((c) => c.id);

export const baselines: Baseline[] = [
  {
    ...envelope("baseline", "acme-800-171", at(-180)),
    name: "Acme 800-171 baseline",
    framework_refs: ["framework--nist-sp-800-171-r3"],
    control_refs: allControlRefs,
  },
  {
    ...envelope("baseline", "acme-800-53-moderate", at(-180)),
    name: "Acme 800-53 moderate subset",
    framework_refs: ["framework--nist-sp-800-53-r5"],
    control_refs: allControlRefs,
  },
];

export const programs: Program[] = [
  { ...envelope("program", "acme-platform-800-171", at(-180)), name: "NIST 800-171", system_ref: SYSTEM_ID, baseline_ref: "baseline--acme-800-171" },
  { ...envelope("program", "acme-platform-800-53", at(-180)), name: "NIST 800-53 moderate", system_ref: SYSTEM_ID, baseline_ref: "baseline--acme-800-53-moderate" },
];

/** Canned kernel output: control id → state and failed conditions. */
export const controlStates = new Map(
  specs.map((s) => [
    `control--${s.slug}`,
    { state: s.state, failed: s.failed ?? [], implementation_id: implFor(s.slug) },
  ]),
);

// Jobs ---------------------------------------------------------------------

export const jobs: Job[] = [
  { id: "job--0193-test-run-mfa", type: "test_run", status: "succeeded", created: at(-1, "06:00:00Z"), finished: at(-1, "06:00:41Z"), result_id: "result--mfa-enforced-latest" },
  { id: "job--0193-git-export", type: "git_export", status: "succeeded", created: at(0, "02:00:00Z"), finished: at(0, "02:01:12Z") },
  { id: "job--0193-ir-drill", type: "test_run", status: "failed", created: at(-4, "06:00:00Z"), finished: at(-4, "06:00:09Z"), error: { type: "urn:opengrc:problem:runner-error", title: "Runner exited with status 1", status: 500 } },
  { id: "job--0193-library-pull", type: "library_pull", status: "succeeded", created: at(-18, "10:12:00Z"), finished: at(-18, "10:14:51Z") },
];
