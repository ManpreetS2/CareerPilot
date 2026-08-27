import { z } from "zod";
import type { TargetPreferences } from "./types";
import { readRoleType, writeRoleType, type RoleTypeFilter } from "./job-role-type";

export const preferenceFormSchema = z.object({
  targetRoles: z.string().trim().min(1, "Enter at least one target role."),
  location: z.string(),
  salaryMin: z.string(),
  workAuth: z.string(),
  remotePreference: z.string(),
  legalName: z.string(),
  linkedinUrl: z.string(),
  githubUrl: z.string(),
  portfolioUrl: z.string(),
  earliestStartDate: z.string(),
  currentlyEnrolled: z.string(),
  expectedGraduation: z.string(),
  degreePursuing: z.string(),
  gender: z.string(),
  raceEthnicity: z.string(),
  veteranStatus: z.string(),
  disabilityStatus: z.string(),
  roleType: z.enum(["internships", "full_time", "both"]),
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

export function preferencesToForm(preferences: TargetPreferences | null): PreferenceFormValues {
  return {
    targetRoles: preferences?.target_roles?.join(", ") || "",
    location: preferences?.preferred_locations?.[0] || "",
    salaryMin:
      preferences?.salary_min == null ? "" : String(preferences.salary_min),
    workAuth: preferences?.work_authorization || "",
    remotePreference: preferences?.remote_preference || "",
    legalName: preferences?.legal_name || "",
    linkedinUrl: preferences?.linkedin_url || "",
    githubUrl: preferences?.github_url || "",
    portfolioUrl: preferences?.portfolio_url || "",
    earliestStartDate: preferences?.earliest_start_date || "",
    currentlyEnrolled: preferences?.currently_enrolled_in_program || "",
    expectedGraduation: preferences?.expected_graduation || "",
    degreePursuing: preferences?.degree_pursuing || "",
    gender: preferences?.gender || "",
    raceEthnicity: preferences?.race_ethnicity || "",
    veteranStatus: preferences?.veteran_status || "",
    disabilityStatus: preferences?.disability_status || "",
    roleType: readRoleType(preferences?.constraints),
  };
}

export function formToPreferences(
  values: PreferenceFormValues,
  previous?: TargetPreferences | null,
): TargetPreferences {
  const roles = values.targetRoles
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const annualSalary = values.salaryMin.trim() ? Number(values.salaryMin) : null;
  return {
    target_roles: roles,
    preferred_locations: values.location.trim() ? [values.location.trim()] : [],
    remote_preference: values.remotePreference || null,
    salary_min: annualSalary,
    work_authorization: values.workAuth || null,
    sponsorship_required: sponsorshipFromWorkAuth(values.workAuth),
    constraints: writeRoleType(previous?.constraints, values.roleType as RoleTypeFilter),
    legal_name: values.legalName.trim() || null,
    linkedin_url: values.linkedinUrl.trim() || null,
    github_url: values.githubUrl.trim() || null,
    portfolio_url: values.portfolioUrl.trim() || null,
    earliest_start_date: values.earliestStartDate.trim() || null,
    currently_enrolled_in_program: values.currentlyEnrolled || null,
    expected_graduation: values.expectedGraduation.trim() || null,
    degree_pursuing: values.degreePursuing.trim() || null,
    gender: values.gender || null,
    race_ethnicity: values.raceEthnicity || null,
    veteran_status: values.veteranStatus || null,
    disability_status: values.disabilityStatus || null,
  };
}
