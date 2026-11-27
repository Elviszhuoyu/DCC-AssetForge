import * as React from "react"

// Keep hints in the page so Qt's native tooltip palette cannot tint the workbench.
export function WorkbenchTooltip() {
  const element = React.useRef<HTMLDivElement>(null)
  React.useEffect(() => {
    const tip = element.current!
    let anchor: HTMLElement | null = null
    let timer = 0
    function dismiss() {
      window.clearTimeout(timer)
      if (anchor?.getAttribute("aria-describedby") === tip.id) anchor.removeAttribute("aria-describedby")
      tip.hidden = true
      anchor = null
    }
    function targetOf(node: EventTarget | null) {
      return node instanceof Element ? node.closest<HTMLElement>("[data-tooltip]") : null
    }
    function show(event: MouseEvent | FocusEvent) {
      const target = targetOf(event.target)
      if (target === anchor) return
      dismiss()
      if (!target?.dataset.tooltip) return
      anchor = target
      timer = window.setTimeout(() => {
        if (!target.isConnected || !target.offsetWidth) return dismiss()
        tip.textContent = target.dataset.tooltip || ""
        tip.hidden = false
        if (!target.hasAttribute("aria-describedby")) target.setAttribute("aria-describedby", tip.id)
        const rect = target.getBoundingClientRect()
        const edge = 6
        const left = rect.left + (rect.width - tip.offsetWidth) / 2
        const top = rect.bottom + edge + tip.offsetHeight <= innerHeight ? rect.bottom + edge : rect.top - tip.offsetHeight - edge
        tip.style.left = Math.max(edge, Math.min(left, innerWidth - tip.offsetWidth - edge)) + "px"
        tip.style.top = Math.max(edge, top) + "px"
      }, 470)
    }
    function leave(event: MouseEvent | FocusEvent) {
      if (targetOf(event.relatedTarget) !== anchor) dismiss()
    }
    document.addEventListener("mouseover", show)
    document.addEventListener("mouseout", leave)
    document.addEventListener("focusin", show)
    document.addEventListener("focusout", leave)
    document.addEventListener("keydown", dismiss)
    document.addEventListener("mousedown", dismiss)
    document.addEventListener("scroll", dismiss, true)
    window.addEventListener("resize", dismiss)
    return () => {
      dismiss()
      document.removeEventListener("mouseover", show)
      document.removeEventListener("mouseout", leave)
      document.removeEventListener("focusin", show)
      document.removeEventListener("focusout", leave)
      document.removeEventListener("keydown", dismiss)
      document.removeEventListener("mousedown", dismiss)
      document.removeEventListener("scroll", dismiss, true)
      window.removeEventListener("resize", dismiss)
    }
  }, [])
  return <div id="af-workbench-hint" className="workbench-tooltip" role="tooltip" hidden ref={element} />
}
