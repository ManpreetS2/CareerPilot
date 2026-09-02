import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight, CheckCircle2, Lock, Sparkles } from "lucide-react";
import { HeroAtmosphere } from "../components/HeroAtmosphere";
import { HeroBlackHole } from "../components/HeroBlackHole";
import { EncryptionSection } from "../components/EncryptionSection";
import { DottedGlobe } from "../components/DottedGlobe";
import { Glass } from "../components/ui/glass";
import { APP_NAME } from "../lib/config";

const capabilities = [
  {
    title: "Grounded candidate profile",
    body: "Parse a real resume into structured experience CareerPilot can cite — never invented skills.",
  },
  {
    title: "Real job discovery",
    body: "Scout Greenhouse, Lever, Remotive, Adzuna, and more, or paste a posting URL yourself.",
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
    body: "CareerPilot can help fill forms. You always submit. Nothing is sent automatically.",
  },
];

export function LandingPage() {
  const reduce = useReducedMotion();

  return (
    <div className="cp-atmosphere relative min-h-screen overflow-x-clip bg-background">
      <section className="relative h-[100svh] min-h-[36rem] overflow-x-clip overflow-y-hidden">
        <header className="safe-pad absolute inset-x-0 top-0 z-20 mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-5 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-accent">
              <span className="text-sm font-bold text-primary-foreground">CP</span>
            </div>
            <span className="font-display text-lg font-semibold tracking-tight text-foreground">
              {APP_NAME}
            </span>
          </div>
          <div className="flex gap-3">
            <Link
              to="/login"
              className="rounded-xl px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              Sign In
            </Link>
            <Link
              to="/signup"
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-primary to-accent px-5 py-2 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/25 transition-all hover:shadow-xl hover:shadow-primary/30"
            >
              Get Started
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </header>

        <HeroAtmosphere />
        <HeroBlackHole />

        <div className="safe-pad relative z-10 mx-auto flex h-full max-w-4xl flex-col items-center px-4 pb-[46%] pt-[4.75rem] text-center sm:px-6 sm:pt-24 lg:px-8">
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mb-4 inline-flex items-center gap-2 rounded-full border border-border bg-foreground/5 px-4 py-2 backdrop-blur-sm sm:mb-6"
          >
            <Sparkles className="h-4 w-4 text-accent" />
            <span className="text-sm font-medium text-foreground/90">AI-Powered Career Navigation</span>
          </motion.div>

          <motion.h1
            className="hero-fluid max-w-[18ch] font-bold leading-[1.05] tracking-tight text-foreground"
            initial={reduce ? false : { opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: reduce ? 0 : 0.1 }}
          >
            Find better roles with{" "}
            <span className="bg-gradient-to-r from-primary via-accent to-primary bg-clip-text text-transparent">
              CareerPilot
            </span>
          </motion.h1>

          <motion.p
            className="mx-auto mt-4 max-w-2xl text-base leading-relaxed text-muted-foreground sm:mt-6 sm:text-xl"
            initial={reduce ? false : { opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: reduce ? 0 : 0.2 }}
          >
            Turn your resume into smarter job matches. Know where you fit before you apply.
            Human-approved applications, never auto-submitted.
          </motion.p>

          <motion.div
            className="mt-7 flex flex-wrap items-center justify-center gap-3 sm:mt-10 sm:gap-4"
            initial={reduce ? false : { opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: reduce ? 0 : 0.3 }}
          >
            <Link
              to="/signup"
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-primary to-accent px-7 py-3.5 text-base font-semibold text-primary-foreground shadow-2xl shadow-primary/40 transition-all hover:scale-105 hover:shadow-primary/50 sm:px-8 sm:py-4"
            >
              Get Started Free
              <ArrowRight className="h-5 w-5" />
            </Link>
            <Link
              to="/login"
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-foreground/5 px-7 py-3.5 text-base font-semibold text-foreground backdrop-blur-sm transition-all hover:bg-foreground/10 sm:px-8 sm:py-4"
            >
              Sign In
            </Link>
          </motion.div>
        </div>
      </section>

      <main className="relative z-10">
        <div className="safe-pad mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <section className="py-10 sm:py-16">
            <Glass variant="floating" className="rounded-3xl p-6 sm:p-10">
              <div className="grid gap-6 sm:grid-cols-3">
                <div className="text-center">
                  <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
                    <CheckCircle2 className="h-7 w-7 text-primary" />
                  </div>
                  <h2 className="font-semibold text-foreground">Real Data Only</h2>
                  <p className="mt-2 text-sm text-muted-foreground">Parse resume experience that actually exists</p>
                </div>
                <div className="text-center">
                  <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
                    <Sparkles className="h-7 w-7 text-primary" />
                  </div>
                  <h2 className="font-semibold text-foreground">Smart Matching</h2>
                  <p className="mt-2 text-sm text-muted-foreground">Explainable fit scores you can review</p>
                </div>
                <div className="text-center">
                  <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10">
                    <Lock className="h-7 w-7 text-primary" />
                  </div>
                  <h2 className="font-semibold text-foreground">You're in Control</h2>
                  <p className="mt-2 text-sm text-muted-foreground">Review and approve before anything is sent</p>
                </div>
              </div>
            </Glass>
          </section>

          <section className="py-8 sm:py-12">
            <EncryptionSection />
          </section>
        </div>

        <section className="relative overflow-hidden pb-0 pt-16 sm:pt-20">
          <div className="safe-pad mx-auto max-w-3xl px-4 text-center sm:px-6">
            <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              Opportunities across every industry
            </h2>
            <p className="mt-4 text-lg text-muted-foreground">
              Helping job seekers everywhere navigate their next career move with confidence
            </p>
          </div>
          <div className="relative mx-auto mt-8 h-[20rem] w-full overflow-hidden sm:h-[28rem] lg:h-[36rem]">
            <DottedGlobe />
          </div>
        </section>

        <div className="safe-pad mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <section className="border-t border-border py-20">
            <div className="mx-auto max-w-5xl">
              <h2 className="mb-12 text-center text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
                How CareerPilot works
              </h2>
              <div className="space-y-8">
                {capabilities.map((item, index) => (
                  <motion.div
                    key={item.title}
                    initial={reduce ? false : { opacity: 0, x: -20 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true, margin: "-100px" }}
                    transition={{ duration: 0.5, delay: index * 0.1 }}
                  >
                    <Glass variant="surface" className="rounded-2xl p-6">
                      <div className="flex items-start gap-4">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-accent font-semibold text-primary-foreground">
                          {index + 1}
                        </div>
                        <div>
                          <h3 className="text-lg font-semibold text-foreground">{item.title}</h3>
                          <p className="mt-2 leading-relaxed text-muted-foreground">{item.body}</p>
                        </div>
                      </div>
                    </Glass>
                  </motion.div>
                ))}
              </div>
            </div>
          </section>

          <section className="py-20">
            <Glass variant="floating" className="rounded-3xl p-12 text-center">
              <div className="mx-auto max-w-2xl">
                <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
                  Ready to navigate your next role?
                </h2>
                <p className="mt-4 text-lg text-muted-foreground">
                  Join CareerPilot today and start making smarter career decisions
                </p>
                <Link
                  to="/signup"
                  className="mt-8 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-primary to-accent px-10 py-5 text-lg font-semibold text-primary-foreground shadow-2xl shadow-primary/40 transition-all hover:scale-105 hover:shadow-primary/50"
                >
                  Get Started Free
                  <ArrowRight className="h-5 w-5" />
                </Link>
              </div>
            </Glass>
          </section>
        </div>
      </main>

      <footer className="safe-pad relative z-10 border-t border-border py-8">
        <div className="mx-auto max-w-7xl px-4 text-center text-sm text-muted-foreground sm:px-6 lg:px-8">
          <p>
            &copy; {new Date().getFullYear()} {APP_NAME}. All rights reserved.{" "}
            <Link to="/privacy" className="font-medium text-foreground underline-offset-4 hover:underline">
              Privacy
            </Link>
          </p>
        </div>
      </footer>
    </div>
  );
}
