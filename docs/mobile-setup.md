# Mobile App — Setup Plan

> **Status:** Deferred. Not started.
>
> **Why deferred:** the CRM is a B2B product used mostly by gym staff at a desk or front-desk terminal. Mobile-responsive web covers the bulk of real usage. Going to prod is gated on Members + Classes + Payments + Leads landing on web — not on a native app. See discussion in `git log` ~2026-04-14.
>
> **Trigger to revisit:** after 4–6 weeks of real gym owners using the prod web CRM, decide based on what they actually ask for. Two distinct products may emerge:
> 1. **Native CRM companion** — staff feature parity (check-in, member lookup) on the floor
> 2. **Member-facing app** — members book / freeze / pay (different auth, different data scope, different UX)

This doc captures the plan so we don't re-derive it later.

---

## Stack decision (when we start)

| Component | Choice | Why |
|---|---|---|
| Framework | **React Native + Expo (managed)** | Reuses React knowledge from web. Expo handles native build / OTA updates / push notifications without ejecting. |
| Language | TypeScript (strict) | Same as web. Type-share via the OpenAPI codegen pipeline (already wired). |
| Navigation | React Navigation | De-facto standard, well-maintained |
| Server state | TanStack Query | Same as web — share hooks where possible |
| HTTP | `fetch` wrapper mirroring `lib/api-client.ts` | Cookie auth doesn't work on RN — see Auth section below |
| Storage | `expo-secure-store` for tokens | Keychain on iOS, Keystore on Android |
| Push notifications | `expo-notifications` | Works for both iOS APNs and Android FCM |
| Build / distribution | EAS Build + TestFlight + Play Store internal track | Standard Expo flow |

**Why not Flutter / native?** RN means one codebase shares ~70% with web (types, hooks, utilities, business logic in services). Flutter would be a third language to maintain. Native would be two more codebases. For a 1-person team, RN is the only sane choice.

**Why not PWA?** Considered. Push notifications + offline are weaker, app store presence matters for sales positioning, and the 70% code-share with React makes RN strictly better.

---

## Monorepo refactor (do this when starting mobile, not before)

The current structure:

```
dopacrm/
├── backend/
└── frontend/
    └── src/lib/
        ├── api-schema.ts    ← auto-generated from OpenAPI
        └── api-types.ts     ← clean re-exports
```

Becomes:

```
dopacrm/
├── backend/
├── packages/
│   └── api-types/
│       ├── package.json     (name: "@dopacrm/api-types")
│       ├── src/
│       │   ├── index.ts     ← re-exports of api-schema types
│       │   └── schema.ts    ← auto-generated from OpenAPI
│       └── tsconfig.json
├── frontend/
│   └── package.json         (deps: "@dopacrm/api-types": "workspace:*")
└── mobile/
    └── package.json         (deps: "@dopacrm/api-types": "workspace:*")
```

### Migration steps

1. **Add `packages/api-types/`** with `package.json`, `tsconfig.json`, and move both `api-schema.ts` + `api-types.ts` from `frontend/src/lib/`.
2. **Add npm workspaces** to root `package.json`:
   ```json
   { "workspaces": ["frontend", "mobile", "packages/*"] }
   ```
3. **Update frontend imports** from `@/lib/api-types` to `@dopacrm/api-types`. One find-and-replace.
4. **Update Make targets**: `gen-api-types` writes to `packages/api-types/src/schema.ts` instead of `frontend/src/lib/api-schema.ts`.
5. **Update CI**: the `check-api-types` step works the same way, just from a different path.
6. **Update tooling**: ESLint, Vitest, TypeScript paths in `frontend/tsconfig.json` to know about the workspace.

Estimated effort: **~30 min refactor, then incidental fixes** (CI step paths, lockfile, etc). Total: half a day.

**Do not do this refactor before mobile starts.** No win, only cost.

---

## Auth strategy — what changes for mobile

The web CRM uses **HttpOnly cookies**. Mobile cannot.

| Aspect | Web | Mobile |
|---|---|---|
| Token storage | HttpOnly cookie (XSS-immune) | `expo-secure-store` (Keychain / Keystore) |
| Token transport | Cookie sent automatically | `Authorization: Bearer <token>` header |
| Logout | Backend clears cookie + Redis blacklist | Backend Redis blacklist + mobile deletes from secure store |
| 401 handling | `ProtectedRoute` redirects to `/login` | Navigation reset to login screen |

**Backend already supports both** — `get_current_user` accepts cookie OR `Authorization` header. Mobile just uses the header path. No backend changes required.

The `lib/api-client.ts` for mobile will be ~50 lines — same shape as the web version, but pulls the token from secure store and sends it as a Bearer header.

---

## Code-share strategy

Three layers of share, in order of value:

1. **Types** — via `@dopacrm/api-types` package. Highest value, zero runtime cost.
2. **Hooks** — TanStack Query hooks like `useMembers()` are pure functions of `api.ts` calls. Could share if `api.ts` is platform-agnostic. Medium value.
3. **Components** — DON'T try. RN components are not React DOM components. Hebrew RTL, Tailwind, shadcn/ui — all DOM-only. Mobile gets its own UI built with React Native primitives. Forcing a shared component layer (React Native Web, Tamagui, etc.) buys ~10% reuse for 10x complexity.

**Recommended scope for v1 mobile:** types + business logic only. Each platform builds its own UI.

---

## Feature scope for v1 mobile (when we start)

Don't try to mirror the entire web app. Pick the on-the-floor use cases that web is bad at:

| Feature | v1 mobile? | Why |
|---|---|---|
| Login | ✅ | Required |
| Member search + check-in | ✅ | Floor staff need this on a phone, walk around the gym |
| Member profile (view) | ✅ | Look up someone mid-conversation |
| Add new member | ✅ | Simple form, common front-desk task |
| Sell pass | ✅ | Front-desk transaction |
| Dashboard | Maybe | Owner reads it, but mobile-responsive web works fine |
| Tenant CRUD | ❌ | super_admin only, desktop is fine |
| Settings / role config | ❌ | Owner does this once at setup, on desktop |
| Lead pipeline | ❌ for v1 | Sales might want it, but punt to mobile v2 |

Rule: **if a feature is a front-desk-floor moment, it goes in v1 mobile. If it's a desk task, leave it on web.**

---

## Push notifications — design before building

Decide BEFORE the first sprint:

- **Who triggers a push?** Backend (event-driven) — never the mobile app itself.
- **Which events warrant a push?**
  - Member's pass about to expire (24h before)
  - New lead assigned to a sales user
  - Class capacity reached (booking feature, future)
  - Payment failed (when payments integrate with Stripe)
- **Token registration:** mobile app fetches Expo push token on login, sends to backend. Backend stores in `user_push_tokens` table (new). On logout, backend deletes the row.
- **Backend integration:** `expo-server-sdk` (Python equivalent) called from a Celery task. Failed sends go to dead-letter queue, same as other Celery work.

This is its own ~3-day feature when we get there. Plan it then; don't pre-build.

---

## Decisions (capture here so we don't re-debate)

1. **React Native + Expo, not Flutter.** Reuse React/TS knowledge.
2. **No shared UI components.** Each platform builds its own.
3. **Types via `@dopacrm/api-types` workspace package.** Codegen pipeline already exists.
4. **Bearer token auth on mobile**, not cookies. Backend already supports both.
5. **EAS Build for distribution.** No native build server setup.
6. **TypeScript strict mode.** Same as web.
7. **Hebrew RTL on day 1.** Same locale story as web.
8. **iOS + Android from launch.** Don't ship one platform first; the dev cost diff is marginal with RN.
9. **Member-facing app is a SEPARATE PRODUCT.** Different repo, different auth, different data scope. Don't conflate "CRM mobile" with "member booking app".

---

## Open questions

1. **Member-facing app — separate repo or same monorepo?** Probably separate, different product / different team eventually.
2. **Offline mode for check-in?** WiFi flakes at gyms. Hard problem (sync, conflict resolution). Probably v2 feature behind a flag.
3. **Tablet support?** Front-desk often runs on iPad. RN handles this for free, but UI needs landscape consideration.
4. **Biometric login?** `expo-local-authentication` is one extra dep. Worth it for v1.
5. **Update strategy for breaking API changes?** Force-update flow when backend bumps a version. Standard, but design before deploying.

---

## Tracking

- `TODO.md` → "Mobile" section (add when this becomes near-term)
- This doc gets updated when work starts — current state is "plan only"

---

## Related docs

- [`spec.md`](./spec.md) — product spec (web CRM)
- [`frontend.md`](./frontend.md) §"Type sharing — backend ↔ frontend" — the OpenAPI codegen pipeline mobile will reuse
- [`features/auth.md`](./features/auth.md) — backend auth, dual cookie + Bearer support
