# Known Bugs

## UI - Markdown Rendering (Narrative Tab)
**Issue**: Markdown formatting (bold, italic) not rendering in Narrative tab sections despite ReactMarkdown integration.

**Location**: `ui/client/src/components/NarrativePane.tsx`

**Status**: Attempted fix with ReactMarkdown component but no visible change. Works correctly in GenerationPane and ComparisonLayout (previous chunk tail).

**Next Steps**: Debug why markdown renders in some components but not NarrativePane. May need different approach for inline narrative sections.

---
