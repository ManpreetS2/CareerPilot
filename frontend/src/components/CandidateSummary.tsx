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
        <h2 className="font-display text-2xl font-semibold">Identity</h2>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-sm text-muted-foreground">Name</dt>
            <dd className="font-medium">{candidate.name}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Email</dt>
            <dd className="font-medium">{candidate.email || "—"}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Phone</dt>
            <dd className="font-medium">{candidate.phone || "—"}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Target roles</dt>
            <dd className="font-medium">
              {preferences?.target_roles?.length
                ? preferences.target_roles.join(", ")
                : "—"}
            </dd>
          </div>
        </dl>
      </section>

      <ChipSection title="Skills" items={candidate.skills} />
      <ChipSection title="Certifications" items={candidate.certifications} />
      <ChipSection title="Evidence / Links" items={candidate.evidence_links} />

      <section className="card p-6">
        <h2 className="font-display text-2xl font-semibold">Experience</h2>
        <div className="mt-4 space-y-4">
          {candidate.experience.length === 0 ? (
            <p className="text-sm text-muted-foreground">No experience listed.</p>
          ) : (
            candidate.experience.map((item) => (
              <div key={`${item.company}-${item.title}`} className="rounded-xl border border-[var(--line)] p-4">
                <h3 className="font-semibold">{item.title}</h3>
                <p className="text-sm text-muted-foreground">
                  {item.company}
                  {item.start_date || item.end_date
                    ? ` · ${item.start_date || "?"} – ${item.end_date || "Present"}`
                    : ""}
                </p>
                {item.highlights.length > 0 ? (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-foreground">
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
            <p className="text-sm text-muted-foreground">No projects listed.</p>
          ) : (
            candidate.projects.map((project) => (
              <div key={project.name} className="rounded-xl border border-[var(--line)] p-4">
                <h3 className="font-semibold">{project.name}</h3>
                {project.description ? (
                  <p className="mt-1 text-sm text-muted-foreground">{project.description}</p>
                ) : null}
                {project.technologies.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {project.technologies.map((tech) => (
                      <span
                        key={tech}
                        className="rounded-lg bg-muted px-2.5 py-1 text-xs font-medium text-foreground"
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
            <p className="text-sm text-muted-foreground">No education listed.</p>
          ) : (
            candidate.education.map((edu) => (
              <div key={`${edu.institution}-${edu.degree}`} className="rounded-xl border border-[var(--line)] p-4">
                <h3 className="font-semibold">{edu.institution}</h3>
                <p className="text-sm text-muted-foreground">
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
        <p className="mt-3 text-sm text-muted-foreground">None listed.</p>
      ) : (
        <div className="mt-4 flex flex-wrap gap-2">
          {items.map((item) => (
            <span
              key={item}
              className="chip"
            >
              {item}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
