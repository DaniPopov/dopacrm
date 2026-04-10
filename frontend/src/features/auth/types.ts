export interface LoginRequest {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface User {
  id: string
  email: string
  role: string
  tenant_id: string | null
  is_active: boolean
  oauth_provider: string | null
  created_at: string
  updated_at: string
}
