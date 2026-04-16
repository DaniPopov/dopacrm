import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  activateClass,
  createClass,
  deactivateClass,
  getClass,
  listClasses,
  updateClass,
} from "./api"
import type { CreateGymClassRequest, UpdateGymClassRequest } from "./types"

/**
 * Fetch all classes in the caller's tenant.
 * Query key: `["classes", filters ?? {}]`.
 */
export function useClasses(filters?: {
  includeInactive?: boolean
  limit?: number
  offset?: number
}) {
  return useQuery({
    queryKey: ["classes", filters ?? {}],
    queryFn: () => listClasses(filters),
  })
}

/** Fetch one class. Query key: `["classes", id]`. Disabled when id is empty. */
export function useClass(id: string) {
  return useQuery({
    queryKey: ["classes", id],
    queryFn: () => getClass(id),
    enabled: !!id,
  })
}

/** Create a class. Invalidates the classes list on success. */
export function useCreateClass() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateGymClassRequest) => createClass(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["classes"] })
    },
  })
}

/** Update a class. Invalidates both list and the single-class cache. */
export function useUpdateClass() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateGymClassRequest }) =>
      updateClass(id, data),
    onSuccess: (cls) => {
      qc.invalidateQueries({ queryKey: ["classes"] })
      qc.setQueryData(["classes", cls.id], cls)
    },
  })
}

/** Deactivate a class. Invalidates lists (active filter changes). */
export function useDeactivateClass() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deactivateClass(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["classes"] }),
  })
}

/** Activate a class. Invalidates lists. */
export function useActivateClass() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => activateClass(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["classes"] }),
  })
}
