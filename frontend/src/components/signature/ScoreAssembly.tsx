import { motion, useReducedMotion } from "motion/react";
import { MatchBadge } from "../MatchBadge";
import { EvidencePathButton } from "./EvidencePath";
import { motionDuration, motionEase } from "../../lib/motion";
import type { MatchScore } from "../../lib/types";

function Factor({
  label,
  value,
  delay,
  skip,
}: {
  label: string;
  value?: number | null;
  delay: number;
  skip: boolean;
}) {
  return (
    <motion.div
      className="flex items-center justify-between gap-3 border-b border-border/70 py-1.5 text-sm last:border-0"
      initial={skip ? false : { opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: motionDuration.fast, ease: motionEase.standard, delay }}
    >
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular font-semibold">
        {value == null ? "—" : Math.round(value)}
      </span>
    </motion.div>
  );
}

export function ScoreAssembly({
  match,
  assembling,
}: {
  match: MatchScore;
  assembling: boolean;
}) {
  const reduce = useReducedMotion();
  const skip = Boolean(reduce) || !assembling;
  const factors = [
    { label: "Skills", value: match.skill_score },
    { label: "Experience", value: match.experience_score },
    { label: "Education", value: match.education_score },
    { label: "Location", value: match.location_score },
    { label: "Preferences", value: match.preference_score },
  ];

  return (
    <div className="space-y-4" data-testid="score-assembly">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <motion.p
          className="score-fluid font-display font-semibold tabular leading-none"
          initial={skip ? false : { opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: motionDuration.emphasis, ease: motionEase.expressive, delay: skip ? 0 : 0.42 }}
        >
          {Math.round(match.overall_score)}
          <span className="ml-1 text-lg text-muted-foreground">%</span>
        </motion.p>
        <motion.div
          initial={skip ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: motionDuration.base, delay: skip ? 0 : 0.62 }}
        >
          <MatchBadge score={match.overall_score} recommendation={match.recommendation} />
        </motion.div>
      </div>
      <div>
        {factors.map((factor, index) => (
          <Factor
            key={factor.label}
            label={factor.label}
            value={factor.value}
            delay={skip ? 0 : index * 0.07}
            skip={skip}
          />
        ))}
      </div>
      {match.matched_skills.length > 0 ? (
        <div>
          <h3 className="text-sm font-semibold">Matched skills</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {match.matched_skills.map((skill) => (
              <EvidencePathButton
                key={skill}
                claim={`${skill} contributed to this fit score`}
                evidence={
                  match.rationale ||
                  `${skill} is listed among stored matched skills for this job.`
                }
              >
                {skill}
              </EvidencePathButton>
            ))}
          </div>
        </div>
      ) : null}
      {match.partial_matches.length > 0 ? (
        <p className="text-sm text-muted-foreground">
          Partial: {match.partial_matches.join(", ")}
        </p>
      ) : null}
      {match.missing_skills.length > 0 ? (
        <p className="text-sm text-muted-foreground">Missing: {match.missing_skills.join(", ")}</p>
      ) : null}
      <p className="text-sm text-muted-foreground">{match.rationale}</p>
    </div>
  );
}
