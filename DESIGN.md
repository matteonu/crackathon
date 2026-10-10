---
version: alpha
colors:
  canvas: "#f5f6f1"
  surface: "#ffffff"
  ink: "#263127"
  muted: "#78866f"
  primary: "#496a48"
  line: "#e3e7df"
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
    description: "A bordered white tool surface beside the source viewer."
---

## Overview

Studyphase is a calm, compact academic workspace. Its visual reference is a well-kept study notebook: restrained sage surfaces, clear ink, and dense controls that leave the source material in charge. Product familiarity wins over decoration; the PDF and the current learning prompt are the signature elements.

## Colors

Semantic state colors supplement the neutral green system. Green communicates selection and success; muted red is reserved for errors. Runtime values are owned by the CSS custom properties and shared component classes in `frontend/src/styles.css`; this document records their roles rather than creating a second token implementation.

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

- Do preserve the existing sage palette, compact density, and source-first hierarchy.
- Do use native controls and explicit labels for answer selection.
- Don't introduce decorative gradients, oversized metrics, or screen-specific token values.
