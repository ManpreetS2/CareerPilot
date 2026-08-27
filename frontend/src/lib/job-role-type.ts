export type RoleTypeFilter = "internships" | "full_time" | "both";

const ROLE_TYPE_PREFIX = "role_type:";

/** Mirrors backend `_role_is_internship`: title/seniority only, no invented fields. */
export function jobLooksLikeInternship(title: string, seniority?: string | null): boolean {
  const seniorityKey = (seniority || "").trim().toLowerCase();
  if (seniorityKey === "intern" || seniorityKey === "internship" || seniorityKey === "intern-level") {
    return true;
  }
  return /\bintern(?:s|ship)?\b/i.test(title || "");
}

export function matchesRoleTypeFilter(
  title: string,
  filter: RoleTypeFilter,
  seniority?: string | null,
): boolean {
  if (filter === "both") return true;
  const internship = jobLooksLikeInternship(title, seniority);
  return filter === "internships" ? internship : !internship;
}

export function readRoleType(constraints: string[] | undefined | null): RoleTypeFilter {
  const found = (constraints ?? []).find((item) => item.startsWith(ROLE_TYPE_PREFIX));
  if (found === `${ROLE_TYPE_PREFIX}internships`) return "internships";
  if (found === `${ROLE_TYPE_PREFIX}full_time`) return "full_time";
  return "both";
}

export function writeRoleType(
  constraints: string[] | undefined | null,
  roleType: RoleTypeFilter,
): string[] {
  const rest = (constraints ?? []).filter((item) => !item.startsWith(ROLE_TYPE_PREFIX));
  return [...rest, `${ROLE_TYPE_PREFIX}${roleType}`];
}

export const CURATED_ROLES = [
  "Software Engineer Intern",
  "Software Engineer",
  "Frontend Engineer",
  "Backend Engineer",
  "Full-Stack Engineer",
  "Data Analyst Intern",
  "Data Analyst",
  "Data Scientist",
  "Machine Learning Engineer",
  "Product Manager Intern",
  "Product Manager",
  "UX Designer",
  "Security Engineer",
];
