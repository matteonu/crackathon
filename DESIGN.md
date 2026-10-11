---
version: alpha
colors:
  canvas: "#f5f6f2"
  surface: "#ffffff"
  ink: "#26352d"
  muted: "#5d6b61"
  primary: "#315c47"
  line: "#e0e5dc"
typography:
  sans:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
rounded:
  control: "7px"
  panel: "12px"
spacing:
  control: "8px"
  panel: "22px"
components:
  learning-panel:
    description: "A bordered tool surface beside the source viewer, using the selected theme."
---

## Overview

Studyhub is a calm, compact academic workspace. Its visual reference is a well-kept study notebook: restrained sage surfaces, clear ink, and dense controls that leave the source material in charge. Product familiarity wins over decoration; the PDF and the current learning prompt are the signature elements.

## Colors

Green is the default theme. Yellow, Blue, Red, Dark mode, High contrast dark, and Color blind are selected through the logo's theme wheel. Semantic tokens in `frontend/src/themes.css` control surfaces, text, borders, actions, and status colors across the app. Component classes live in `frontend/src/styles.css`; use these tokens instead of fixed green or white colors. PDF pages retain their document colors. Subject colors remain stable between themes.

The Color blind theme uses blue/orange status colors, stripes and dots for flashcard states, and patterns for planned versus recorded hours. High contrast dark uses strong borders and text contrast of at least 7:1 on the main surfaces. The theme wheel shows a vertical arc: the current logo stays at its original position beside the stationary wordmark, with smaller tilted previous and next logos above and below. The neighbors and theme label ease into view on hover and retract when the pointer leaves; keyboard focus keeps the wheel available. Logos rotate into that same spot with the wheel; each scroll turn advances one theme and finishes before another starts. Keep readable labels alongside colors and honor reduced-motion preferences for the wheel.

## Typography

The application uses its established sans-serif stack. Questions may be long, so prompt text uses generous line height and never truncates.

## Layout

The file viewer keeps a source stage beside one learning-tool panel, collapsing to one column at 700px. Practice replaces the source inside the same stage so navigation remains spatially stable.

## Elevation & Depth

Borders provide structure. Shadows are faint and limited to focused study cards and transient layers.

## Shapes

Controls use compact 7px corners; panels and study cards use 12px–14px corners.

## Components

Learning tools share one segmented switch, stable busy controls, semantic fieldsets, visible focus, inline errors, and live answer feedback. Source navigation remains available throughout practice.

## Do's and Don'ts

- Do preserve compact density and source-first hierarchy, using the selected theme's semantic colors.
- Do use native controls and explicit labels for answer selection.
- Don't introduce decorative gradients, oversized metrics, or screen-specific token values.
