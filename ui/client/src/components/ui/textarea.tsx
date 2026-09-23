import * as React from "react"

import { cn } from "@/lib/utils"

type TextareaProps = React.ComponentProps<"textarea"> & {
  /** Grow and shrink to fit the content, including soft-wrapped lines. */
  autoSize?: boolean
}

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  TextareaProps
>(({ className, autoSize = false, value, onInput, ...props }, ref) => {
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null)
  const setRef = React.useCallback(
    (node: HTMLTextAreaElement | null) => {
      textareaRef.current = node
      if (typeof ref === "function") ref(node)
      else if (ref) ref.current = node
    },
    [ref]
  )

  const resize = React.useCallback(() => {
    const textarea = textareaRef.current
    if (!autoSize || !textarea) return
    const style = getComputedStyle(textarea)
    const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom)
    const border =
      parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth)
    // Reset first so deleting text can shrink the field as well as grow it.
    textarea.style.height = "auto"
    const height =
      textarea.scrollHeight + (style.boxSizing === "border-box" ? border : -padding)
    textarea.style.height = `${height}px`
  }, [autoSize])

  React.useLayoutEffect(resize, [resize, value, className])

  React.useLayoutEffect(() => {
    const textarea = textareaRef.current
    if (!autoSize || !textarea) return
    let width = textarea.getBoundingClientRect().width
    const observer = new ResizeObserver(() => {
      const nextWidth = textarea.getBoundingClientRect().width
      // Ignore our own height changes to avoid a resize feedback loop.
      if (nextWidth !== width) {
        width = nextWidth
        resize()
      }
    })
    observer.observe(textarea)
    document.fonts?.addEventListener("loadingdone", resize)
    return () => {
      observer.disconnect()
      document.fonts?.removeEventListener("loadingdone", resize)
    }
  }, [autoSize, resize])

  return (
    <textarea
      className={cn(
        "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-base ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
        autoSize && "resize-none overflow-hidden",
        className
      )}
      ref={setRef}
      value={value}
      onInput={(event) => {
        resize()
        onInput?.(event)
      }}
      {...props}
    />
  )
})
Textarea.displayName = "Textarea"

export { Textarea }
