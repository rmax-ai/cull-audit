# cull-audit v0.1.0

## What it is

`cull-audit` is a local-first verification harness for records produced by
AI photo-culling pipelines. It measures stage disagreement, repeat-read
stability, and reported usage cost. It is an audit layer, not an artistic
judge or a claim of human ground truth.

## Included

- versioned judgment records and the `validate` command;
- deterministic flip, stability, and cost metrics;
- an optional Gemini reference runner using an environment-only key;
- a keyless synthetic demo;
- a licensed open-photo demo manifest and offline verification tools;
- release, contribution, security, and producer-adapter guidance.

## Install

```bash
python -m pip install -e .
python -m cull_audit demo --output tmp/demo
```

## Limitations

Results depend on the producer, model, prompt, settings, input population,
and selected stages. The project does not establish the best photograph,
human ground truth, or universal model reliability. The default workflow is
local-first; provider calls are opt-in and require the user's own key.
