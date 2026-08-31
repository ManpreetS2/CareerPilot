import { QueryClient } from "@tanstack/react-query";

/** Public/static queries that are safe to keep across account changes. */
const PUBLIC_QUERY_ROOTS = new Set<unknown>(["health"]);

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: 1,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}

function isAuthenticatedQueryKey(queryKey: readonly unknown[]): boolean {
  return !PUBLIC_QUERY_ROOTS.has(queryKey[0]);
}

/**
 * Authenticated-query cache boundary. Call on logout and before binding a new
 * identity so a previous user's Jobs/Saved/scores/resume data cannot render
 * during the next user's staleTime window.
 */
export async function clearAuthenticatedQueryCache(queryClient: QueryClient) {
  const privateQuery = { predicate: (query: { queryKey: readonly unknown[] }) => isAuthenticatedQueryKey(query.queryKey) };
  await queryClient.cancelQueries(privateQuery);
  queryClient.removeQueries(privateQuery);
  queryClient.getMutationCache().clear();
}
