export type Verdict = "accept" | "maybe" | "reject";
export type TransitionTone = "slate" | "amber" | "red";

export type Flip = {
  id: string;
  title: string;
  filename: string;
  before: number;
  after: number;
  from: Verdict;
  to: Verdict;
  image: string;
  page: string;
  headline?: boolean;
};

export const attribution = {
  creator: "Nick Webb from London, United Kingdom",
  license: "CC BY 2.0",
  licenseUrl: "https://creativecommons.org/licenses/by/2.0",
  source: "Wikimedia Commons"
} as const;

export const meta = {
  hero: {
    kicker: "cull-audit · public demo study",
    title: "A top-scoring pick became a reject.",
    sub:
      "A local-first verification harness for records from AI photo-culling pipelines: bring JSON/JSONL judgments and it writes a flip table, repeat-stability classes, and cost evidence to audit.json and report.md. The study below audits one 67-call reference run on an openly licensed photo set — an example produced with the optional runner.",
    links: {
      study: "Read the study ↓",
      tool: "Get the tool ↗",
      release: "v0.1.0 release ↗"
    },
    toolUrl: "https://github.com/rmax-ai/cull-audit",
    releaseUrl: "https://github.com/rmax-ai/cull-audit/releases/tag/v0.1.0"
  },
  stats: [
    "77 photos",
    "67 provider calls",
    "135 records",
    "21 paired",
    "6 flips (all downward)",
    "8/8 repeat groups robust",
    "$0.2737 estimated"
  ],
  problem: {
    first:
      "AI culling pipelines often expose scores and rankings that invite more confidence than a single read warrants. cull-audit asks a narrower, answerable question: what do the records actually say — and what happens when the same question is asked again, alone and at higher resolution?",
    second:
      "It audits what a culler's records say about stage disagreement, repeat stability, and cost. It never claims human ground truth."
  },
  study: {
    label: "What was run",
    foundLabel: "What this run found",
    found: [
      "6 of 21 paired finalists flipped downward",
      "8/8 eligible repeat groups robust",
      "$0.273687 estimated across 67 calls"
    ],
    pipeline:
      "77 openly licensed photos (Wikimedia Commons, CC BY 2.0) → nine contact sheets, up to nine photos each (triage reads, relative context) → 21 dedicated reads (1536 px, one photo each) → 21 face crops (enrichment) → 16 repeat reads (8 groups × 2, identical settings).",
    model: "gemini-3-flash-preview",
    calls: "67 provider calls, 135 judgment records, 34m23s wall clock.",
    provenance:
      "Every number on this page reproduces from the frozen artifacts in the repository: examples/open-demo/run-2026-10-03 (audit.json, report.md, RUN-NOTES.md)."
  },
  flips: {
    title: "Six finalists fell on a dedicated read.",
    copy:
      "The triage pass judges a photo inside a contact sheet; the dedicated pass reads each finalist alone, at higher resolution. Of the 21 paired finalists (all triage accepts), 6 flipped — every one downward: 2 accept→reject, 4 accept→maybe; 15 stayed accept. The other 56 photos had no dedicated comparison. This run shows the disagreement; it does not isolate whether sheet context, resolution, or other stage differences caused any single change.",
    intro: "The six flips, with the actual photographs — scores are composites (0–100):",
    transitions: [
      { count: 15, from: "accept", to: "accept", tone: "slate" },
      { count: 4, from: "accept", to: "maybe", tone: "amber" },
      { count: 2, from: "accept", to: "reject", tone: "red" }
    ] satisfies Array<{ count: number; from: Verdict; to: Verdict; tone: TransitionTone }>
  },
  stability: {
    title: "Ranking is not stability.",
    copy:
      "The top eight finalists were read twice under identical settings. All eight came back robust: identical verdicts, composite spread within the v1 threshold (mostly 0; one spread of 3). A verdict that survives a re-read is evidence; a rank position is not.",
    metric: "two reads per selected photo · identical verdicts · composite spread ≤ 5 under v1",
    boundary:
      "This tests only these two configured repeats for these eight photos — not ranking stability, and not general model reliability.",
    groups: [
      { id: "0002", spread: 0 },
      { id: "0008", spread: 0 },
      { id: "0015", spread: 0 },
      { id: "0016", spread: 0 },
      { id: "0019", spread: 3 },
      { id: "0022", spread: 0 },
      { id: "0033", spread: 0 },
      { id: "0072", spread: 0 }
    ]
  },
  cost: {
    title: "This run's estimated usage cost.",
    copy:
      "Estimated across 67 calls: $0.273687 from a pinned price table (documented in the repository). 67 records carry usage for 67 calls; the other 68 records — triage siblings sharing one billed call per sheet — have no separate bill. \"Known $0\" means no known-price records, not free provider usage.",
    rows: [
      ["triage", "$0.0775845", "9 calls"],
      ["dedicated", "$0.102256", "21 calls"],
      ["face", "$0.0537015", "21 calls"],
      ["repeat", "$0.040145", "16 calls"]
    ],
    tokens: "80,928 in · 18,559 out · 59,182 thinking",
    tokenNote: "thinking-token counts may overlap output-token counts (per the frozen report's warnings)"
  },
  reproduce: {
    title: "Run it, inspect it.",
    syntheticLabel: "Try the audit mechanics — keyless and image-free, on invented records:",
    code: [
      "git clone https://github.com/rmax-ai/cull-audit",
      "cd cull-audit",
      "uv venv && uv pip install -e .",
      "python -m cull_audit demo --output tmp/demo"
    ],
    syntheticNote: "This synthetic demo exercises the mechanics; it does not reproduce the 77-photo study.",
    studyLabel: "Check the study — rerun the audit on the frozen judgments:",
    studyCode: [
      "python -m cull_audit audit \\",
      "  --judgments examples/open-demo/run-2026-10-03/judgments.json \\",
      "  --baseline-stage triage --decisive-stage dedicated \\",
      "  --prices examples/open-demo/price-table-gemini-3-flash-preview-2026-10.json \\",
      "  --output tmp/audit-check --source-date-epoch 1791029022"
    ],
    studyNote: "Produces the same aggregates as the committed audit (6/21 flips, 8/8 robust, $0.273687). Byte-identical output means rerunning the audit on identical frozen inputs — not rerunning the live provider; the staged-workspace procedure is in RUN-NOTES. The optional reference runner (your own key, dry-run gate first) is how the study itself was produced.",
    links: [
      [
        "Frozen run artifacts ↗",
        "https://github.com/rmax-ai/cull-audit/tree/main/examples/open-demo/run-2026-10-03"
      ],
      ["README ↗", "https://github.com/rmax-ai/cull-audit#readme"],
      [
        "Judgment schema ↗",
        "https://github.com/rmax-ai/cull-audit/blob/main/schemas/judgments.schema.json"
      ]
    ]
  },
  limits: {
    title: "What this cannot say.",
    copy:
      "One licensed set, one model snapshot, one prompt configuration: these are demonstration receipts, not a benchmark. No claim of human ground truth; provider outputs drift; aesthetic judgment stays with people.",
    next:
      "The audit is the point, and it is open to challenge: inspect the frozen audit.json and report.md, run the synthetic smoke test, or bring your own records and pressure-test the pairing rules, stability thresholds, and cost attribution.",
    nextLinks: [
      ["Import guide ↗", "https://github.com/rmax-ai/cull-audit#3-audit-records-from-another-tool"],
      ["Contribution guide ↗", "https://github.com/rmax-ai/cull-audit/blob/main/CONTRIBUTING.md"]
    ]
  },
  footer:
    "Photographs: Nick Webb (London, United Kingdom), CC BY 2.0, via Wikimedia Commons — hotlinked with attribution from the demo manifest; not redistributed. Code: MIT. Site built from the v0.1.0 release artifacts.",
  flipsData: [
    {
      id: "0026",
      title: "DSC 2952",
      filename: "0026.jpg",
      from: "accept",
      to: "maybe",
      before: 88,
      after: 52,
      image:
        "https://commons.wikimedia.org/wiki/Special:FilePath/DSC_2952_%287662279904%29.jpg?width=1000",
      page: "https://commons.wikimedia.org/wiki/File:DSC_2952_(7662279904).jpg"
    },
    {
      id: "0037",
      title: "DSC 3051",
      filename: "0037.jpg",
      from: "accept",
      to: "maybe",
      before: 85,
      after: 62,
      image:
        "https://commons.wikimedia.org/wiki/Special:FilePath/DSC_3051_%287662408140%29.jpg?width=1000",
      page: "https://commons.wikimedia.org/wiki/File:DSC_3051_(7662408140).jpg"
    },
    {
      id: "0050",
      title: "DSC 3228",
      headline: true,
      filename: "0050.jpg",
      from: "accept",
      to: "reject",
      before: 92,
      after: 45,
      image:
        "https://commons.wikimedia.org/wiki/Special:FilePath/DSC_3228_%287662604466%29.jpg?width=1000",
      page: "https://commons.wikimedia.org/wiki/File:DSC_3228_(7662604466).jpg"
    },
    {
      id: "0058",
      title: "Mike Oldfield",
      filename: "0058.jpg",
      from: "accept",
      to: "maybe",
      before: 92,
      after: 55,
      image:
        "https://commons.wikimedia.org/wiki/Special:FilePath/Mike_Oldfield_%287662481762%29.jpg?width=1000",
      page: "https://commons.wikimedia.org/wiki/File:Mike_Oldfield_(7662481762).jpg"
    },
    {
      id: "0063",
      title: "Smoking",
      filename: "0063.jpg",
      from: "accept",
      to: "reject",
      before: 86,
      after: 35,
      image:
        "https://commons.wikimedia.org/wiki/Special:FilePath/Smoking_%287662451492%29.jpg?width=1000",
      page: "https://commons.wikimedia.org/wiki/File:Smoking_(7662451492).jpg"
    },
    {
      id: "0064",
      title: "Sun Dance",
      filename: "0064.jpg",
      from: "accept",
      to: "maybe",
      before: 88,
      after: 62,
      image:
        "https://commons.wikimedia.org/wiki/Special:FilePath/Sun_Dance_%287662618466%29.jpg?width=1000",
      page: "https://commons.wikimedia.org/wiki/File:Sun_Dance_(7662618466).jpg"
    }
  ] satisfies Flip[]
} as const;

export const dataset = {
  label: "The set, and why it is this one",
  copy: "The demo runs on one coherent, openly licensed event set — fixed and licensed before any model touched a frame.",
  criteria: [
    "Scale: 60–120 photos — large enough that frames compete for the same slot, small enough to inspect every outcome by hand. This set uses 77.",
    "Coherence: one event, not a stock collage. Flips are meaningful when near-duplicate frames from the same session are judged against each other.",
    "License clarity: only per-asset CC0, CC BY, or CC BY-SA with a stable author and source record. Anything unclear is excluded.",
    "Fixed in advance: the set was licensed, SHA-256 verified, and frozen before the run — selection followed the event, not the results.",
    "Manifest-first: every asset carries a source URL, creator, license, attribution text, and a content hash. The manifest is the authority.",
    "No redistribution: the repository ships the manifest and a fetch script; photographs stay at their source, and this page hotlinks them with attribution."
  ],
  facts: [
    ["photos", "77 — one event: London 2012 opening ceremony"],
    ["creator", "Nick Webb (London, United Kingdom)"],
    ["license", "CC BY 2.0 — verified per asset"],
    ["integrity", "SHA-256 per file; manifest in examples/open-demo"],
    ["acquisition", "scripted, fetch-only — no image files committed"]
  ]
} as const;

export const sheet = {
  label: "What the triage pass saw",
  copy: "Relative reads happen inside sheets like this one: nine frames judged together in a single call — sheet 7 of 9. Two of this sheet's frames flipped downward when read alone, marked below; whether the neighbours caused the change is not something this run isolates.",
  note: "Tiles are hotlinked Wikimedia Commons thumbnails; each links to its source page. Photographs: Nick Webb, CC BY 2.0.",
  tiles: [
    { pos: 1, file: "0055.jpg", title: "Danny Boyle", verdict: "accept", composite: 85, flip: null,
      image: "https://commons.wikimedia.org/wiki/Special:FilePath/Danny_Boyle_%287662179152%29.jpg?width=400",
      page: "https://commons.wikimedia.org/wiki/File:Danny_Boyle_(7662179152).jpg" },
    { pos: 2, file: "0056.jpg", title: "Green and Pleasant Land", verdict: "maybe", composite: 65, flip: null,
      image: "https://commons.wikimedia.org/wiki/Special:FilePath/Green_and_Pleasant_Land_%287662168214%29.jpg?width=400",
      page: "https://commons.wikimedia.org/wiki/File:Green_and_Pleasant_Land_(7662168214).jpg" },
    { pos: 3, file: "0057.jpg", title: "Here's To Everyone Who Gives Their Best", verdict: "maybe", composite: 55, flip: null,
      image: "https://commons.wikimedia.org/wiki/Special:FilePath/Here%27s_To_Everyone_Who_Gives_Their_Best_%287662150706%29.jpg?width=400",
      page: "https://commons.wikimedia.org/wiki/File:Here's_To_Everyone_Who_Gives_Their_Best_(7662150706).jpg" },
    { pos: 4, file: "0058.jpg", title: "Mike Oldfield", verdict: "accept", composite: 92, flip: { to: "maybe", after: 55 },
      image: "https://commons.wikimedia.org/wiki/Special:FilePath/Mike_Oldfield_%287662481762%29.jpg?width=400",
      page: "https://commons.wikimedia.org/wiki/File:Mike_Oldfield_(7662481762).jpg" },
    { pos: 5, file: "0059.jpg", title: "Olympic Rings Converge", verdict: "accept", composite: 82, flip: null,
      image: "https://commons.wikimedia.org/wiki/Special:FilePath/Olympic_Rings_Converge_%287662424656%29.jpg?width=400",
      page: "https://commons.wikimedia.org/wiki/File:Olympic_Rings_Converge_(7662424656).jpg" },
    { pos: 6, file: "0060.jpg", title: "Olympic Stadium", verdict: "accept", composite: 88, flip: null,
      image: "https://commons.wikimedia.org/wiki/Special:FilePath/Olympic_Stadium_%287662105508%29.jpg?width=400",
      page: "https://commons.wikimedia.org/wiki/File:Olympic_Stadium_(7662105508).jpg" },
    { pos: 7, file: "0061.jpg", title: "Orbit & The Olympic Stadium", verdict: "maybe", composite: 60, flip: null,
      image: "https://commons.wikimedia.org/wiki/Special:FilePath/Orbit_%26_The_Olypmic_Stadium_%287662118386%29.jpg?width=400",
      page: "https://commons.wikimedia.org/wiki/File:Orbit_%26_The_Olypmic_Stadium_(7662118386).jpg" },
    { pos: 8, file: "0062.jpg", title: "Royal Box", verdict: "reject", composite: 35, flip: null,
      image: "https://commons.wikimedia.org/wiki/Special:FilePath/Royal_Box_%287662466136%29.jpg?width=400",
      page: "https://commons.wikimedia.org/wiki/File:Royal_Box_(7662466136).jpg" },
    { pos: 9, file: "0063.jpg", title: "Smoking", verdict: "accept", composite: 86, flip: { to: "reject", after: 35 },
      image: "https://commons.wikimedia.org/wiki/Special:FilePath/Smoking_%287662451492%29.jpg?width=400",
      page: "https://commons.wikimedia.org/wiki/File:Smoking_(7662451492).jpg" }
  ]
} as const;

export const sections = {
  links: {
    github: "https://github.com/rmax-ai/cull-audit",
    license: attribution.licenseUrl
  }
};
