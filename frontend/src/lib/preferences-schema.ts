import { z } from "zod";
import type { TargetPreferences } from "./types";
import { readRoleType, writeRoleType, type RoleTypeFilter } from "./job-role-type";

export const preferenceFormSchema = z.object({
  targetRoles: z.array(z.string().trim().min(1)).min(1, "Enter at least one target role."),
  locations: z.array(z.string()),
  salaryMin: z.string(),
  workAuth: z.string(),
  workModes: z.array(z.string()),
  legalName: z.string(),
  linkedinUrl: z.string(),
  githubUrl: z.string(),
  portfolioUrl: z.string(),
  earliestStartDate: z.string(),
  currentlyEnrolled: z.string(),
  expectedGraduation: z.string(),
  degreePursuing: z.string(),
  academicYear: z.string(),
  fieldOfStudy: z.string(),
  industries: z.array(z.string()),
  experienceLevels: z.array(z.string()),
  opportunityPreference: z.enum(["internships", "roles", "both"]),
  skills: z.array(z.string()),
  gender: z.string(),
  raceEthnicity: z.string(),
  veteranStatus: z.string(),
  disabilityStatus: z.string(),
}).superRefine((value, ctx) => {
  if (!value.salaryMin.trim()) return;
  const annual = Number(value.salaryMin);
  if (Number.isNaN(annual) || annual < 10000 || annual > 1_000_000) {
    ctx.addIssue({
      code: "custom",
      path: ["salaryMin"],
      message: "Minimum base salary must be an annual USD amount between 10,000 and 1,000,000.",
    });
  }
});

export type PreferenceFormValues = z.infer<typeof preferenceFormSchema>;

export function sponsorshipFromWorkAuth(workAuth: string): boolean | null {
  if (workAuth === "Requires sponsorship") return true;
  if (workAuth === "US Citizen" || workAuth === "US Permanent Resident") return false;
  return null;
}

export function opportunityToRoleType(value: PreferenceFormValues["opportunityPreference"]): RoleTypeFilter {
  if (value === "internships") return "internships";
  if (value === "roles") return "full_time";
  return "both";
}

export function roleTypeToOpportunity(value: RoleTypeFilter): PreferenceFormValues["opportunityPreference"] {
  if (value === "internships") return "internships";
  if (value === "full_time") return "roles";
  return "both";
}

export function remotePreferenceFromWorkModes(modes: string[]): string | null {
  const set = new Set(modes.map((item) => item.toLowerCase()));
  if (set.has("remote") && set.has("hybrid") && !set.has("onsite")) return "hybrid_or_remote";
  if (set.size === 1 && set.has("remote")) return "remote";
  if (set.size === 1 && set.has("hybrid")) return "hybrid";
  if (set.size === 1 && set.has("onsite")) return "onsite";
  if (set.has("remote")) return "hybrid_or_remote";
  return modes[0] || null;
}

function opportunityFromPreferences(preferences: TargetPreferences | null): PreferenceFormValues["opportunityPreference"] {
  const stored = preferences?.opportunity_preference?.trim().toLowerCase();
  if (stored === "internships" || stored === "roles" || stored === "both") return stored;
  return roleTypeToOpportunity(readRoleType(preferences?.constraints));
}

export function preferencesToForm(preferences: TargetPreferences | null): PreferenceFormValues {
  const workModes = preferences?.work_mode_preferences?.filter(Boolean) ?? [];
  const remote = preferences?.remote_preference;
  return {
    targetRoles: preferences?.target_roles?.filter(Boolean) ?? [],
    locations: preferences?.preferred_locations?.filter(Boolean) ?? [],
    salaryMin: preferences?.salary_min == null ? "" : String(preferences.salary_min),
    workAuth: preferences?.work_authorization || "",
    workModes: workModes.length
      ? workModes
      : remote
        ? remote === "hybrid_or_remote"
          ? ["hybrid", "remote"]
          : [remote]
        : [],
    legalName: preferences?.legal_name || "",
    linkedinUrl: preferences?.linkedin_url || "",
    githubUrl: preferences?.github_url || "",
    portfolioUrl: preferences?.portfolio_url || "",
    earliestStartDate: preferences?.earliest_start_date || "",
    currentlyEnrolled: preferences?.currently_enrolled_in_program || "",
    expectedGraduation: preferences?.expected_graduation || "",
    degreePursuing: preferences?.degree_pursuing || "",
    academicYear: preferences?.academic_year || "",
    fieldOfStudy: preferences?.field_of_study || "",
    industries: preferences?.industry_preferences?.filter(Boolean) ?? [],
    experienceLevels: preferences?.experience_levels?.filter(Boolean) ?? [],
    opportunityPreference: opportunityFromPreferences(preferences),
    skills: preferences?.skill_preferences?.filter(Boolean) ?? [],
    gender: preferences?.gender || "",
    raceEthnicity: preferences?.race_ethnicity || "",
    veteranStatus: preferences?.veteran_status || "",
    disabilityStatus: preferences?.disability_status || "",
  };
}

export function formToPreferences(
  values: PreferenceFormValues,
  previous?: TargetPreferences | null,
): TargetPreferences {
  const annualSalary = values.salaryMin.trim() ? Number(values.salaryMin) : null;
  return {
    target_roles: values.targetRoles.map((item) => item.trim()).filter(Boolean),
    preferred_locations: values.locations.map((item) => item.trim()).filter(Boolean),
    remote_preference: remotePreferenceFromWorkModes(values.workModes),
    salary_min: annualSalary,
    work_authorization: values.workAuth || null,
    sponsorship_required: sponsorshipFromWorkAuth(values.workAuth),
    constraints: writeRoleType(previous?.constraints, opportunityToRoleType(values.opportunityPreference)),
    legal_name: values.legalName.trim() || null,
    linkedin_url: values.linkedinUrl.trim() || null,
    github_url: values.githubUrl.trim() || null,
    portfolio_url: values.portfolioUrl.trim() || null,
    earliest_start_date: values.earliestStartDate.trim() || null,
    currently_enrolled_in_program: values.currentlyEnrolled || null,
    expected_graduation: values.expectedGraduation.trim() || null,
    degree_pursuing: values.degreePursuing.trim() || null,
    academic_year: values.academicYear.trim() || null,
    work_mode_preferences: values.workModes,
    field_of_study: values.fieldOfStudy.trim() || null,
    industry_preferences: values.industries.map((item) => item.trim()).filter(Boolean),
    opportunity_preference: values.opportunityPreference,
    experience_levels: values.experienceLevels.map((item) => item.trim()).filter(Boolean),
    skill_preferences: values.skills.map((item) => item.trim()).filter(Boolean),
    gender: values.gender || null,
    race_ethnicity: values.raceEthnicity || null,
    veteran_status: values.veteranStatus || null,
    disability_status: values.disabilityStatus || null,
  };
}
