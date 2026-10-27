# Desktop workflows

Adapted from Impeccable's task-oriented design and interface-copy guidance. Load only the relevant section. Keep changes proportional to the user's request.

## Init, shape, document, extract

For `init`, inspect the current README and UI before recording product purpose, audience supported by evidence, core tasks, platform, language, and constraints in PRODUCT.md. Separate unknowns from facts and preserve existing context. Ask only for missing information that materially changes the design.

For `shape`, describe the task, entry point, normal path, important decisions, failure recovery, and completion state. Use current widgets and interaction patterns. Implement when implementation is part of the request; a planning-only request stops at the plan.

For `document`, derive DESIGN.md from observed styles and components rather than an imagined brand system. For `extract`, consolidate recurring ttk styles, spacing values, or widget patterns only when reuse benefits the actual code. Do not introduce abstraction for one occurrence.

## Critique and audit

Inspect a whole task, not isolated widgets. Identify unclear primary actions, misleading labels, inconsistent controls, crowded groups, weak selection or focus, missing feedback, and unsafe ambiguity around files. For an audit, also examine keyboard operation, contrast, long content, failure states, cancellation, and event-loop blocking.

Report concrete findings with their location, user impact, and a proportional correction. Separate observed problems from unverified risks. Do not assign arbitrary scores or run a web detector against Python widgets. A review alone does not authorize unrelated implementation.

## Polish, distill, quieter

Preserve the current identity and task flow. Fix alignment, spacing, font hierarchy, label consistency, state clarity, and unnecessary visual emphasis. Remove repeated explanations and decorative containers when they add no task information. Retain information needed for a meaningful decision, recovery, or file safety.

## Bolder, colorize, typeset, layout

Choose a specific weakness before changing styling: an indistinct main action, unreadable data, an unclear heading, or weak grouping. Adjust the relevant hierarchy or semantic color using shared styles. Check that selection, disabled text, errors, and keyboard focus stay distinct. Brand expression belongs in precise details and should not compete with library data or operation status.

## Clarify

Read the complete interaction path and write in Brazilian Portuguese using consistent product terminology. Controls name their action and object when needed. Persistent labels identify fields; example text does not replace a label.

An error states what failed, why when known, and what can be done. Avoid unsupported diagnoses or promises. Loading text names the real operation. Success confirms what actually completed; partial success retains visible failures. A confirmation names the affected object and consequence, and its action button names the operation.

Remove repeated prose while preserving meaning. Verify dynamic values, long paths, track names, plurals, and accessible names in context. Never invent product claims or change file-operation semantics through copy.

## Harden and onboard

Exercise the requested flow with realistic missing data, empty libraries, unavailable providers, invalid paths, failed operations, cancellation, and retries as relevant. Keep previously valid data intact according to existing contracts. Distinguish retryable failure from completed work.

For onboarding, explain the next useful step near the relevant control. Keep rare environment preparation in Settings when consistent with the current app. Do not add an introductory tour or mandatory wizard when a clear empty state and action suffice.

## Optimize

Reproduce and measure the delay before choosing a fix. Separate provider wait, file I/O, conversion, and Tkinter rendering. Inspect thread ownership, event scheduling, update frequency, and large list rendering where relevant. Preserve accurate feedback and cancellation. Compare the same operation before and after; describe limits when provider conditions differ.
