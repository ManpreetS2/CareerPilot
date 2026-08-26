import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { CheckCircle2 } from "lucide-react";
import { IntelligenceField } from "../components/signature/IntelligenceField";
import { MagneticLink } from "../components/signature/MagneticLink";
import { PointerHalo } from "../components/signature/PointerHalo";
import { ScoreOrb } from "../components/signature/ScoreOrb";
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

const EVIDENCE = [
  { id: "resume", label: "Resume evidence", detail: "Parsed skills and experience" },
  { id: "job", label: "Job requirements", detail: "Stored posting, not invented" },
  { id: "score", label: "Fit score", detail: "Only when you calculate" },
  { id: "material", label: "Approved material", detail: "Locked after review" },
];

function ProductPreview() {
  const { reducedMotion } = useTheme();
  const ref = useRef<HTMLDivElement>(null);
  const live = !reducedMotion && hasFinePointer();

  useEffect(() => {
    if (!live) return;
    const el = ref.current;
    if (!el) return;
    let frame = 0;
    const onMove = (event: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const rect = el.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / Math.max(rect.width, 1) - 0.5) * 7;
        const y = ((event.clientY - rect.top) / Math.max(rect.height, 1) - 0.5) * -7;
        el.style.transform = `perspective(1200px) rotateX(${y}deg) rotateY(${x}deg)`;
      });
    };
    const onLeave = () => {
      cancelAnimationFrame(frame);
      el.style.transform = "perspective(1200px) rotateX(0deg) rotateY(0deg)";
    };
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(frame);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [live]);

  return (
    <div
      ref={ref}
      className="relative"
      data-testid="product-preview"
      style={live ? { transformStyle: "preserve-3d" } : undefined}
    >
      <Glass variant="floating" refract className="rounded-[1.4rem] p-3 sm:p-4">
        <div className="grid min-w-0 gap-3 sm:grid-cols-[5.25rem_minmax(0,1fr)]">
          <aside className="hidden rounded-[var(--radius-md)] border border-border/70 bg-background/40 p-2 sm:block">
            <p className="px-1 text-[10px] font-semibold tracking-tight">CP</p>
            <ol className="mt-3 space-y-1.5 text-[10px] text-muted-foreground">
              <li className="rounded bg-primary/10 px-1.5 py-1 font-medium text-foreground">Overview</li>
              <li className="px-1.5 py-1">Discover</li>
              <li className="px-1.5 py-1">Analyze</li>
              <li className="px-1.5 py-1">Prepare</li>
              <li className="px-1.5 py-1">Track</li>
            </ol>
          </aside>
          <div className="min-w-0 space-y-3">
            <div className="rounded-[var(--radius-md)] border border-border/70 bg-background/50 p-3">
              <p className="cp-kicker">Next action</p>
              <p className="mt-1 font-display text-sm font-semibold">Open analysis for Platform Engineer</p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Stored score is ready. Scoring never runs until you ask.
              </p>
            </div>
            <div className="flex min-w-0 items-start gap-3 rounded-[var(--radius-md)] border border-border/70 bg-background/50 p-3">
              <ScoreOrb score={86} />
              <div className="min-w-0">
                <p className="wrap-anywhere font-display text-sm font-semibold">Platform Engineer</p>
                <p className="text-xs text-muted-foreground">Northwind · Remote</p>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                  Python and distributed systems appear in the parsed experience snapshot.
                </p>
              </div>
            </div>
            <div className="rounded-[var(--radius-md)] border border-accent/30 bg-accent/10 px-3 py-2 text-[11px]">
              Resume version 4 locked after human approval.
            </div>
          </div>
        </div>
      </Glass>
    </div>
  );
}

export function LandingPage() {
  const reduce = useReducedMotion();

  return (
    <div className="cp-atmosphere relative min-h-screen bg-background">
      <PointerHalo />
      <IntelligenceField />
      <header className="safe-pad relative z-10 mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
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

      <main className="safe-pad relative z-10 mx-auto max-w-6xl px-4 pb-16 sm:px-6">
        <section className="grid items-start gap-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] lg:gap-12 lg:py-6">
          <div className="min-w-0">
            <p className="cp-kicker">{APP_NAME} · Career navigation</p>
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
              CareerPilot guides you from a cited profile through discovery, analysis, preparation, and
              tracking. It never submits an application for you.
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
                { id: "discover", label: "Discover", state: "complete" },
                { id: "analyze", label: "Analyze", state: "current" },
                { id: "prepare", label: "Prepare", state: "upcoming" },
                { id: "track", label: "Track", state: "upcoming" },
              ]}
            />
            <ol className="mt-6 grid gap-2 sm:grid-cols-2" data-testid="evidence-signals">
              {EVIDENCE.map((item, index) => (
                <li
                  key={item.id}
                  className="glass-atmosphere min-w-0 rounded-[var(--radius-md)] px-3 py-2.5"
                >
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {String(index + 1).padStart(2, "0")} · {item.label}
                  </p>
                  <p className="mt-1 text-sm">{item.detail}</p>
                </li>
              ))}
            </ol>
          </div>
          <ProductPreview />
        </section>

        <section className="mt-10 divide-y divide-border border-y border-border">
          {capabilities.map((item) => (
            <article key={item.title} className="grid gap-2 py-5 sm:grid-cols-[minmax(0,16rem)_1fr] sm:gap-8">
              <h2 className="font-display text-base font-semibold">{item.title}</h2>
              <p className="text-sm leading-relaxed text-muted-foreground">{item.body}</p>
            </article>
          ))}
        </section>

        <p className="mt-8 flex items-start gap-2 text-sm text-muted-foreground">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />
          Human approval is required. CareerPilot never automatically submits an application.
        </p>
      </main>
    </div>
  );
}
