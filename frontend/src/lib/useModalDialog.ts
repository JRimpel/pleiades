import { useEffect } from 'react'
import type { RefObject } from 'react'

/**
 * Show a native `<dialog>` as a modal while `open` is true, and return focus to whatever
 * opened it when it closes. Native modals make the rest of the page inert and stack, so a
 * username prompt can open on top of the photo viewer.
 */
export function useModalDialog(ref: RefObject<HTMLDialogElement | null>, open = true) {
  useEffect(() => {
    const dialog = ref.current
    if (!dialog || !open) return
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    if (!dialog.open) dialog.showModal()
    // showModal() focuses the first focusable element, overriding React's autoFocus; a
    // `data-autofocus` element wins instead.
    dialog.querySelector<HTMLElement>('[data-autofocus]')?.focus()
    return () => {
      if (dialog.open) dialog.close()
      if (opener?.isConnected) opener.focus()
    }
  }, [ref, open])
}
