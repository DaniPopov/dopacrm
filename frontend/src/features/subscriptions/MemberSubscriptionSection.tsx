import { useState } from "react"
import { useAuth } from "@/features/auth/auth-provider"
import { usePlans } from "@/features/plans/hooks"
import {
  useCurrentSubscriptionForMember,
  useSubscriptionEvents,
  useSubscriptionHistoryForMember,
  useUnfreezeSubscription,
} from "./hooks"
import SubscriptionCancelDialog from "./SubscriptionCancelDialog"
import SubscriptionChangePlanDialog from "./SubscriptionChangePlanDialog"
import SubscriptionEnrollDialog from "./SubscriptionEnrollDialog"
import SubscriptionFreezeDialog from "./SubscriptionFreezeDialog"
import SubscriptionRenewDialog from "./SubscriptionRenewDialog"
import SubscriptionTimeline from "./SubscriptionTimeline"
import { SubscriptionBadge } from "./SubscriptionBadge"
import { formatPaymentMethod } from "./paymentMethods"
import type { Subscription } from "./types"

/**
 * The subscription-centric portion of the Member detail page.
 *
 * Layout:
 * 1. Current subscription card — plan, price, status badge, dates,
 *    action buttons (freeze / renew / change-plan / cancel). Shows
 *    an "enroll" CTA if no current sub.
 * 2. Timeline of the current (or most recent) sub's events.
 * 3. History table — past + replaced / cancelled / expired subs.
 *
 * Only staff+ (staff, owner, super_admin) see action buttons; sales
 * see read-only info. Backend also enforces this — UI gating is UX,
 * not security.
 */
export default function MemberSubscriptionSection({
  memberId,
}: {
  memberId: string
}) {
  const { user } = useAuth()
  const canMutate =
    user?.role === "staff" || user?.role === "owner" || user?.role === "super_admin"

  const { data: current, isLoading: currentLoading } =
    useCurrentSubscriptionForMember(memberId)
  const { data: history } = useSubscriptionHistoryForMember(memberId)
  const { data: plans } = usePlans()

  // The timeline follows whichever sub is "representative" — prefer
  // current live sub; otherwise the newest one in history.
  const focusSub = current ?? history?.[0] ?? null
  const { data: events } = useSubscriptionEvents(focusSub?.id ?? "")

  const planById = new Map((plans ?? []).map((p) => [p.id, p]))
  const pastSubs = (history ?? []).filter((s) => s.id !== current?.id)

  // Dialog state — one-at-a-time, keyed by sub op
  const [dialog, setDialog] = useState<
    null | "enroll" | "freeze" | "renew" | "changePlan" | "cancel"
  >(null)

  const unfreeze = useUnfreezeSubscription()

  return (
    <div className="space-y-8">
      {/* ── Current sub ─────────────────────────────────────── */}
      <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-base font-semibold text-gray-900">מנוי נוכחי</h2>

        {currentLoading ? (
          <div className="text-sm text-gray-400">טוען...</div>
        ) : current ? (
          <CurrentSubCard
            sub={current}
            planName={planById.get(current.plan_id)?.name ?? "—"}
            canMutate={canMutate}
            unfreezing={unfreeze.isPending}
            onFreeze={() => setDialog("freeze")}
            onUnfreeze={() => unfreeze.mutate(current.id)}
            onRenew={() => setDialog("renew")}
            onChangePlan={() => setDialog("changePlan")}
            onCancel={() => setDialog("cancel")}
          />
        ) : (
          <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50/50 p-6 text-center">
            <p className="mb-3 text-sm text-gray-500">
              לחבר/ה אין כרגע מנוי פעיל
            </p>
            {canMutate && (
              <button
                onClick={() => setDialog("enroll")}
                className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700"
              >
                + רישום מנוי חדש
              </button>
            )}
          </div>
        )}
      </section>

      {/* ── Timeline ─────────────────────────────────────────── */}
      {focusSub && (
        <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-base font-semibold text-gray-900">טיימליין</h2>
          <SubscriptionTimeline events={events ?? []} />
        </section>
      )}

      {/* ── History ──────────────────────────────────────────── */}
      {pastSubs.length > 0 && (
        <section className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-base font-semibold text-gray-900">
            היסטוריית מנויים
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-right text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-gray-500">
                  <th className="py-2 font-medium">מסלול</th>
                  <th className="py-2 font-medium">סטטוס</th>
                  <th className="py-2 font-medium">התחיל</th>
                  <th className="py-2 font-medium">הסתיים</th>
                </tr>
              </thead>
              <tbody>
                {pastSubs.map((s) => (
                  <tr key={s.id} className="border-b border-gray-50">
                    <td className="py-2 text-gray-900">
                      {planById.get(s.plan_id)?.name ?? "—"}
                    </td>
                    <td className="py-2">
                      <SubscriptionBadge status={s.status} />
                    </td>
                    <td className="py-2 text-gray-600">{formatDate(s.started_at)}</td>
                    <td className="py-2 text-gray-600">
                      {formatDate(
                        s.cancelled_at ?? s.replaced_at ?? s.expired_at ?? null,
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* ── Dialogs ──────────────────────────────────────────── */}
      {dialog === "enroll" && (
        <SubscriptionEnrollDialog memberId={memberId} onClose={() => setDialog(null)} />
      )}
      {dialog === "freeze" && current && (
        <SubscriptionFreezeDialog
          subscriptionId={current.id}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "renew" && current && (
        <SubscriptionRenewDialog
          subscriptionId={current.id}
          currentExpiresAt={current.expires_at}
          currentPaymentMethod={current.payment_method}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "changePlan" && current && (
        <SubscriptionChangePlanDialog
          subscriptionId={current.id}
          currentPlanId={current.plan_id}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "cancel" && current && (
        <SubscriptionCancelDialog
          subscriptionId={current.id}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  )
}

/* ── Current subscription card ────────────────────────────── */

function CurrentSubCard({
  sub,
  planName,
  canMutate,
  unfreezing,
  onFreeze,
  onUnfreeze,
  onRenew,
  onChangePlan,
  onCancel,
}: {
  sub: Subscription
  planName: string
  canMutate: boolean
  unfreezing: boolean
  onFreeze: () => void
  onUnfreeze: () => void
  onRenew: () => void
  onChangePlan: () => void
  onCancel: () => void
}) {
  return (
    <div>
      <div className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
        <Row label="מסלול" value={planName} />
        <Row
          label="מחיר"
          value={`${(sub.price_cents / 100).toLocaleString("he-IL")} ${sub.currency === "ILS" ? "₪" : sub.currency}`}
        />
        <Row
          label="סטטוס"
          valueNode={<SubscriptionBadge status={sub.status} />}
        />
        <Row label="התחיל" value={formatDate(sub.started_at)} />
        <Row
          label="תוקף עד"
          value={
            sub.expires_at
              ? formatDate(sub.expires_at)
              : "ללא מגבלת זמן (הרשאת קבע)"
          }
        />
        <Row
          label="תשלום"
          value={formatPaymentMethod(sub.payment_method, sub.payment_method_detail)}
        />
        {sub.status === "frozen" && (
          <Row
            label="הפשרה אוטומטית"
            value={sub.frozen_until ? formatDate(sub.frozen_until) : "ידנית בלבד"}
          />
        )}
      </div>

      {canMutate && (
        <div className="mt-5 flex flex-wrap gap-2 border-t border-gray-100 pt-4">
          {sub.status === "active" && (
            <ActionButton onClick={onFreeze}>הקפא</ActionButton>
          )}
          {sub.status === "frozen" && (
            <ActionButton onClick={onUnfreeze} disabled={unfreezing}>
              {unfreezing ? "..." : "הפשר"}
            </ActionButton>
          )}
          {(sub.status === "active" || sub.status === "expired") && (
            <ActionButton onClick={onRenew}>חדש</ActionButton>
          )}
          {(sub.status === "active" || sub.status === "frozen") && (
            <ActionButton onClick={onChangePlan}>החלף מסלול</ActionButton>
          )}
          {sub.status !== "cancelled" && sub.status !== "replaced" && (
            <ActionButton onClick={onCancel} destructive>
              בטל מנוי
            </ActionButton>
          )}
        </div>
      )}
    </div>
  )
}

function Row({
  label,
  value,
  valueNode,
}: {
  label: string
  value?: string
  valueNode?: React.ReactNode
}) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="w-28 text-gray-500">{label}</span>
      <span className="min-w-0 flex-1 text-gray-900">
        {valueNode ?? value}
      </span>
    </div>
  )
}

function ActionButton({
  onClick,
  disabled,
  destructive,
  children,
}: {
  onClick: () => void
  disabled?: boolean
  destructive?: boolean
  children: React.ReactNode
}) {
  const base =
    "rounded-lg border px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
  const variant = destructive
    ? "border-red-200 text-red-600 hover:bg-red-50"
    : "border-gray-200 text-gray-700 hover:bg-gray-50"
  return (
    <button onClick={onClick} disabled={disabled} className={`${base} ${variant}`}>
      {children}
    </button>
  )
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  try {
    const d = new Date(iso)
    return d.toLocaleDateString("he-IL", {
      day: "numeric",
      month: "long",
      year: "numeric",
    })
  } catch {
    return iso
  }
}
