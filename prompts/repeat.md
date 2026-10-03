# Repeat reference read

Prompt version: repeat-v1

Review this exact prepared input with the exact repeat settings. Return JSON
only with `verdict` (`accept`, `maybe`, or `reject`), `composite` from 0 to
100, `scores`, `reasons`, and `kill_factors`.

Treat this as a repeatability measurement, not a claim of human ground truth.
The runner will associate responses made with the same bytes, prompt, model,
and generation settings.
