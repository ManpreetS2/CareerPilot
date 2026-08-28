import { Sheet, SheetContent } from "./ui/sheet";
import type { JobsWorkspaceState } from "../lib/jobs-workspace";

const EMPLOYMENT = [
  ["internship", "Internship"],
  ["new_grad", "New Grad"],
  ["full_time", "Full Time"],
  ["part_time", "Part Time"],
  ["contract", "Contract"],
  ["co_op", "Co-op"],
] as const;

const EXPERIENCE = [
  ["intern", "Intern"],
  ["new_grad", "New Grad"],
  ["entry", "Entry"],
  ["junior", "Junior"],
  ["mid", "Mid"],
  ["senior", "Senior"],
  ["staff", "Staff"],
  ["principal", "Principal"],
  ["lead", "Lead"],
  ["manager", "Manager"],
] as const;

const WORK = [
  ["remote", "Remote"],
  ["hybrid", "Hybrid"],
  ["onsite", "On-site"],
] as const;

function toggle(list: string[] | undefined, value: string): string[] {
  const current = list ?? [];
  return current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
}

export function JobsFilterPanel({
  open,
  onOpenChange,
  state,
  onChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  state: JobsWorkspaceState;
  onChange: (patch: Partial<JobsWorkspaceState>) => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" title="Filters">
        <div className="space-y-6 text-sm">
          <fieldset>
            <legend className="mb-2 font-semibold">Opportunity</legend>
            <div className="flex flex-col gap-2">
              {(
                [
                  ["both", "Both"],
                  ["internship", "Internships"],
                  ["role", "Roles"],
                ] as const
              ).map(([value, label]) => (
                <label key={value} className="flex min-h-11 items-center gap-2">
                  <input
                    type="radio"
                    name="opportunity"
                    checked={(state.opportunity ?? "both") === value}
                    onChange={() => onChange({ opportunity: value, page: 1 })}
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="mb-2 font-semibold">Employment</legend>
            {EMPLOYMENT.map(([value, label]) => (
              <label key={value} className="flex min-h-11 items-center gap-2">
                <input
                  type="checkbox"
                  checked={(state.employment_type ?? []).includes(value)}
                  onChange={() => onChange({ employment_type: toggle(state.employment_type, value), page: 1 })}
                />
                {label}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend className="mb-2 font-semibold">Experience</legend>
            {EXPERIENCE.map(([value, label]) => (
              <label key={value} className="flex min-h-11 items-center gap-2">
                <input
                  type="checkbox"
                  checked={(state.experience_level ?? []).includes(value)}
                  onChange={() => onChange({ experience_level: toggle(state.experience_level, value), page: 1 })}
                />
                {label}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend className="mb-2 font-semibold">Work setup</legend>
            {WORK.map(([value, label]) => (
              <label key={value} className="flex min-h-11 items-center gap-2">
                <input
                  type="checkbox"
                  checked={(state.work_mode ?? []).includes(value)}
                  onChange={() => onChange({ work_mode: toggle(state.work_mode, value), page: 1 })}
                />
                {label}
              </label>
            ))}
          </fieldset>
          <label className="block space-y-1">
            <span className="font-semibold">Location</span>
            <input
              className="input"
              placeholder="San Francisco, Remote US…"
              value={state.location?.[0] ?? ""}
              onChange={(event) =>
                onChange({
                  location: event.target.value.trim() ? [event.target.value.trim()] : [],
                  page: 1,
                })
              }
            />
          </label>
          <fieldset>
            <legend className="mb-2 font-semibold">Verification</legend>
            {(
              [
                ["all", "All"],
                ["verified", "Verified Match"],
                ["potential", "Potential Match"],
              ] as const
            ).map(([value, label]) => (
              <label key={value} className="flex min-h-11 items-center gap-2">
                <input
                  type="radio"
                  name="verified"
                  checked={(state.verified_state ?? "all") === value}
                  onChange={() => onChange({ verified_state: value, page: 1 })}
                />
                {label}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend className="mb-2 font-semibold">Eligibility</legend>
            {(
              [
                ["all", "All"],
                ["likely_eligible", "Eligible based on stated requirements"],
                ["eligibility_uncertain", "Uncertain"],
                ["likely_ineligible", "Likely ineligible"],
              ] as const
            ).map(([value, label]) => (
              <label key={value} className="flex min-h-11 items-center gap-2">
                <input
                  type="radio"
                  name="eligibility"
                  checked={(state.eligibility ?? "all") === value}
                  onChange={() => onChange({ eligibility: value, page: 1 })}
                />
                {label}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend className="mb-2 font-semibold">Confidence</legend>
            {(
              [
                ["all", "All"],
                ["high", "High"],
                ["medium", "Medium"],
                ["low", "Low"],
              ] as const
            ).map(([value, label]) => (
              <label key={value} className="flex min-h-11 items-center gap-2">
                <input
                  type="radio"
                  name="confidence"
                  checked={(state.confidence ?? "all") === value}
                  onChange={() => onChange({ confidence: value, page: 1 })}
                />
                {label}
              </label>
            ))}
          </fieldset>
          <label className="block space-y-1">
            <span className="font-semibold">Date posted</span>
            <select
              className="input"
              value={state.date_posted ?? ""}
              onChange={(event) => onChange({ date_posted: event.target.value || undefined, page: 1 })}
            >
              <option value="">Any time</option>
              <option value="past_24h">Past 24 hours</option>
              <option value="past_3d">Past 3 days</option>
              <option value="past_7d">Past 7 days</option>
              <option value="past_14d">Past 14 days</option>
              <option value="past_30d">Past 30 days</option>
            </select>
          </label>
        </div>
      </SheetContent>
    </Sheet>
  );
}
