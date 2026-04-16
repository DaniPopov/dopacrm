/**
 * Re-exports of generated OpenAPI types with friendly aliases.
 *
 * The actual generated types live in `api-schema.ts` (auto-generated from
 * the FastAPI backend's `/openapi.json`). They use a verbose
 * `components["schemas"]["TenantResponse"]` syntax that's unfriendly in
 * application code.
 *
 * This file gives them clean names, and is the ONLY place outside the
 * codegen runner that imports from `api-schema.ts`.
 *
 * To regenerate after a backend change:
 *
 *     make backend-running
 *     cd frontend && npm run gen:api-types
 *
 * CI fails if `api-schema.ts` is out of sync with the live backend.
 */

import type { components } from "./api-schema"

type Schemas = components["schemas"]

// Auth
export type Role = Schemas["Role"]
export type LoginRequest = Schemas["LoginRequest"]
export type TokenResponse = Schemas["TokenResponse"]
export type User = Schemas["UserResponse"]

// Tenants
export type TenantStatus = Schemas["TenantStatus"]
export type Tenant = Schemas["TenantResponse"]
export type CreateTenantRequest = Schemas["CreateTenantRequest"]
export type UpdateTenantRequest = Schemas["UpdateTenantRequest"]

// Members
export type MemberStatus = Schemas["MemberStatus"]
export type Member = Schemas["MemberResponse"]
export type CreateMemberRequest = Schemas["CreateMemberRequest"]
export type UpdateMemberRequest = Schemas["UpdateMemberRequest"]
export type FreezeMemberRequest = Schemas["FreezeMemberRequest"]

// Classes (gym class-types catalog)
export type GymClass = Schemas["GymClassResponse"]
export type CreateGymClassRequest = Schemas["CreateGymClassRequest"]
export type UpdateGymClassRequest = Schemas["UpdateGymClassRequest"]

// Users
export type CreateUserRequest = Schemas["CreateUserRequest"]
export type UpdateUserRequest = Schemas["UpdateUserRequest"]

// Uploads
export type UploadResponse = Schemas["UploadResponse"]

// Errors
export type ValidationError = Schemas["HTTPValidationError"]
