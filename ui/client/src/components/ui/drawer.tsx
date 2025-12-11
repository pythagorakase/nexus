"use client"

import * as React from "react"
import { Drawer as DrawerPrimitive } from "vaul"

import { cn } from "@/lib/utils"

type DrawerDirection = "top" | "bottom" | "left" | "right"

type DrawerProps = React.PropsWithChildren<
  React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Root> & {
    direction?: DrawerDirection
  }
>

const Drawer = ({
  shouldScaleBackground = true,
  direction = "bottom",
  ...props
}: DrawerProps) => (
  <DrawerPrimitive.Root
    shouldScaleBackground={shouldScaleBackground}
    direction={direction}
    {...props}
  />
)
Drawer.displayName = "Drawer"

const DrawerTrigger = DrawerPrimitive.Trigger

const DrawerPortal = DrawerPrimitive.Portal

const DrawerClose = DrawerPrimitive.Close

const DrawerOverlay = React.forwardRef<
  React.ElementRef<typeof DrawerPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DrawerPrimitive.Overlay
    ref={ref}
    className={cn("fixed inset-0 z-50 bg-transparent", className)}
    {...props}
  />
))
DrawerOverlay.displayName = DrawerPrimitive.Overlay.displayName

interface DrawerContentProps
  extends React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Content> {
  /** Override direction for styling (vaul handles the actual direction) */
  direction?: DrawerDirection
}

const DrawerContent = React.forwardRef<
  React.ElementRef<typeof DrawerPrimitive.Content>,
  DrawerContentProps
>(({ className, children, direction = "bottom", ...props }, ref) => (
  <DrawerPortal>
    <DrawerOverlay />
    <DrawerPrimitive.Content
      ref={ref}
      className={cn(
        "fixed z-50 flex flex-col bg-background",
        // Bottom drawer (default)
        direction === "bottom" &&
          "inset-x-0 bottom-0 mt-24 h-auto max-h-[96vh] rounded-t-[10px] border-t",
        // Top drawer
        direction === "top" &&
          "inset-x-0 top-0 mb-24 h-auto max-h-[96vh] rounded-b-[10px] border-b",
        // Right drawer
        direction === "right" &&
          "inset-y-0 right-0 h-full w-[400px] max-w-[90vw] border-l",
        // Left drawer
        direction === "left" &&
          "inset-y-0 left-0 h-full w-[400px] max-w-[90vw] border-r",
        className
      )}
      {...props}
    >
      {/* Handle bar - only show for bottom/top drawers */}
      {(direction === "bottom" || direction === "top") && (
        <div className="mx-auto mt-4 h-2 w-[100px] rounded-full bg-muted" />
      )}
      {children}
    </DrawerPrimitive.Content>
  </DrawerPortal>
))
DrawerContent.displayName = "DrawerContent"

const DrawerHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("grid gap-1.5 p-4 text-center sm:text-left", className)}
    {...props}
  />
)
DrawerHeader.displayName = "DrawerHeader"

const DrawerFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn("mt-auto flex flex-col gap-2 p-4", className)}
    {...props}
  />
)
DrawerFooter.displayName = "DrawerFooter"

const DrawerTitle = React.forwardRef<
  React.ElementRef<typeof DrawerPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DrawerPrimitive.Title
    ref={ref}
    className={cn(
      "text-lg font-semibold leading-none tracking-tight",
      className
    )}
    {...props}
  />
))
DrawerTitle.displayName = DrawerPrimitive.Title.displayName

const DrawerDescription = React.forwardRef<
  React.ElementRef<typeof DrawerPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DrawerPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DrawerPrimitive.Description
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
))
DrawerDescription.displayName = DrawerPrimitive.Description.displayName

export {
  Drawer,
  DrawerPortal,
  DrawerOverlay,
  DrawerTrigger,
  DrawerClose,
  DrawerContent,
  DrawerHeader,
  DrawerFooter,
  DrawerTitle,
  DrawerDescription,
}
