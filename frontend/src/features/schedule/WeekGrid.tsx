/**
 * WeekGrid — 7 day columns × hourly rows.
 *
 * Bins each session into the (day, hour) cell it starts in. Multiple
 * sessions in the same cell stack vertically (gym with two studios
 * running side-by-side, or back-to-back classes in the same time slot).
 *
 * Hours range from 06:00 to 23:00 — covers typical gym hours without
 * making the grid scroll forever. Earlier/later sessions get clamped
 * to the visible range with a small "earlier" / "later" indicator
 * (future).
 */

import { useMemo } from "react"
import type { GymClass } from "@/features/classes/types"
import type { Coach } from "@/features/coaches/types"
import { SessionCard } from "./SessionCard"
import type { ClassSession } from "./types"

const FIRST_HOUR = 6
const LAST_HOUR = 22 // 22:00 row covers 22:00-22:59
const HOURS = Array.from({ length: LAST_HOUR - FIRST_HOUR + 1 }, (_, i) => FIRST_HOUR + i)

const DAY_LABELS = [
  { code: "sun", he: "ראשון", short: "א'" },
  { code: "mon", he: "שני", short: "ב'" },
  { code: "tue", he: "שלישי", short: "ג'" },
  { code: "wed", he: "רביעי", short: "ד'" },
  { code: "thu", he: "חמישי", short: "ה'" },
  { code: "fri", he: "שישי", short: "ו'" },
  { code: "sat", he: "שבת", short: "ש'" },
] as const

interface Props {
  weekStart: Date // Sunday at 00:00 local
  sessions: ClassSession[]
  classes: GymClass[]
  coaches: Coach[]
  onSessionClick: (session: ClassSession) => void
}

export function WeekGrid({
  weekStart,
  sessions,
  classes,
  coaches,
  onSessionClick,
}: Props) {
  const classMap = useMemo(
    () => new Map(classes.map((c) => [c.id, c])),
    [classes],
  )
  const coachMap = useMemo(
    () => new Map(coaches.map((c) => [c.id, c])),
    [coaches],
  )

  // Bucket sessions into (dayIndex, hour) → ClassSession[].
  const buckets = useMemo(() => {
    const map = new Map<string, ClassSession[]>()
    for (const s of sessions) {
      const start = new Date(s.starts_at)
      const dayIdx = sundayIndexedDay(start)
      const hour = start.getHours()
      if (hour < FIRST_HOUR || hour > LAST_HOUR) continue
      const key = `${dayIdx}-${hour}`
      const arr = map.get(key)
      if (arr) arr.push(s)
      else map.set(key, [s])
    }
    // Sort within bucket by start time.
    for (const arr of map.values()) {
      arr.sort(
        (a, b) =>
          new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime(),
      )
    }
    return map
  }, [sessions])

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="w-full table-fixed border-collapse">
        <thead>
          <tr>
            <th className="w-14 border-b border-gray-200 bg-gray-50 p-2 text-xs font-medium text-gray-500">
              שעה
            </th>
            {DAY_LABELS.map((d, i) => {
              const date = addDays(weekStart, i)
              return (
                <th
                  key={d.code}
                  className="border-b border-l border-gray-200 bg-gray-50 p-2 text-center text-xs font-medium text-gray-700"
                >
                  <div>{d.he}</div>
                  <div className="text-[10px] text-gray-400">
                    {formatDayMonth(date)}
                  </div>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {HOURS.map((hour) => (
            <tr key={hour}>
              <td className="border-b border-r border-gray-100 bg-gray-50/50 p-1 text-center font-mono text-[11px] text-gray-500">
                {String(hour).padStart(2, "0")}:00
              </td>
              {DAY_LABELS.map((_, dayIdx) => {
                const bucket = buckets.get(`${dayIdx}-${hour}`) ?? []
                return (
                  <td
                    key={dayIdx}
                    className="h-16 border-b border-l border-gray-100 align-top"
                  >
                    {bucket.length > 0 && (
                      <div className="flex h-full flex-col gap-0.5 p-0.5">
                        {bucket.map((s) => {
                          const cls = classMap.get(s.class_id)
                          const coach = s.head_coach_id
                            ? coachMap.get(s.head_coach_id)
                            : null
                          return (
                            <SessionCard
                              key={s.id}
                              session={s}
                              className={cls?.name ?? "שיעור"}
                              classColor={cls?.color ?? null}
                              coachName={
                                coach
                                  ? `${coach.first_name} ${coach.last_name}`
                                  : null
                              }
                              onClick={() => onSessionClick(s)}
                            />
                          )
                        })}
                      </div>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Convert JS Date.getDay() (Sun=0..Sat=6) to our index (Sun=0..Sat=6).
 *  Already aligned, but kept as a named helper for clarity. */
function sundayIndexedDay(d: Date): number {
  return d.getDay()
}

function addDays(d: Date, n: number): Date {
  const out = new Date(d)
  out.setDate(out.getDate() + n)
  return out
}

function formatDayMonth(d: Date): string {
  return `${d.getDate()}/${d.getMonth() + 1}`
}
