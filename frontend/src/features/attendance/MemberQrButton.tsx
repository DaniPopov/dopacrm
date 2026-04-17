import { useEffect, useRef, useState } from "react"
import QRCode from "qrcode"

/**
 * Renders a "הצג QR / הדפס כרטיס" button on the member detail page.
 *
 * The QR payload is just the member's UUID (client-side rendered via
 * the qrcode lib — no DB column, no stored blob). Staff scans it at
 * check-in and the existing /attendance endpoints look up the member
 * in the caller's tenant scope. Cross-tenant leaks are impossible
 * because foreign UUIDs → 404 from our own tenant scoping.
 *
 * Clicking the button opens a modal with a large QR + the member's
 * name + a print-ready layout (browser print dialog handles the rest).
 */
export default function MemberQrButton({
  memberId,
  memberName,
}: {
  memberId: string
  memberName: string
}) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
      >
        הצג QR / הדפס כרטיס
      </button>
      {open && (
        <QrModal memberId={memberId} memberName={memberName} onClose={() => setOpen(false)} />
      )}
    </>
  )
}

function QrModal({
  memberId,
  memberName,
  onClose,
}: {
  memberId: string
  memberName: string
  onClose: () => void
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!canvasRef.current) return
    // Render the UUID as a QR code onto the canvas. 280px feels right
    // for both screen display and A6 print cards.
    QRCode.toCanvas(canvasRef.current, memberId, {
      width: 280,
      margin: 2,
      color: { dark: "#111827", light: "#ffffff" },
    }).catch((err) => {
      // Shouldn't happen — UUID is ASCII + short. Log if it does.
      // eslint-disable-next-line no-console
      console.error("qrcode render failed", err)
    })
  }, [memberId])

  function handlePrint() {
    window.print()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 print:bg-white"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-2xl print:shadow-none">
        <div className="mb-4 flex items-center justify-between print:hidden">
          <h3 className="text-lg font-bold text-gray-900">כרטיס חבר</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="סגירה"
          >
            ✕
          </button>
        </div>

        <div className="flex flex-col items-center gap-3 py-4">
          <div className="text-xl font-bold text-gray-900">{memberName}</div>
          <canvas ref={canvasRef} aria-label="קוד QR של החבר" />
          <div className="font-mono text-[10px] text-gray-400" dir="ltr">
            {memberId}
          </div>
        </div>

        <div className="mt-4 flex justify-end gap-3 border-t border-gray-100 pt-4 print:hidden">
          <button
            onClick={onClose}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
          >
            סגור
          </button>
          <button
            onClick={handlePrint}
            className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700"
          >
            הדפס
          </button>
        </div>
      </div>
    </div>
  )
}
