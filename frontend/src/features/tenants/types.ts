export interface Tenant {
  id: string
  slug: string
  name: string
  phone: string | null
  status: "trial" | "active" | "suspended" | "cancelled"
  timezone: string
  currency: string
  locale: string
  trial_ends_at: string | null
  created_at: string
  updated_at: string
}

export interface CreateTenantRequest {
  slug: string
  name: string
  phone?: string
  timezone?: string
  currency?: string
  locale?: string
}

export interface UpdateTenantRequest {
  name?: string
  phone?: string
  timezone?: string
  currency?: string
  locale?: string
}
