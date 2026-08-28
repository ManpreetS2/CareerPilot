import type { JobSearchIntent } from "./types";

export type { JobSearchIntent as SearchIntent };

const LOCATION_ALIASES: Array<[RegExp, string]> = [
  [/\b(?:sf\s+)?bay\s+area\b|\bsan\s+francisco\s+bay\b|\bsilicon\s+valley\b/i, "San Francisco Bay Area"],
  [/\bsan\s+francisco\b/i, "San Francisco"],
  [/\bnew\s+york(?:\s+city)?\b|\bnyc\b|\bmanhattan\b/i, "New York"],
  [/\blos\s+angeles\b/i, "Los Angeles"],
  [/\bseattle\b/i, "Seattle"],
  [/\baustin\b/i, "Austin"],
  [/\bboston\b/i, "Boston"],
  [/\bchicago\b/i, "Chicago"],
  [/\bdenver\b/i, "Denver"],
  [/\batlanta\b/i, "Atlanta"],
  [/\bremote\s+us\b|\bunited\s+states\b/i, "United States"],
];

const INDUSTRY_ALIASES: Array<[RegExp, string]> = [
  [/\bfintech\b|\bfinancial\s+tech/i, "fintech"],
  [/\bhealth(?:care)?\s*tech\b|\bhealthtech\b/i, "healthtech"],
  [/\bclimate\s*tech\b|\bclimatetech\b/i, "climatetech"],
  [/\bedtech\b|\beducation\s+tech/i, "edtech"],
  [/\bsaas\b/i, "saas"],
];

const ROLE_ALIASES: Array<[RegExp, string]> = [
  [/\bsoftware\s+engineers?\b|\bsoftware\s+engineering\b|\bswe\b/i, "Software Engineering"],
  [/\bbackend\b/i, "Backend"],
  [/\bfrontend\b|\bfront-end\b/i, "Frontend"],
  [/\bfull[\s-]?stack\b/i, "Full-Stack"],
  [/\bdata\s+scientist\b|\bdata\s+science\b/i, "Data Science"],
  [/\bdata\s+analyst\b|\bdata\s+analytics\b/i, "Data Analyst"],
  [/\bmachine\s+learning\b|\bml\s+engineer\b/i, "Machine Learning"],
  [/\bproduct\s+manager\b/i, "Product Manager"],
  [/\bux\s+design/i, "UX Design"],
  [/\bsecurity\s+engineer\b/i, "Security Engineering"],
];

const EXPERIENCE: Array<[string, string]> = [
  ["principal", "principal"],
  ["staff", "staff"],
  ["director", "director"],
  ["manager", "manager"],
  ["senior", "senior"],
  ["lead", "lead"],
  ["junior", "junior"],
  ["entry-level", "entry"],
  ["entry level", "entry"],
  ["new grad", "new_grad"],
  ["new-grad", "new_grad"],
  ["intern", "intern"],
];

function emptyIntent(): JobSearchIntent {
  return {
    roles: [],
    locations: [],
    opportunity_types: [],
    employment_types: [],
    experience_levels: [],
    work_modes: [],
    remote_scopes: [],
    industries: [],
    skills: [],
    verified_state: "all",
    eligibility_state: "all",
    confidence_state: "all",
    parser_ready: true,
    parser_source: "empty",
  };
}

function dedupe(values: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of values) {
    const key = item.trim().toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(item.trim());
  }
  return out;
}

export function parseSearchIntent(raw: string): JobSearchIntent {
  const text = raw.trim();
  if (!text) return emptyIntent();
  const lowered = text.toLowerCase();
  const consumed: Array<[number, number]> = [];
  const mark = (match: RegExpMatchArray) => {
    if (match.index == null) return;
    consumed.push([match.index, match.index + match[0].length]);
  };

  const work_modes: string[] = [];
  const hybrid = lowered.match(/\bhybrid\b/);
  if (hybrid) {
    work_modes.push("hybrid");
    mark(hybrid);
  }
  const onsite = lowered.match(/\bon-?site\b|\bin[\s-]?office\b/);
  if (onsite) {
    work_modes.push("onsite");
    mark(onsite);
  }
  const remote = lowered.match(/\bremote\b/);
  if (remote) {
    work_modes.push("remote");
    mark(remote);
  }

  const employment_types: string[] = [];
  const opportunity_types: Array<"internship" | "role" | "unknown"> = [];
  const intern = lowered.match(/\bintern(?:s|ships?)?\b/);
  if (intern) {
    employment_types.push("internship");
    opportunity_types.push("internship");
    mark(intern);
  }
  const coop = lowered.match(/\bco-?ops?\b/);
  if (coop) {
    employment_types.push("co_op");
    opportunity_types.push("internship");
    mark(coop);
  }
  const newGrad = lowered.match(/\bnew[\s-]?grads?(?:uate)?s?\b/);
  if (newGrad) {
    employment_types.push("new_grad");
    opportunity_types.push("internship");
    mark(newGrad);
  }
  const fullTime = lowered.match(/\bfull[\s-]?time\b/);
  if (fullTime) {
    employment_types.push("full_time");
    if (!opportunity_types.includes("internship")) opportunity_types.push("role");
    mark(fullTime);
  }
  const partTime = lowered.match(/\bpart[\s-]?time\b/);
  if (partTime) {
    employment_types.push("part_time");
    mark(partTime);
  }
  const contract = lowered.match(/\bcontract\b/);
  if (contract) {
    employment_types.push("contract");
    mark(contract);
  }

  const remote_scopes: string[] = [];
  const remoteUs = lowered.match(/\bremote\s+(?:us|u\.s\.|united\s+states)\b/);
  if (remoteUs) {
    remote_scopes.push("United States only");
    mark(remoteUs);
  }

  const locations: string[] = [];
  for (const [pattern, label] of LOCATION_ALIASES) {
    const match = text.match(pattern);
    if (match?.index != null) {
      locations.push(label);
      consumed.push([match.index, match.index + match[0].length]);
    }
  }
  const industries: string[] = [];
  for (const [pattern, label] of INDUSTRY_ALIASES) {
    const match = text.match(pattern);
    if (match?.index != null) {
      industries.push(label);
      consumed.push([match.index, match.index + match[0].length]);
    }
  }
  const roles: string[] = [];
  for (const [pattern, label] of ROLE_ALIASES) {
    const match = text.match(pattern);
    if (match?.index != null) {
      roles.push(label);
      consumed.push([match.index, match.index + match[0].length]);
    }
  }

  const experience_levels: string[] = [];
  for (const [needle, label] of EXPERIENCE) {
    if (needle === "intern" && employment_types.includes("internship")) continue;
    const pattern = new RegExp(`\\b${needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
    const match = lowered.match(pattern);
    if (match?.index != null) {
      experience_levels.push(label);
      consumed.push([match.index, match.index + match[0].length]);
    }
  }

  const leftover = text.split("");
  for (const [start, end] of [...consumed].sort((a, b) => b[0] - a[0])) {
    leftover.splice(start, end - start, ...Array(end - start).fill(" "));
  }
  const leftoverText = leftover
    .join("")
    .replace(/\b(?:in|at|the|and|or|for|with|companies?|roles?|jobs?|looking|want(?:ed)?)\b/gi, " ")
    .replace(/[^\w+#.+]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  return {
    raw_query: text,
    query: leftoverText || null,
    roles: dedupe(roles),
    locations: dedupe(locations),
    opportunity_types: dedupe(opportunity_types) as JobSearchIntent["opportunity_types"],
    employment_types: dedupe(employment_types),
    experience_levels: dedupe(experience_levels),
    work_modes: dedupe(work_modes),
    remote_scopes: dedupe(remote_scopes),
    industries: dedupe(industries),
    skills: [],
    verified_state: "all",
    eligibility_state: "all",
    confidence_state: "all",
    parser_ready: true,
    parser_source: "deterministic",
  };
}

export function scoutTermsFromIntent(intent: JobSearchIntent): { what?: string; where?: string } {
  let queries = [...intent.roles];
  if (intent.opportunity_types.length === 1 && intent.opportunity_types[0] === "internship" && queries.length) {
    queries = queries.map((item) => (item.toLowerCase().includes("intern") ? item : `${item} intern`));
  }
  const what = queries[0] || intent.query || intent.raw_query || undefined;
  const where = intent.locations[0];
  return { what: what?.slice(0, 120), where };
}

export const CHIP_LABELS: Record<string, string> = {
  internship: "Internship",
  co_op: "Co-op",
  new_grad: "New Grad",
  full_time: "Full Time",
  part_time: "Part Time",
  contract: "Contract",
  hybrid: "Hybrid",
  onsite: "On-site",
  remote: "Remote",
  intern: "Intern",
  entry: "Entry",
  junior: "Junior",
  mid: "Mid",
  senior: "Senior",
  staff: "Staff",
  principal: "Principal",
  lead: "Lead",
  manager: "Manager",
  fintech: "Fintech",
  internship_opp: "Internships",
  role: "Roles",
  verified: "Verified Match",
  potential: "Potential Match",
  likely_eligible: "Eligible based on stated requirements",
  eligibility_uncertain: "Uncertain",
  likely_ineligible: "Likely ineligible",
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
  past_24h: "Past 24 hours",
  past_3d: "Past 3 days",
  past_7d: "Past 7 days",
  past_14d: "Past 14 days",
  past_30d: "Past 30 days",
};

export function chipLabel(value: string): string {
  return CHIP_LABELS[value] ?? value.replaceAll("_", " ");
}
