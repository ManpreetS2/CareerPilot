import { Link } from "react-router-dom";
import { APP_NAME, APP_TAGLINE } from "../lib/config";
import { useAuth } from "../lib/auth";

export function PrivacyPage() {
  const { user } = useAuth();

  return (
    <div className="min-h-[100dvh] bg-background text-foreground">
      <header className="safe-pad border-b border-border">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-5 sm:px-6">
          <Link to="/" className="font-display text-lg font-semibold tracking-tight">
            {APP_NAME}
          </Link>
          <nav className="flex items-center gap-3 text-sm">
            {user ? (
              <Link to="/settings" className="font-medium text-muted-foreground hover:text-foreground">
                Settings
              </Link>
            ) : (
              <>
                <Link to="/login" className="font-medium text-muted-foreground hover:text-foreground">
                  Log in
                </Link>
                <Link to="/signup" className="font-semibold text-primary">
                  Sign up
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <main className="safe-pad mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <article className="space-y-8 rounded-[var(--radius-lg)] border border-border bg-card p-6 text-sm leading-relaxed sm:p-8">
          <header className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{APP_TAGLINE}</p>
            <h1 className="font-display text-3xl font-semibold tracking-tight">Privacy</h1>
            <p className="text-muted-foreground">
              CareerPilot is a local, source-visible job-search copilot. This page describes what
              the current software stores and where data can go when you use a feature. It is not a
              certification, and it does not claim production cloud infrastructure that this
              repository does not provide.
            </p>
          </header>

          <section className="space-y-2">
            <h2 className="font-display text-xl font-semibold">Where data lives</h2>
            <p>
              By default CareerPilot stores account and application data in a local SQLite database
              on the machine running the API (<span className="font-mono text-xs">data/careerpilot.db</span>
              ). There is no CareerPilot-operated cloud account in this codebase. If you configure
              third-party AI providers, those providers receive only the content required for the
              feature you explicitly run.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="font-display text-xl font-semibold">Information CareerPilot can store</h2>
            <p>If you use the corresponding feature, CareerPilot may store:</p>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              <li>Account email and a hashed password (not the password itself)</li>
              <li>Server-side session records (hashed session tokens)</li>
              <li>Candidate profile: name, contact fields, skills, education, experience, projects</li>
              <li>Resume file contents used to build that profile (parsed in memory; not written as a trusted filename on disk)</li>
              <li>Job preferences, including optional work authorization, sponsorship, salary minimum, and optional manually entered EEO answers</li>
              <li>Saved jobs, Fit/Match scores, and Match/Evidence snapshots (private to you)</li>
              <li>Generated application materials, approval state, tracker rows, resume versions, interview prep</li>
              <li>Assisted-apply / extension autofill attempt records (CareerPilot never submits the application)</li>
            </ul>
            <p>
              Job postings and extracted job requirements are a shared catalog. They are not deleted
              when you delete your account merely because you viewed or scored them.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="font-display text-xl font-semibold">AI providers</h2>
            <p>
              Depending on configuration, CareerPilot may send relevant content to Ollama, Gemini,
              Anthropic, and/or OpenAI. Ollama is typically a local/private model endpoint. Configured
              cloud providers may receive the minimum content required for the requested feature.
            </p>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              <li>Resume parsing / candidate profile extraction: resume text</li>
              <li>Job intelligence and requirement extraction: the job posting text, not your resume</li>
              <li>Application materials: stored candidate evidence, job posting/intelligence, and allowlisted preferences (not EEO or salary)</li>
              <li>Interview answer feedback: the question, your answer, role context, and listed skills</li>
            </ul>
            <p>
              Fit scoring is deterministic and does not call an AI provider. Job discovery (Find Jobs)
              queries public job-source APIs and does not send your resume to those sources. Interview
              prep generation is deterministic on the current product path.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="font-display text-xl font-semibold">Job sources</h2>
            <p>
              CareerPilot may fetch public job-posting data from Greenhouse, Lever, Remotive, Adzuna,
              RemoteOK, Jobicy, and Himalayas, or from a posting URL you paste. Those sources are not
              sent your resume by CareerPilot.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="font-display text-xl font-semibold">Sensitive preferences</h2>
            <p>
              Work authorization, sponsorship, salary, and EEO fields are manual. CareerPilot does
              not infer race, ethnicity, gender, disability, or veteran status. EEO answers are not
              used to rank jobs and are not sent to AI providers or job-discovery APIs.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="font-display text-xl font-semibold">Retention and deletion</h2>
            <p>
              CareerPilot keeps your private records until you delete your account or the local
              database file is removed. There is no automatic retention timer in this software.
              Signed-in users can delete their account and private data from Settings → Privacy &amp;
              Safety. That action removes owner-scoped records and revokes every session for that
              account. Shared job catalog rows remain.
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="font-display text-xl font-semibold">What this page does not claim</h2>
            <p className="text-muted-foreground">
              CareerPilot does not claim end-to-end encryption, SOC 2, HIPAA, GDPR certification,
              or CCPA certification. Public source on GitHub is not a license to copy the product.
              Opening this page does not search for jobs, score listings, or change your account.
            </p>
          </section>
        </article>
      </main>
    </div>
  );
}
