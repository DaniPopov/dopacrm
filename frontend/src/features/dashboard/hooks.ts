import { useQuery } from "@tanstack/react-query"
import { getPlatformStats } from "./api"

/** Platform-wide stats for the super_admin dashboard. Refetches on focus. */
export function usePlatformStats() {
  return useQuery({
    queryKey: ["admin", "platform-stats"],
    queryFn: getPlatformStats,
  })
}
