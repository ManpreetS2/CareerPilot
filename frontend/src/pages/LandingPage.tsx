import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { CheckCircle2 } from "lucide-react";
import { IntelligenceField } from "../components/signature/IntelligenceField";
import { MagneticLink } from "../components/signature/MagneticLink";
import { PointerHalo } from "../components/signature/PointerHalo";
import { WorkflowPath } from "../components/signature/WorkflowPath";
import { Glass } from "../components/ui/glass";
import { APP_NAME } from "../lib/config";
import { motionDuration, motionEase } from "../lib/motion";
import { hasFinePointer } from "../lib/pointer";
import { useTheme } from "../lib/theme";

const capabilities = [
  {
    title: "Grounded candidate profile",
    body: "Parse a real resume into structured experience CareerPilot can cite — never invented skills.",
  },
  {
    title: "Real job discovery",
    body: "Scout Greenhouse, Lever, Remotive, Adzuna, and RemoteOK, or paste a posting URL yourself.",
  },
  {
    title: "Explainable job fit",
    body: "Stored scores show matched, missing, and partial skills. Fit is calculated only when you ask.",
  },
  {
    title: "Human-approved materials",
    body: "Tailored bullets, cover letter, and recruiter message stay drafts until you review and approve.",
  },
  {
    title: "Assisted apply, no auto-submit",
    body: "CareerPilot can help fill Greenhouse and Lever forms. You always submit. Nothing is sent automatically.",
  },
];

function ProductPreview() {
  const { reducedMotion } = useTheme();
  const ref = useRef<HTMLDivElement>(null);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const live = !reducedMotion && hasFinePointer();

  useEffect(() => {
    if (!live) return;
    const el = ref.current;
    if (!el) return;
    const onMove = (event: PointerEvent) => {
      const rect = el.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width - 0.5) * 6;
      const y = ((event.clientY - rect.top) / rect.height - 0.5) * -6;
      setTilt({ x: y, y: x });
    };
    const onLeave = () => setTilt({ x: 0, y: 0 });
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [live]);

  return (
    <div
      ref={ref}
      className="relative mx-auto mt-10 max-w-xl"
      style={
        live
          ? {
              transform: `perspective(1200px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
              transformStyle: "preserve-3d",
            }
          : undefined
      }
    >
      <Glass variant="floating" refract className="rounded-[var(--radius-lg)] p-4 sm:p-5">
        <div className="grid gap-3 sm:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-[var(--radius-md)] border border-border bg-surface p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Job</p>
            <p className="mt-2 font-display text-sm font-semibold">Platform Engineer</p>
            <p className="text-xs text-muted-foreground">Northwind · Remote</p>
          </div>
          <div className="rounded-[var(--radius-md)] border border-border bg-surface p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Match</p>
            <p className="mt-2 font-display text-2xl font-semibold tabular">86%</p>
            <p className="text-xs text-muted-foreground">Skills and experience from stored profile evidence.</p>
          </div>
          <div className="rounded-[var(--radius-md)] border border-border bg-surface p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Evidence</p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              “Python” and “distributed systems” appear in the parsed experience snapshot.
            </p>
          </div>
          <div className="rounded-[var(--radius-md)] border border-border bg-surface p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Prepare / Resume</p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              Review tailored bullets, approve, then lock an immutable resume version.
            </p>
          </div>
        </div>
      </Glass>
    </div>
  );
}

export function LandingPage() {
  const reduce = useReducedMotion();

  return (
    <div className="relative min-h-screen overflow-hidden bg-background">
      <PointerHalo />
      <IntelligenceField />
      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <span className="font-display text-lg font-semibold tracking-tight">{APP_NAME}</span>
        <div className="flex gap-2">
          <Link to="/login" className="btn-ghost">
            Sign In
          </Link>
          <MagneticLink to="/signup" className="btn-primary">
            Get Started
          </MagneticLink>
        </div>
      </header>

      <main className="relative z-10 mx-auto max-w-6xl px-4 pb-16 sm:px-6">
        <section className="relative overflow-hidden rounded-[var(--radius-lg)] px-1 py-8 sm:px-4 sm:py-12">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-primary">{APP_NAME}</p>
          <h1 className="hero-fluid mt-4 max-w-3xl font-display font-semibold leading-[1.05] tracking-tight">
            <motion.span
              className="block"
              initial={reduce ? false : { opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: motionDuration.hero, ease: motionEase.expressive }}
            >
              Grounded job search.
            </motion.span>
            <motion.span
              className="mt-1 block"
              initial={reduce ? false : { opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: motionDuration.hero, ease: motionEase.expressive, delay: reduce ? 0 : 0.12 }}
            >
              Human-approved{" "}
              <span className="relative inline-block">
                applications
                <svg className="absolute -bottom-1 left-0 h-2 w-full text-accent" viewBox="0 0 120 8" aria-hidden>
                  <path
                    d="M2 6 C 30 1, 70 1, 118 6"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    className={reduce ? undefined : "path-stroke"}
                    pathLength={1}
                  />
                </svg>
              </span>
              .
            </motion.span>
          </h1>
          <motion.p
            className="mt-5 max-w-xl text-base text-muted-foreground sm:text-lg"
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: motionDuration.panel, ease: motionEase.standard, delay: reduce ? 0 : 0.22 }}
          >
            CareerPilot is a local copilot for grounded profiles, real job search, and approved
            application materials. It never submits an application for you.
          </motion.p>
          <div className="mt-7 flex flex-wrap gap-2">
            <MagneticLink to="/signup" className="btn-primary">
              Get Started
            </MagneticLink>
            <Link to="/login" className="btn-secondary">
              Sign In
            </Link>
          </div>
          <WorkflowPath
            className="mt-8"
            nodes={[
              { id: "profile", label: "Profile", state: "complete" },
              { id: "jobs", label: "Jobs", state: "complete" },
              { id: "match", label: "Match", state: "current" },
              { id: "prepare", label: "Prepare", state: "upcoming" },
              { id: "resume", label: "Resume", state: "upcoming" },
            ]}
          />
          <ProductPreview />
        </section>

        <section className="mt-8 divide-y divide-border border-y border-border">
          {capabilities.map((item) => (
            <article key={item.title} className="grid gap-2 py-5 sm:grid-cols-[minmax(0,16rem)_1fr] sm:gap-8">
              <h2 className="font-display text-base font-semibold">{item.title}</h2>
              <p className="text-sm leading-relaxed text-muted-foreground">{item.body}</p>
            </article>
          ))}
        </section>

        <p className="mt-8 flex items-center gap-2 text-sm text-muted-foreground">
          <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />
          Human approval is required. CareerPilot never automatically submits an application.
        </p>
      </main>
    </div>
  );
}
