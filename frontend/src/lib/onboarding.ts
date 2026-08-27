export type OnboardingProgress = {
  step: number;
  skipped: boolean;
  completed: boolean;
};

const KEY = "careerpilot.onboarding";

function scoped(userId: number) {
  return `${KEY}.u${userId}`;
}

export function readOnboardingProgress(userId: number): OnboardingProgress {
  try {
    const raw = localStorage.getItem(scoped(userId));
    if (!raw) return { step: 1, skipped: false, completed: false };
    const parsed = JSON.parse(raw) as Partial<OnboardingProgress>;
    return {
      step: typeof parsed.step === "number" ? parsed.step : 1,
      skipped: Boolean(parsed.skipped),
      completed: Boolean(parsed.completed),
    };
  } catch {
    return { step: 1, skipped: false, completed: false };
  }
}

export function saveOnboardingProgress(userId: number, progress: OnboardingProgress) {
  localStorage.setItem(scoped(userId), JSON.stringify(progress));
}

export function shouldPromptFinishSetup(userId: number): boolean {
  const progress = readOnboardingProgress(userId);
  return progress.skipped && !progress.completed;
}
