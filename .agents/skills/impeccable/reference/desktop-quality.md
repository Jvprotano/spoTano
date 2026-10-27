# Desktop quality floor

Adapted from Impeccable's craft-floor, Operate, and clarify guidance.

## Visual hierarchy

- Make the primary task and current selection easy to identify. Group related controls closely and separate unrelated tasks with space.
- Use a consistent spacing scale and align labels, fields, buttons, and table columns. Avoid nesting decorative panels where a clear group suffices.
- Prefer the existing system font and a restrained size/weight hierarchy. One family is usually enough. Keep labels and data readable; use consistent numeric alignment where it aids comparison.
- Use restrained surfaces and semantic colors. Accent identifies primary actions or selection. Do not rely on color alone for errors, warnings, selection, or completion.
- Aim for text contrast of at least 4.5:1 for ordinary text and 3:1 for large text. Check the actual rendered colors, including secondary text.
- Preserve standard controls, focus indicators, scrollbars, dialogs, and selection behavior. Do not redraw them solely to create a distinctive appearance.
- Avoid decorative gradients, glowing effects, gratuitous animation, and progress graphics that convey no real state. Product precision matters more than spectacle.

## Interaction and accessibility

- Verify keyboard traversal, visible focus, activation, selection, and appropriate shortcuts. Controls need meaningful visible labels.
- Check applicable enabled, disabled, selected, busy, error, empty, and completed states. Avoid indistinguishable controls or controls that appear available during incompatible work.
- Verify long playlist names, track names, paths, and Portuguese messages. Preserve access to full values through suitable columns, scrolling, details, or copy actions.
- Check the normal supported desktop window and Windows text/display scaling when available. Avoid clipped controls and inaccessible dialog actions. Do not invent a new minimum window size or change resizing policy without inspecting the existing app.
- Use native confirmation for operations whose consequences require an explicit decision. State what will happen to the actual files and library data.

## Product truth

- Use real operation names and states. Display counts, bytes, percentages, and elapsed stages only when backed by actual events or data; otherwise indicate ongoing work without a fabricated estimate.
- Preserve the distinction between playlist metadata, downloaded files, library membership, and exported copies. A visual redesign must not alter synchronization or removal semantics.
- Keep long operations off the Tkinter event loop and marshal widget updates through the existing UI scheduling pattern. Preserve cancellation and recovery.
- Empty states distinguish first use, no matches, and failure. Provide a useful next action.
- Errors explain what failed, the cause when known, and how to recover. Keep technical diagnostics available without making them the primary user-facing message.

## Verification

Exercise the changed interaction with realistic data and inspect the rendered desktop UI when possible. Check focus, labels, state transitions, relevant errors, and the actual result of the action. Run repository checks appropriate to any changed code. Report visual checks separately from automated checks, including unavailable runtime validation.
