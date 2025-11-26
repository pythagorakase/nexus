# NEXUS UI Issues

## Closed Issues

### Issue #107: Green Color Artifacts in Gilded Theme ✅ RESOLVED
**Status:** Closed  
**Date Opened:** 2025-11-25  
**Date Closed:** 2025-11-25  
**Severity:** Medium  
**Component:** UI - Theme System

**Description:**
Multiple UI elements were displaying green colors instead of the proper gold/primary colors when using the Gilded (Art Deco) theme:
- Model name display ("GPT-OSS-120B") in StatusBar
- Tab labels ("MAP", "CHARACTERS") in navigation

**Root Cause:**
1. StatusBar was using conditional logic that didn't properly force gold colors for the Gilded theme
2. Tab triggers in NexusLayout were not explicitly setting text colors for inactive states

**Resolution:**
- Modified `StatusBar.tsx` to force `text-primary/90 deco-glow` for loaded/loading model states in Gilded mode
- Updated `NexusLayout.tsx` to force `text-primary/70` for tab text when inactive
- Verified color is correct gold (`rgb(169, 153, 112)`)

**Files Modified:**
- `ui/client/src/components/StatusBar.tsx`
- `ui/client/src/components/NexusLayout.tsx`

---

## Open Issues

### Issue #108: Narrative Tab Scroll Disabled
**Status:** Open  
**Date Opened:** 2025-11-25  
**Priority:** High  
**Component:** UI - NarrativeTab

**Description:**
The narrative content area in the NarrativeTab does not respond to normal scrolling input methods:
- Mouse wheel scrolling is non-functional
- Page Down (PGDN) key does not scroll
- Arrow keys do not scroll
- Content is present in the DOM (can be selected and copied) but is not visible without scrolling

**Current Observations:**
- Full text content is present in the DOM and can be copied via CTRL+A, CTRL+C
- Content appears truncated visually (e.g., last visible line: "And when he sees Alex?", but actual last line is "The **next phase begins.**")
- `ScrollArea` component (Radix UI) is present with correct height (`862px`)
- Viewport has `overflow: scroll` but does not respond to scroll events

**Attempted Fixes (Unsuccessful):**
1. Added `min-h-0` and `flex-col` to `TabsContent` container
2. Added `z-10` and `relative` to `ScrollArea` to lift above overlays
3. Removed hardcoded `terminal-scanlines` class (was blocking in Gilded theme)
4. Simulated wheel events work in programmatic tests but user reports real scrolling still broken

**Environment:**
- Platform: macOS
- Browser: (not specified, assumed Chrome/Safari)
- Theme: Gilded (Art Deco)

**Next Steps:**
- Investigate Radix ScrollArea viewport configuration
- Check for event handler conflicts or scroll prevention
- Verify CSS overflow chain from root to viewport
- Consider alternative scroll implementation if Radix ScrollArea has compatibility issues

**Workaround:**
None currently available for end users.

---

## Issue Template

```markdown
### Issue #XXX: [Title]
**Status:** Open/In Progress/Closed  
**Date Opened:** YYYY-MM-DD  
**Priority:** Low/Medium/High/Critical  
**Component:** [Component Name]

**Description:**
[Clear description of the issue]

**Steps to Reproduce:**
1. [Step 1]
2. [Step 2]

**Expected Behavior:**
[What should happen]

**Actual Behavior:**
[What actually happens]

**Environment:**
- Platform: 
- Browser: 
- Theme: 

**Additional Context:**
[Any other relevant information]
```
