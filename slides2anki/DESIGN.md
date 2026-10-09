---
version: alpha
colors:
  ink: "#202222"
  paper: "#F4F0E8"
  panel: "#FFFCF7"
  terracotta: "#C85A45"
  moss: "#71816B"
  sand: "#E8DFD0"
  muted: "#766F66"
typography:
  display:
    fontFamily: "Georgia, 'Times New Roman', serif"
    fontSize: "clamp(2.4rem, 5vw, 4.8rem)"
    lineHeight: "0.95"
  body:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.95rem"
    lineHeight: "1.5"
  utility:
    fontFamily: "'SFMono-Regular', Consolas, monospace"
    fontSize: "0.7rem"
    lineHeight: "1.2"
rounded:
  card: "18px"
  control: "10px"
  pill: "999px"
spacing:
  unit: "4px"
components:
  primaryButton:
    background: "#202222"
    foreground: "#FFFCF7"
    radius: "10px"
  sampleCard:
    background: "#FFFCF7"
    border: "1px solid #E8DFD0"
    radius: "18px"
---

## Overview

An editorial study desk for turning lecture material into trustworthy Anki decks. The product should feel like annotated paper on a dark worktable: calm, inspectable, and a little tactile. The product register is focused and tool-like, with warmth reserved for the learning artifact.

The signature is the calibration stage: one large sample card sits in the visual center while feedback is expressed as a small set of legible editorial marks. Avoid generic gradients, glassmorphism, and dashboard chrome.

## Colors

Ink and paper are the structural pair. Terracotta marks the active learning decision; moss signals a completed, healthy state. Sand is for rules, borders, and quiet grouping. Never use terracotta as body text on paper.

## Typography

Georgia carries the human, study-notes voice only in major titles and card prompts. Inter is the everyday reading face. Monospace utility labels expose the pipeline stage, count, and file metadata with a restrained technical voice.

## Layout

Use a two-column application shell: a narrow, dark worktable rail and a flexible paper workspace. The workspace starts with a compact masthead and a generous main canvas. On narrow screens, the rail becomes a horizontal top bar and the two-column layout collapses to one column.

## Elevation & Depth

Prefer borders and tonal contrast over shadows. One faint shadow may support the active sample card so it reads as a physical card above the desk.

## Shapes

Large cards use 18px corners; controls use 10px corners; status tags are pill-shaped. Keep corners deliberate and avoid mixing arbitrary radii.

## Components

Buttons have clear solid, outline, and ghost emphasis. Upload uses a dashed boundary and a visible picker alternative. Feedback controls are compact pill buttons with a selected state that is never color-only.

## Do's and Don'ts

- Do make every pipeline stage visible and name the user's next action.
- Do keep generated content editable and reviewable before export.
- Don't hide the sample card behind a modal or make feedback feel like a survey.
- Don't use decorative imagery that competes with the cards.
