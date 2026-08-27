import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Save } from "lucide-react";
import { ErrorBanner } from "./ErrorBanner";
import { LockIn } from "./signature/LockIn";
import {
  formToPreferences,
  preferenceFormSchema,
  preferencesToForm,
  type PreferenceFormValues,
} from "../lib/preferences-schema";
import { CURATED_ROLES } from "../lib/job-role-type";
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
      className="space-y-4"
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
          <label>
            <span className="label">Target roles</span>
            <input className="input" {...form.register("targetRoles")} placeholder="Add a role, then press a suggestion or type your own" />
          </label>
          <div className="mt-2 flex flex-wrap gap-2">
            {CURATED_ROLES.map((role) => (
              <button
                key={role}
                type="button"
                className="rounded-full border border-border px-2.5 py-1 text-xs hover:bg-muted"
                onClick={() => {
                  const current = form.getValues("targetRoles");
                  const parts = current.split(",").map((item) => item.trim()).filter(Boolean);
                  if (!parts.some((item) => item.toLowerCase() === role.toLowerCase())) {
                    form.setValue("targetRoles", [...parts, role].join(", "), { shouldValidate: true });
                  }
                }}
              >
                {role}
              </button>
            ))}
          </div>
        </div>
        <label>
          <span className="label">Preferred location</span>
          <input className="input" {...form.register("location")} placeholder="City, state, or Remote" />
        </label>
        <label>
          <span className="label">Role type</span>
          <select className="input" {...form.register("roleType")}>
            <option value="both">Internships and full-time</option>
            <option value="internships">Internships</option>
            <option value="full_time">Full-time roles</option>
          </select>
        </label>
        <label>
          <span className="label">Minimum base salary (annual USD)</span>
          <input className="input tabular" type="number" min={10000} max={1000000} step={5000} {...form.register("salaryMin")} />
          <span className="mt-1 block text-xs text-muted-foreground">
            {salaryPreview ?? "Enter an annual amount (for example 100000)."}
          </span>
        </label>
        <label>
          <span className="label">Work authorization</span>
          <select className="input" {...form.register("workAuth")}>
            <option value="">Select work authorization…</option>
            <option value="US Citizen">US Citizen</option>
            <option value="US Permanent Resident">US Permanent Resident</option>
            <option value="Requires sponsorship">Requires sponsorship</option>
            <option value="Other">Other</option>
          </select>
        </label>
        <label>
          <span className="label">Remote preference</span>
          <select className="input" {...form.register("remotePreference")}>
            <option value="">No preference selected…</option>
            <option value="remote">Remote</option>
            <option value="hybrid_or_remote">Hybrid or remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">Onsite</option>
          </select>
        </label>
        <label>
          <span className="label">Legal name (if different)</span>
          <input className="input" {...form.register("legalName")} />
        </label>
        <label>
          <span className="label">LinkedIn URL</span>
          <input className="input" {...form.register("linkedinUrl")} />
        </label>
        <label>
          <span className="label">GitHub URL</span>
          <input className="input" {...form.register("githubUrl")} />
        </label>
        <label>
          <span className="label">Portfolio / website URL</span>
          <input className="input" {...form.register("portfolioUrl")} />
        </label>
        <label>
          <span className="label">Earliest start date</span>
          <input className="input" {...form.register("earliestStartDate")} />
        </label>
        <label>
          <span className="label">Currently enrolled in a program?</span>
          <select className="input" {...form.register("currentlyEnrolled")}>
            <option value="">Select…</option>
            <option value="Yes">Yes</option>
            <option value="No">No</option>
          </select>
        </label>
        <label>
          <span className="label">Expected graduation</span>
          <input className="input" {...form.register("expectedGraduation")} />
        </label>
        <label>
          <span className="label">Degree currently pursuing</span>
          <input className="input" {...form.register("degreePursuing")} />
        </label>
      </div>

      <div className="border-t border-border pt-4">
        <h3 className="font-display text-lg font-semibold">Voluntary self-identification</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Optional. Saved answers stay private to you and are not required to use CareerPilot.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label>
            <span className="label">Gender</span>
            <select className="input" {...form.register("gender")}>
              <option value="">Prefer not to say</option>
              <option value="Male">Male</option>
              <option value="Female">Female</option>
              <option value="Non-binary">Non-binary</option>
            </select>
          </label>
          <label>
            <span className="label">Hispanic or Latino</span>
            <select className="input" {...form.register("raceEthnicity")}>
              <option value="">Prefer not to say</option>
              <option value="Yes">Yes</option>
              <option value="No">No</option>
            </select>
          </label>
          <label>
            <span className="label">Veteran status</span>
            <select className="input" {...form.register("veteranStatus")}>
              <option value="">I don&apos;t wish to answer</option>
              <option value="I am not a protected veteran">I am not a protected veteran</option>
              <option value="I identify as one or more of the classifications of a protected veteran">
                I identify as a protected veteran
              </option>
            </select>
          </label>
          <label>
            <span className="label">Disability status</span>
            <select className="input" {...form.register("disabilityStatus")}>
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

      <button type="submit" className="btn-secondary" disabled={saving}>
        <Save className="h-4 w-4" aria-hidden />
        {saving ? "Saving…" : "Save job preferences"}
      </button>
    </form>
  );
}
