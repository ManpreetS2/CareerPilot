/** Reserved fixture identities only. Never infer that an arbitrary Manual posting is fictional. */
const SHOWCASE_COMPANIES: Record<string, string> = {
  "showcase-harborline-intern": "Harborline Analytics",
  "showcase-cedar-backend": "Cedar & Pine Robotics",
};

export function isSyntheticShowcasePosting(jobId: string, company: string): boolean {
  return SHOWCASE_COMPANIES[jobId] === company;
}
