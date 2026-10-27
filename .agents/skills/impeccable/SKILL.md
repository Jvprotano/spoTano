---
name: impeccable
description: Improve spoTano Windows desktop UI in Python/Tkinter. Use for interface design, critique, audit, polish, simplification, typography, color, UX copy, onboarding, error handling, and documenting reusable visual conventions. Excludes backend-only tasks.
license: Apache-2.0
---

# Impeccable for spoTano desktop

This is a locally adapted edition of [Impeccable](https://github.com/pbakaus/impeccable), by Paul Bakaus, based on commit `d34c87e1a00989ae8dbdd7f6b30b70f23319e860` (upstream package version 4.8.0). Its original design principles and selected workflows have been rewritten for this repository. See [LICENSE](LICENSE) for upstream licensing.

## Product and scope

spoTano is a Windows desktop music library application built with Python and Tkinter/ttk. Its interface is in Brazilian Portuguese. Users follow Spotify playlists, maintain local MP3 files, and export them to a USB drive or folder. Read the current README and the relevant code in `spotano/gui.py` before proposing changes; this context is not a substitute for the implementation.

Design for mouse, keyboard, native Windows controls, and desktop task completion. Preserve familiar ttk affordances and current product behavior. Use the existing widget styles, fonts, spacing, and assets before introducing new conventions.

This edition contains no device-adaptation workflow. Do not add phone/tablet layouts, mobile-first rules, touch gestures, breakpoint systems, or a web frontend as part of applying it. Web detectors, browser hooks, and browser variant tooling are intentionally omitted. Desktop text scaling, legibility, keyboard access, and usable dialogs remain relevant.

## Working method

1. Inspect the requested screen, its task, and existing visual conventions. Read PRODUCT.md or DESIGN.md if present; missing design documents do not block a focused refinement.
2. Choose the smallest useful change. Refinement preserves identity, behavior, and factual copy outside the request. A requested redesign may replace the visual direction while retaining product truth and native affordances.
3. Read [reference/desktop-quality.md](reference/desktop-quality.md) before editing UI. Read the relevant section of [reference/workflows.md](reference/workflows.md) for a named operation.
4. Implement within Tkinter/ttk and keep background work from blocking the event loop. Do not add new frameworks or dependencies merely to follow a design technique.
5. Inspect the running desktop result when possible. Batch visual checks, fix what the inspection reveals, and report any verification that could not run. A build or static check alone does not establish visual quality.

The default mode is **Operate**: users need to complete tasks. Scanability, consistency, clear feedback, and native expectations take priority over decorative expression. For help text, prioritize comprehension.

## Supported operations

These names select sections of the workflow reference; they are instructions for the agent, not installed executable commands.

| Operation | Purpose |
|---|---|
| `init` | Capture verified product context in PRODUCT.md when requested |
| `shape` | Plan an interaction or screen before implementation |
| `document`, `extract` | Document existing visual conventions or consolidate repeated styles |
| `critique`, `audit` | Review task clarity, hierarchy, accessibility, states, and UI performance |
| `polish` | Finish alignment, spacing, typography, copy, and interaction details |
| `distill`, `quieter` | Remove unnecessary complexity or visual noise |
| `bolder`, `colorize`, `typeset`, `layout` | Improve emphasis, semantic color, text hierarchy, or grouping |
| `clarify` | Improve Portuguese labels, errors, and status messages |
| `harden` | Handle realistic content, failures, cancellation, and recovery |
| `onboard` | Improve first use and empty states |
| `optimize` | Investigate measured desktop UI performance problems |

Honor the user's requested operation and scope. For a general improvement request, inspect the screen and choose the relevant checks without requiring a command selection. A bare invocation can present a short menu of applicable operations.

Automatic upstream updates can restore removed material and overwrite this adaptation. Update only when requested, then review the incoming instructions against the desktop scope before replacing files.
