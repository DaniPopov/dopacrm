import { useState, type InputHTMLAttributes } from "react"
import { cn } from "@/lib/utils"

/**
 * Password input with a show/hide eye toggle.
 *
 * Drop-in replacement for `<input type="password">` — accepts every
 * standard input prop via spread (value, onChange, placeholder,
 * required, minLength, etc.) except `type`, which is managed internally.
 *
 * The toggle button sits on the LEFT edge (RTL layout). Clicking it
 * swaps between `type=password` (masked) and `type=text` (revealed),
 * and the icon flips between eye / eye-off. The button has
 * `tabIndex={-1}` so tab navigation goes password → next field,
 * not password → eye → next field.
 *
 * Accessibility: the toggle carries an aria-label that switches based
 * on current state ("הצג סיסמה" / "הסתר סיסמה").
 */
export type PasswordInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type"
>

export default function PasswordInput({
  className,
  ...rest
}: PasswordInputProps) {
  const [show, setShow] = useState(false)

  return (
    <div className="relative">
      <input
        {...rest}
        type={show ? "text" : "password"}
        className={cn(className, "pl-10")}
      />
      <button
        type="button"
        onClick={() => setShow((v) => !v)}
        aria-label={show ? "הסתר סיסמה" : "הצג סיסמה"}
        tabIndex={-1}
        className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 transition-colors hover:text-gray-600"
      >
        {show ? <EyeOffIcon /> : <EyeIcon />}
      </button>
    </div>
  )
}

/** Open eye — shown when password is masked (click to reveal). */
function EyeIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

/** Slashed eye — shown when password is revealed (click to hide). */
function EyeOffIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  )
}
