import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  activatePlan,
  createPlan,
  deactivatePlan,
  getPlan,
  listPlans,
  updatePlan,
} from "./api"
import type { CreatePlanRequest, UpdatePlanRequest } from "./types"

/**
 * Fetch all plans in the caller's tenant.
 * Query key: `["plans", filters ?? {}]`.
 */
export function usePlans(filters?: {
  includeInactive?: boolean
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: ["plans", filters ?? {}],
    queryFn: () => listPlans(filters),
  })
}

/** Fetch one plan. Query key: `["plans", id]`. Disabled when id is empty. */
export function usePlan(id: string) {
  return useQuery({
    queryKey: ["plans", id],
    queryFn: () => getPlan(id),
    enabled: !!id,
  })
}

/** Create a plan. Invalidates the plans list on success. */
export function useCreatePlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreatePlanRequest) => createPlan(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plans"] })
    },
  })
}

/** Update a plan. Invalidates both list and the single-plan cache. */
export function useUpdatePlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdatePlanRequest }) =>
      updatePlan(id, data),
    onSuccess: (plan) => {
      qc.invalidateQueries({ queryKey: ["plans"] })
      qc.setQueryData(["plans", plan.id], plan)
    },
  })
}

/** Deactivate a plan. Invalidates lists (active filter changes). */
export function useDeactivatePlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deactivatePlan(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plans"] }),
  })
}

/** Activate a plan. Invalidates lists. */
export function useActivatePlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => activatePlan(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["plans"] }),
  })
}
