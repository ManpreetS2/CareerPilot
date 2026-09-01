import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Save } from "lucide-react";
import { ErrorBanner } from "./ErrorBanner";
import { GuidedCombobox } from "./GuidedCombobox";
import { LockIn } from "./signature/LockIn";
import {
  formToPreferences,
  preferenceFormSchema,
  preferencesToForm,
  type PreferenceFormValues,
} from "../lib/preferences-schema";
import {
  ACADEMIC_YEARS,
  DEGREE_TYPES,
  EXPERIENCE_LEVELS,
  FIELDS_OF_STUDY,
  INDUSTRIES,
  OPPORTUNITY_PREFERENCES,
  SUGGESTED_LOCATIONS,
  SUGGESTED_SKILLS,
  TARGET_ROLES,
  WORK_SETUPS,
} from "../lib/profile-taxonomy";
import { isLegacyHourlySalary } from "../lib/session";
import type { TargetPreferences } from "../lib/types";

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

export function PreferenceForm({
  preferences,
  onSave,
  saving,
  error,
  success,
}: {
  preferences: TargetPreferences | null;
  onSave: (next: TargetPreferences) => Promise<void>;
  saving: boolean;
  error: unknown;
  success: string | null;
}) {
  const form = useForm<PreferenceFormValues>({
    resolver: zodResolver(preferenceFormSchema),
    defaultValues: preferencesToForm(
      preferences?.salary_min != null && isLegacyHourlySalary(preferences.salary_min)
        ? { ...preferences, salary_min: null }
        : preferences,
    ),
  });

  useEffect(() => {
    form.reset(
      preferencesToForm(
        preferences?.salary_min != null && isLegacyHourlySalary(preferences.salary_min)
          ? { ...preferences, salary_min: null }
          : preferences,
      ),
    );
  }, [form, preferences]);

  const salaryMin = form.watch("salaryMin");
  const salaryPreview = (() => {
    const value = Number(salaryMin);
    if (!salaryMin || Number.isNaN(value) || value < 10000) return null;
    return `${currency.format(value)}/year`;
  })();

  return (
    <form
      className="space-y-5"
      onSubmit={form.handleSubmit(async (values) => {
        await onSave(formToPreferences(values, preferences));
      })}
      noValidate
    >
      <ErrorBanner error={error} />
      {success ? <LockIn active message={success} /> : null}
      {form.formState.errors.targetRoles ? (
        <p className="text-sm text-danger" role="alert">
          {form.formState.errors.targetRoles.message}
        </p>
      ) : null}
      {form.formState.errors.salaryMin ? (
        <p className="text-sm text-danger" role="alert">
          {form.formState.errors.salaryMin.message}
        </p>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        <div className="md:col-span-2">
          <Controller
            control={form.control}
            name="targetRoles"
            render={({ field }) => (
              <GuidedCombobox
                id="pref-target-roles"
                label="Target roles"
                values={field.value}
                onChange={field.onChange}
                options={TARGET_ROLES}
                placeholder="Search roles or add your own"
              />
            )}
          />
        </div>
        <Controller
          control={form.control}
          name="fieldOfStudy"
          render={({ field }) => (
            <GuidedCombobox
              id="pref-major"
              label="Major / field of study"
              values={field.value ? [field.value] : []}
              onChange={(next) => field.onChange(next[0] ?? "")}
              options={FIELDS_OF_STUDY}
              multiple={false}
              placeholder="Search majors or add your own"
            />
          )}
        />
        <Controller
          control={form.control}
          name="degreePursuing"
          render={({ field }) => (
            <GuidedCombobox
              id="pref-degree"
              label="Degree type"
              values={field.value ? [field.value] : []}
              onChange={(next) => field.onChange(next[0] ?? "")}
              options={DEGREE_TYPES}
              multiple={false}
              placeholder="Search degrees or add your own"
            />
          )}
        />
        <Controller
          control={form.control}
          name="industries"
          render={({ field }) => (
            <GuidedCombobox
              id="pref-industries"
              label="Industries"
              values={field.value}
              onChange={field.onChange}
              options={INDUSTRIES}
              placeholder="Search industries or add your own"
            />
          )}
        />
        <Controller
          control={form.control}
          name="experienceLevels"
          render={({ field }) => (
            <GuidedCombobox
              id="pref-experience"
              label="Experience level"
              values={field.value}
              onChange={field.onChange}
              options={EXPERIENCE_LEVELS}
              placeholder="Search levels or add your own"
            />
          )}
        />
        <Controller
          control={form.control}
          name="workModes"
          render={({ field }) => (
            <GuidedCombobox
              id="pref-work-setup"
              label="Work setup"
              values={field.value}
              onChange={field.onChange}
              options={WORK_SETUPS}
              placeholder="Remote, hybrid, or onsite"
            />
          )}
        />
        <Controller
          control={form.control}
          name="opportunityPreference"
          render={({ field }) => (
            <GuidedCombobox
              id="pref-opportunity"
              label="Opportunity preference"
              values={field.value ? [field.value] : []}
              onChange={(next) => field.onChange((next[0] as PreferenceFormValues["opportunityPreference"]) || "both")}
              options={OPPORTUNITY_PREFERENCES}
              multiple={false}
              allowCustom={false}
              placeholder="Internships, roles, or both"
            />
          )}
        />
        <Controller
          control={form.control}
          name="academicYear"
          render={({ field }) => (
            <GuidedCombobox
              id="pref-academic-year"
              label="Academic year"
              values={field.value ? [field.value] : []}
              onChange={(next) => field.onChange(next[0] ?? "")}
              options={ACADEMIC_YEARS}
              multiple={false}
              placeholder="Year in program"
            />
          )}
        />
        <label>
          <span className="label">Expected graduation</span>
          <input
            className="input min-h-11"
            {...form.register("expectedGraduation")}
            placeholder="2027 or 2027-05"
          />
        </label>
        <div className="md:col-span-2">
          <Controller
            control={form.control}
            name="locations"
            render={({ field }) => (
              <GuidedCombobox
                id="pref-locations"
                label="Locations"
                values={field.value}
                onChange={field.onChange}
                options={SUGGESTED_LOCATIONS}
                placeholder="Search cities or add any location"
                description="Suggestions are optional. You can add any city or region."
              />
            )}
          />
        </div>
        <div className="md:col-span-2">
          <Controller
            control={form.control}
            name="skills"
            render={({ field }) => (
              <GuidedCombobox
                id="pref-skills"
                label="Skills"
                values={field.value}
                onChange={field.onChange}
                options={SUGGESTED_SKILLS}
                placeholder="Add a skill"
                description="Suggestions are a short CareerPilot list, not every possible skill."
              />
            )}
          />
        </div>
        <label>
          <span className="label">Minimum base salary (annual USD)</span>
          <input className="input min-h-11 tabular" type="number" min={10000} max={1000000} step={5000} {...form.register("salaryMin")} />
          <span className="mt-1 block text-xs text-muted-foreground">
            {salaryPreview ?? "Enter an annual amount (for example 100000)."}
          </span>
        </label>
        <label>
          <span className="label">Work authorization</span>
          <select className="input min-h-11" {...form.register("workAuth")}>
            <option value="">Select work authorization…</option>
            <option value="US Citizen">US Citizen</option>
            <option value="US Permanent Resident">US Permanent Resident</option>
            <option value="Requires sponsorship">Requires sponsorship</option>
            <option value="Other">Other</option>
          </select>
        </label>
        <label>
          <span className="label">Legal name (if different)</span>
          <input className="input min-h-11" {...form.register("legalName")} />
        </label>
        <label>
          <span className="label">LinkedIn URL</span>
          <input className="input min-h-11" {...form.register("linkedinUrl")} />
        </label>
        <label>
          <span className="label">GitHub URL</span>
          <input className="input min-h-11" {...form.register("githubUrl")} />
        </label>
        <label>
          <span className="label">Portfolio / website URL</span>
          <input className="input min-h-11" {...form.register("portfolioUrl")} />
        </label>
        <label>
          <span className="label">Earliest start date</span>
          <input className="input min-h-11" {...form.register("earliestStartDate")} />
        </label>
        <label>
          <span className="label">Currently enrolled in a program?</span>
          <select className="input min-h-11" {...form.register("currentlyEnrolled")}>
            <option value="">Select…</option>
            <option value="Yes">Yes</option>
            <option value="No">No</option>
          </select>
        </label>
      </div>

      <div className="border-t border-border pt-4">
        <h3 className="font-display text-lg font-semibold">Voluntary self-identification</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Optional. Saved answers stay private to you and are not required to use CareerPilot.
          These fields are never inferred.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label>
            <span className="label">Gender</span>
            <select className="input min-h-11" {...form.register("gender")}>
              <option value="">Prefer not to say</option>
              <option value="Male">Male</option>
              <option value="Female">Female</option>
              <option value="Non-binary">Non-binary</option>
            </select>
          </label>
          <label>
            <span className="label">Hispanic or Latino</span>
            <select className="input min-h-11" {...form.register("raceEthnicity")}>
              <option value="">Prefer not to say</option>
              <option value="Yes">Yes</option>
              <option value="No">No</option>
            </select>
          </label>
          <label>
            <span className="label">Veteran status</span>
            <select className="input min-h-11" {...form.register("veteranStatus")}>
              <option value="">I don&apos;t wish to answer</option>
              <option value="I am not a protected veteran">I am not a protected veteran</option>
              <option value="I identify as one or more of the classifications of a protected veteran">
                I identify as a protected veteran
              </option>
            </select>
          </label>
          <label>
            <span className="label">Disability status</span>
            <select className="input min-h-11" {...form.register("disabilityStatus")}>
              <option value="">I do not want to answer</option>
              <option value="Yes, I have a disability, or have had one in the past">
                Yes, I have (or have had) a disability
              </option>
              <option value="No, I do not have a disability and have not had one in the past">
                No, I do not have a disability
              </option>
            </select>
          </label>
        </div>
      </div>

      <button type="submit" className="btn-secondary min-h-11" disabled={saving}>
        <Save className="h-4 w-4" aria-hidden />
        {saving ? "Saving…" : "Save job preferences"}
      </button>
    </form>
  );
}
