export type TenantStatus = "trial" | "active" | "suspended" | "cancelled"

export interface Tenant {
  id: string
  slug: string
  name: string
  status: TenantStatus
  saas_plan_id: string

  // Branding
  logo_url: string | null
  logo_presigned_url: string | null

  // Contact
  phone: string | null
  email: string | null
  website: string | null

  // Address
  address_street: string | null
  address_city: string | null
  address_country: string | null
  address_postal_code: string | null

  // Legal
  legal_name: string | null
  tax_id: string | null

  // Regional
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
  logo_url?: string | null
  phone?: string | null
  email?: string | null
  website?: string | null
  address_street?: string | null
  address_city?: string | null
  address_country?: string | null
  address_postal_code?: string | null
  legal_name?: string | null
  tax_id?: string | null
  timezone?: string
  currency?: string
  locale?: string
}

export interface UpdateTenantRequest {
  name?: string | null
  logo_url?: string | null
  phone?: string | null
  email?: string | null
  website?: string | null
  address_street?: string | null
  address_city?: string | null
  address_country?: string | null
  address_postal_code?: string | null
  legal_name?: string | null
  tax_id?: string | null
  timezone?: string | null
  currency?: string | null
  locale?: string | null
}

export interface UploadResponse {
  key: string
  presigned_url: string
}
