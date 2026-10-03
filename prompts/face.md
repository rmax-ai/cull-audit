# Face reference read

Prompt version: face-v1

Review the supplied margin crop as a focused face or detail read. Return JSON
only with `verdict` (`accept`, `maybe`, or `reject`), `composite` from 0 to
100, `scores`, `reasons`, and `kill_factors`.

Use only visible evidence in the crop. Do not identify a person and do not
claim human ground truth.
