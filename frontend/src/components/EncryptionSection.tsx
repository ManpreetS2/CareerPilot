import { Shield } from "lucide-react";
import { useReducedMotion } from "motion/react";

const ENCRYPTION_TEXT = [
  "iVBORw0KGgoAAAANSUhEUgAABjkAAAQqCAYAAACqkC9hAAAACXBIWXMAABYlAAAWJQFJU",
  "2VyaWFsaXplZCBkYXRhOiBwcm9maWxlLCBleHBlcmllbmNlLCBza2lsbHMsIGxvY2F0aW9u",
  "AES-256-GCM encrypted profile data stored locally with end-to-end encryption",
  "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI",
  "UmVzdW1lIG1ldGFkYXRhOiBlZHVjYXRpb24sIGNlcnRpZmljYXRpb25zLCBwcm9qZWN0cw",
  "TLS 1.3 transport layer security for all API communications and data transfer",
  "dXNlcl9pZDogYWJjZGVmMTIzNDU2LCByb2xlX3R5cGU6ICJlbmdpbmVlciIsIGxvY2F0aW9u",
  "Zero-knowledge architecture: server cannot decrypt user profile or resume data",
];

export function EncryptionSection() {
  const reduceMotion = useReducedMotion();

  return (
    <section className="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-b from-[#0B0818]/80 to-[#070511]/90 px-6 py-20 sm:px-12 sm:py-28">
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
                className="absolute whitespace-nowrap font-mono text-xs text-purple-300/20"
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
        <div className="mb-6 inline-flex rounded-2xl border border-purple-400/20 bg-purple-500/10 p-4">
          <Shield className="h-10 w-10 text-purple-300" strokeWidth={1.5} />
        </div>
        <h2 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          Your resume stays protected
        </h2>
        <p className="mt-5 text-lg leading-relaxed text-gray-300">
          Grounded insights. Private by design. Your documents and profile data stay secure with
          end-to-end encryption. We never share your information with employers until you choose to
          apply.
        </p>
      </div>
    </section>
  );
}
