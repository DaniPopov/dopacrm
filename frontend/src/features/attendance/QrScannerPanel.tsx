import { useEffect, useRef, useState } from "react"
import { BrowserMultiFormatReader, type IScannerControls } from "@zxing/browser"

/**
 * Camera-based QR scanner using @zxing/browser.
 *
 * Decodes a single payload (we expect a UUID — the member's id) and
 * hands it to ``onDecode``. The parent closes this panel + feeds the
 * UUID into the same flow as a manual member pick.
 *
 * Error handling:
 * - Camera permission denied → we render an inline message asking the
 *   user to allow the camera.
 * - No camera on the device → same message.
 * - Invalid (non-UUID) decode → we still call onDecode; the backend
 *   returns 404 and the parent's toast handles it gracefully.
 */
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export default function QrScannerPanel({
  onDecode,
  onClose,
}: {
  onDecode: (memberId: string) => void
  onClose: () => void
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const reader = new BrowserMultiFormatReader()
    let controls: IScannerControls | null = null

    reader
      .decodeFromVideoDevice(undefined, videoRef.current!, (result) => {
        if (!result) return
        const text = result.getText().trim()
        // Accept bare UUIDs or URL-style payloads like dopacrm://checkin?member=<uuid>
        const match = text.match(UUID_REGEX) ?? extractMemberIdFromUrl(text)
        if (match) {
          controls?.stop()
          onDecode(Array.isArray(match) ? match[0] : match)
        }
      })
      .then((c) => {
        controls = c
      })
      .catch((err: Error) => {
        if (err.name === "NotAllowedError") {
          setError("הגישה למצלמה נדחתה. אפשרו אותה בהגדרות הדפדפן ונסו שוב.")
        } else if (err.name === "NotFoundError") {
          setError("לא נמצאה מצלמה במכשיר זה. השתמשו בחיפוש ידני.")
        } else {
          setError(`שגיאה בהפעלת המצלמה: ${err.message}`)
        }
      })

    return () => {
      controls?.stop()
    }
  }, [onDecode])

  return (
    <div className="rounded-xl border border-gray-200 bg-black p-0 shadow-sm">
      <div className="relative aspect-square w-full overflow-hidden rounded-xl">
        {/* Fills the square. Hidden while error is shown. */}
        {!error && (
          <video
            ref={videoRef}
            className="h-full w-full object-cover"
            muted
            playsInline
            autoPlay
          />
        )}
        {/* Overlay: scan target frame + dismiss button */}
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          {!error && (
            <div className="h-56 w-56 rounded-2xl border-4 border-white/70 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" />
          )}
        </div>
        <button
          onClick={onClose}
          className="absolute left-2 top-2 rounded-full bg-white/90 px-3 py-1.5 text-xs font-medium text-gray-700 shadow hover:bg-white"
        >
          סגור
        </button>
      </div>
      {error && (
        <div className="rounded-b-xl bg-white p-4 text-center text-sm text-red-600">
          {error}
        </div>
      )}
    </div>
  )
}

/**
 * Extract a member UUID from a URL-style QR payload.
 * Accepts patterns like:
 *   dopacrm://checkin?member=<uuid>
 *   https://gym.example.com/c/<uuid>
 *
 * Returns the first UUID found, or null.
 */
function extractMemberIdFromUrl(text: string): string | null {
  const match = text.match(
    /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
  )
  return match?.[0] ?? null
}
