import { Shield } from "lucide-react";
import { useReducedMotion } from "motion/react";

const ENCRYPTION_TEXT = [
  "iVBORw0KGgoAAAANSUhEUgAABjkAAAQqCAYAAACqkC9hAAAACXBIWXMAABYlAAAWJQFJU",
  "2VyaWFsaXplZCBkYXRhOiBwcm9maWxlLCBleHBlcmllbmNlLCBza2lsbHMsIGxvY2F0aW9u",
  "Local SQLite stores application records and uploaded files in the CareerPilot deployment",
  "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI",
  "UmVzdW1lIG1ldGFkYXRhOiBlZHVjYXRpb24sIGNlcnRpZmljYXRpb25zLCBwcm9qZWN0cw",
  "Configured cloud AI providers can receive resume text or job content for requested operations",
  "dXNlcl9pZDogYWJjZGVmMTIzNDU2LCByb2xlX3R5cGU6ICJlbmdpbmVlciIsIGxvY2F0aW9u",
  "You review the ATS form and press Submit; CareerPilot never auto-submits",
];

export function EncryptionSection() {
  const reduceMotion = useReducedMotion();

  return (
    <section className="glass-floating relative overflow-hidden rounded-3xl px-6 py-20 sm:px-12 sm:py-28">
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div
          className="absolute inset-0 opacity-5"
          style={{
            backgroundImage: `
              repeating-linear-gradient(0deg, rgba(139, 92, 246, 0.1) 0 1px, transparent 1px 24px),
              repeating-linear-gradient(90deg, rgba(139, 92, 246, 0.1) 0 1px, transparent 1px 24px)
            `,
          }}
        />
        {!reduceMotion && (
          <div className="absolute inset-0 overflow-hidden opacity-80">
            {ENCRYPTION_TEXT.map((text, index) => (
              <div
                key={index}
                className="absolute whitespace-nowrap font-mono text-xs text-primary/25"
                style={{
                  top: `${index * 12 + 5}%`,
                  left: `-${index % 3 * 10}%`,
                  animation: `ripple-drift ${12 + index * 2}s ease-in-out infinite`,
                  animationDelay: `${index * -1.5}s`,
                  filter: "blur(0.5px)",
                }}
              >
                {text.repeat(4)}
              </div>
            ))}
          </div>
        )}
      </div>

      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-48 opacity-60 blur-2xl"
        style={{
          background:
            "radial-gradient(ellipse at bottom, rgba(139, 92, 246, 0.35) 0%, transparent 70%)",
        }}
      />

      <div className="relative z-10 mx-auto max-w-2xl text-center">
        <div className="mb-6 inline-flex rounded-2xl border border-primary/25 bg-primary/10 p-4">
          <Shield className="h-10 w-10 text-primary" strokeWidth={1.5} />
        </div>
        <h2 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
          Your resume stays protected
        </h2>
        <p className="mt-5 text-lg leading-relaxed text-muted-foreground">
          Application records and uploaded files are stored in the CareerPilot deployment you run.
          Configured AI providers can receive resume text, stored evidence, or job content for the
          operation you request. Listing a local provider first is not local-only processing if a
          cloud fallback is configured, and Ollama can point at a remote host. Fit scoring stays
          deterministic. CareerPilot never submits an application — you review the ATS form and press
          Submit.
        </p>
      </div>
    </section>
  );
}
