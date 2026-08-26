import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { motion, useReducedMotion, LayoutGroup } from "motion/react";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { Sheet, SheetContent } from "../components/ui/sheet";
import { PageHeader } from "../components/ui/page-header";
import { Surface } from "../components/ui/surface";
import { Skeleton } from "../components/ui/skeleton";
import { api, ApiClientError } from "../lib/api";
import { cn } from "../lib/cn";
import { queryKeys } from "../lib/query-keys";
import type { ResumeVersionDetail, ResumeVersionProfile } from "../lib/types";

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function asRecords(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
}

function formatDate(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function ResumePreview({ detail }: { detail: ResumeVersionDetail }) {
  const profile: ResumeVersionProfile = detail.profile ?? {};
  const skills = asStringList(profile.skills);
  const certifications = asStringList(profile.certifications);
  const experience = asRecords(profile.experience);
  const projects = asRecords(profile.projects);
  const education = asRecords(profile.education);
  const links = [profile.linkedin_url, profile.github_url, profile.portfolio_url, ...asStringList(profile.evidence_links)].filter(
    Boolean,
  );

  return (
    <article className="space-y-6" data-testid="resume-preview">
      <header>
        <h2 className="font-display text-2xl font-semibold">{profile.name || "Candidate"}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {[profile.email, profile.phone].filter(Boolean).join(" · ") || "Contact not stored on this version"}
        </p>
      </header>

      {detail.tailored_bullets.length > 0 ? (
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Tailored bullets</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {detail.tailored_bullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Experience</h3>
        {experience.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">None on this snapshot.</p>
        ) : (
          <div className="mt-2 space-y-3">
            {experience.map((item, index) => (
              <div key={`${String(item.company)}-${index}`}>
                <p className="font-medium">{String(item.title ?? "Role")}</p>
                <p className="text-sm text-muted-foreground">{String(item.company ?? "")}</p>
                {Array.isArray(item.highlights) ? (
                  <ul className="mt-1 list-disc pl-5 text-sm">
                    {item.highlights.filter((h): h is string => typeof h === "string").map((h) => (
                      <li key={h}>{h}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Projects</h3>
        {projects.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">None on this snapshot.</p>
        ) : (
          <ul className="mt-2 space-y-2 text-sm">
            {projects.map((project, index) => (
              <li key={`${String(project.name)}-${index}`}>
                <p className="font-medium">{String(project.name ?? "Project")}</p>
                {typeof project.description === "string" ? (
                  <p className="text-muted-foreground">{project.description}</p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Skills</h3>
        <p className="mt-2 text-sm">{skills.length ? skills.join(" · ") : "None on this snapshot."}</p>
      </section>

      <section>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Education</h3>
        {education.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">None on this snapshot.</p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm">
            {education.map((edu, index) => (
              <li key={`${String(edu.institution)}-${index}`}>
                {String(edu.institution ?? "School")}
                {edu.degree ? ` · ${String(edu.degree)}` : ""}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Certifications</h3>
        <p className="mt-2 text-sm">{certifications.length ? certifications.join(" · ") : "None on this snapshot."}</p>
      </section>

      {links.length > 0 ? (
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Evidence / Links</h3>
          <ul className="mt-2 list-disc pl-5 text-sm">
            {links.map((link) => (
              <li key={String(link)}>{String(link)}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}

export function ResumePage() {
  const { versionId } = useParams();
  const navigate = useNavigate();
  const [detailsOpen, setDetailsOpen] = useState(false);
  const reduce = useReducedMotion();

  const listQuery = useQuery({
    queryKey: queryKeys.resumeVersions,
    queryFn: ({ signal }) => api.listAllResumeVersions({ signal }),
  });

  const versions = listQuery.data ?? [];
  const selectedId = versionId || versions[0]?.id;
  const detailQuery = useQuery({
    queryKey: queryKeys.resumeVersion(selectedId ?? ""),
    queryFn: ({ signal }) => api.getResumeVersionDetail(selectedId!, { signal }),
    enabled: Boolean(selectedId),
    retry: false,
  });

  const selected = useMemo(
    () => versions.find((item) => item.id === selectedId) ?? null,
    [versions, selectedId],
  );

  if (listQuery.isPending) {
    return (
      <div className="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]" aria-busy>
        <div className="space-y-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
        <Skeleton className="min-h-[28rem] w-full" />
      </div>
    );
  }
  if (listQuery.error) return <ErrorBanner error={listQuery.error} />;

  if (versions.length === 0) {
    return (
      <EmptyState
        title="No resume versions"
        description="Approve grounded materials for a job, then save an immutable resume version."
        action={
          <Link to="/jobs" className="btn-primary">
            Open jobs
          </Link>
        }
      />
    );
  }

  const missingDetail =
    detailQuery.error instanceof ApiClientError && detailQuery.error.status === 404;

  const library = (
    <nav aria-label="Resume versions" className="space-y-1" data-testid="resume-version-list">
      {versions.map((version) => {
        const active = version.id === selectedId;
        return (
          <Link
            key={version.id}
            to={`/resume/${version.id}`}
            className={cn(
              "block rounded-[var(--radius-sm)] border px-3 py-2.5 text-sm",
              active ? "border-primary/40 bg-primary/10" : "border-transparent hover:bg-muted",
            )}
            aria-current={active ? "page" : undefined}
          >
            <motion.span
              layoutId={reduce ? undefined : `resume-meta-${version.id}`}
              className="block"
            >
              <span className="flex items-center justify-between gap-2">
                <span className="font-semibold tabular">Version {version.version_number}</span>
                <span className="text-xs text-muted-foreground tabular">
                  {new Date(version.created_at).toLocaleDateString()}
                </span>
              </span>
              <span className="mt-0.5 block truncate text-muted-foreground">
                {version.company} · {version.job_title}
              </span>
            </motion.span>
            <span className="mt-1 block text-xs text-muted-foreground">
              {version.matches_current_profile ? "Matches current profile" : "Historical snapshot"}
            </span>
          </Link>
        );
      })}
    </nav>
  );

  const preview = (
    <Surface className="p-6">
      {selected ? (
        <motion.div layoutId={reduce ? undefined : `resume-meta-${selected.id}`} className="mb-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Version {selected.version_number}
          </p>
          <p className="text-sm text-muted-foreground">
            {selected.company} · {selected.job_title}
          </p>
        </motion.div>
      ) : null}
      {detailQuery.isPending ? (
        <LoadingState label="Loading resume…" />
      ) : missingDetail ? (
        <p className="text-sm text-muted-foreground">This resume version was not found.</p>
      ) : detailQuery.error ? (
        <ErrorBanner error={detailQuery.error} />
      ) : detailQuery.data ? (
        <ResumePreview detail={detailQuery.data} />
      ) : null}
      <button type="button" className="btn-secondary mt-6" onClick={() => setDetailsOpen(true)}>
        Version details
      </button>
    </Surface>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Resume"
        description="Immutable approved snapshots. Each preview uses the historical profile stored with that version."
      />

      <LayoutGroup>
      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[18rem_minmax(0,1fr)]">
        <div className={versionId ? "hidden lg:block" : "block"}>
          <Surface className="p-3">{library}</Surface>
        </div>
        <div className={!versionId ? "hidden lg:block" : "block"}>
          {versionId ? (
            <button
              type="button"
              className="btn-ghost mb-3 px-0 lg:hidden"
              onClick={() => navigate("/resume")}
            >
              Back to versions
            </button>
          ) : null}
          {preview}
        </div>
      </div>
      </LayoutGroup>

      <Sheet open={detailsOpen} onOpenChange={setDetailsOpen}>
        <SheetContent side="right" title="Version details" className="glass-floating">
          {selected ? (
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-muted-foreground">Version</dt>
                <dd className="tabular font-medium">{selected.version_number}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Linked job</dt>
                <dd>
                  <Link className="text-primary" to={`/jobs/${selected.job_id}`}>
                    {selected.job_title} · {selected.company}
                  </Link>
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Saved</dt>
                <dd className="tabular">{formatDate(selected.created_at)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Provenance</dt>
                <dd>Approved snapshot</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Current-profile match</dt>
                <dd>{selected.matches_current_profile ? "Yes" : "No"}</dd>
              </div>
              {detailQuery.data?.source_traceability_notes?.length ? (
                <div>
                  <dt className="text-muted-foreground">Traceability notes</dt>
                  <dd>
                    <ul className="mt-1 list-disc pl-5">
                      {detailQuery.data.source_traceability_notes.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  </dd>
                </div>
              ) : null}
            </dl>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
