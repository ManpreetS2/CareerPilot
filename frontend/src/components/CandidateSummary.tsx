import type { CandidateProfile, TargetPreferences } from "../lib/types";

export function CandidateSummary({
  candidate,
  preferences,
}: {
  candidate: CandidateProfile;
  preferences?: TargetPreferences | null;
}) {
  return (
    <div className="space-y-6">
      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Overview</h2>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-sm text-ink-500">Name</dt>
            <dd className="font-medium">{candidate.name}</dd>
          </div>
          <div>
            <dt className="text-sm text-ink-500">Email</dt>
            <dd className="font-medium">{candidate.email || "—"}</dd>
          </div>
          <div>
            <dt className="text-sm text-ink-500">Phone</dt>
            <dd className="font-medium">{candidate.phone || "—"}</dd>
          </div>
          <div>
            <dt className="text-sm text-ink-500">Target roles</dt>
            <dd className="font-medium">
              {preferences?.target_roles?.length
                ? preferences.target_roles.join(", ")
                : "—"}
            </dd>
          </div>
        </dl>
      </section>

      <ChipSection title="Skills" items={candidate.skills} />
      <ChipSection title="Strengths" items={candidate.strengths} />
      <ChipSection title="Certifications" items={candidate.certifications} />

      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Experience</h2>
        <div className="mt-4 space-y-4">
          {candidate.experience.length === 0 ? (
            <p className="text-sm text-ink-500">No experience listed.</p>
          ) : (
            candidate.experience.map((item) => (
              <div key={`${item.company}-${item.title}`} className="rounded-xl border border-[var(--line)] p-4">
                <h3 className="font-semibold">{item.title}</h3>
                <p className="text-sm text-ink-600 dark:text-ink-300">
                  {item.company}
                  {item.start_date || item.end_date
                    ? ` · ${item.start_date || "?"} – ${item.end_date || "Present"}`
                    : ""}
                </p>
                {item.highlights.length > 0 ? (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-700 dark:text-ink-200">
                    {item.highlights.map((highlight) => (
                      <li key={highlight}>{highlight}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))
          )}
        </div>
      </section>

      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Projects</h2>
        <div className="mt-4 space-y-4">
          {candidate.projects.length === 0 ? (
            <p className="text-sm text-ink-500">No projects listed.</p>
          ) : (
            candidate.projects.map((project) => (
              <div key={project.name} className="rounded-xl border border-[var(--line)] p-4">
                <h3 className="font-semibold">{project.name}</h3>
                {project.description ? (
                  <p className="mt-1 text-sm text-ink-600 dark:text-ink-300">{project.description}</p>
                ) : null}
                {project.technologies.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {project.technologies.map((tech) => (
                      <span
                        key={tech}
                        className="rounded-lg bg-ink-100 px-2.5 py-1 text-xs font-medium text-ink-700 dark:bg-ink-800 dark:text-ink-100"
                      >
                        {tech}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))
          )}
        </div>
      </section>

      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Education</h2>
        <div className="mt-4 space-y-3">
          {candidate.education.length === 0 ? (
            <p className="text-sm text-ink-500">No education listed.</p>
          ) : (
            candidate.education.map((edu) => (
              <div key={`${edu.institution}-${edu.degree}`} className="rounded-xl border border-[var(--line)] p-4">
                <h3 className="font-semibold">{edu.institution}</h3>
                <p className="text-sm text-ink-600 dark:text-ink-300">
                  {[edu.degree, edu.field, edu.graduation_year].filter(Boolean).join(" · ") || "—"}
                </p>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function ChipSection({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="card p-6">
      <h2 className="font-display text-2xl font-semibold">{title}</h2>
      {items.length === 0 ? (
        <p className="mt-3 text-sm text-ink-500">None listed.</p>
      ) : (
        <div className="mt-4 flex flex-wrap gap-2">
          {items.map((item) => (
            <span
              key={item}
              className="rounded-lg bg-accent-50 px-2.5 py-1 text-xs font-semibold text-accent-800 dark:bg-accent-900/30 dark:text-accent-200"
            >
              {item}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
