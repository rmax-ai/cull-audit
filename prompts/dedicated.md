# Dedicated reference read

Prompt version: dedicated-v1

Review the supplied photograph as an absolute read at the prepared input
size. Return JSON only with `verdict` (`accept`, `maybe`, or `reject`),
`composite` from 0 to 100, `scores`, `reasons`, and `kill_factors`.

When a face or important detail is visible and a crop can be identified,
also return `bbox` as normalized `x0,y0,x1,y1` coordinates in the range
`[0,1]`. Judge visible evidence only. Do not claim human ground truth.
