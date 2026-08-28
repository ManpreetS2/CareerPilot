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
  suffix = "",
}: {
  label: string;
  value?: number | string | null;
  delay: number;
  skip: boolean;
  suffix?: string;
}) {
  const display =
    value == null ? "—" : typeof value === "number" ? `${Math.round(value)}${suffix}` : value;
  return (
    <motion.div
      className="flex items-center justify-between gap-3 border-b border-border/70 py-1.5 text-sm last:border-0"
      initial={skip ? false : { opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: motionDuration.fast, ease: motionEase.standard, delay }}
    >
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular font-semibold">{display}</span>
    </motion.div>
  );
}

function ReasonList({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className={`mt-2 space-y-1 text-sm ${tone}`}>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

const ELIGIBILITY_LABEL: Record<string, string> = {
  likely_eligible: "Eligible based on stated requirements",
  eligibility_uncertain: "Eligibility uncertain",
  likely_ineligible: "Likely ineligible",
};

const CONFIDENCE_LABEL: Record<string, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

export function ScoreAssembly({
  match,
  assembling,
}: {
  match: MatchScore;
  assembling: boolean;
}) {
  const reduce = useReducedMotion();
  const skip = Boolean(reduce) || !assembling;
  const v2 = (match.scoring_version ?? 1) >= 2;
  const factors = v2
    ? [
        { label: "Qualification Fit", value: match.qualification_score, suffix: "%" },
        { label: "Preference Fit", value: match.preference_score, suffix: "%" },
        {
          label: "Eligibility",
          value: match.eligibility_status ? ELIGIBILITY_LABEL[match.eligibility_status] : null,
        },
        {
          label: "Confidence",
          value: match.confidence_level ? CONFIDENCE_LABEL[match.confidence_level] : null,
        },
      ]
    : [
        { label: "Skills", value: match.skill_score, suffix: "" },
        { label: "Experience", value: match.experience_score, suffix: "" },
        { label: "Education", value: match.education_score, suffix: "" },
        { label: "Location", value: match.location_score, suffix: "" },
        { label: "Preferences", value: match.preference_score, suffix: "" },
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
          <MatchBadge
            score={match.overall_score}
            recommendation={match.recommendation}
            matchTier={match.match_tier}
            applyRecommendation={match.apply_recommendation}
            confidenceLevel={match.confidence_level}
          />
        </motion.div>
      </div>
      {match.score_kind === "preliminary" ? (
        <p className="text-sm text-muted-foreground">
          Preliminary match from the posting text. Generating Job Intelligence can refine this.
        </p>
      ) : null}
      <div>
        {factors.map((factor, index) => (
          <Factor
            key={factor.label}
            label={factor.label}
            value={factor.value}
            suffix={"suffix" in factor ? factor.suffix : ""}
            delay={skip ? 0 : index * 0.07}
            skip={skip}
          />
        ))}
      </div>
      <ReasonList title="Why you match" items={match.match_reasons ?? []} tone="text-foreground" />
      <ReasonList title="Gaps" items={match.gap_reasons ?? []} tone="text-muted-foreground" />
      <ReasonList title="Watch out" items={match.watchouts ?? []} tone="text-muted-foreground" />
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
          Related: {match.partial_matches.join(", ")}
        </p>
      ) : null}
      {match.missing_skills.length > 0 ? (
        <p className="text-sm text-muted-foreground">Missing: {match.missing_skills.join(", ")}</p>
      ) : null}
      <p className="text-sm text-muted-foreground">{match.rationale}</p>
    </div>
  );
}
