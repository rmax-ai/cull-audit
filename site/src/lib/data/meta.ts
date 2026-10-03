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
    title: "The number-one pick became a reject.",
    sub:
      "A local-first audit of a 67-call reference run on an openly licensed photo set — where relative reads flip, why ranking is not stability, and what the skepticism actually cost. An audit layer, not another judge.",
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
      "Every AI culling pipeline emits scores, and teams read the top of the list as fact. cull-audit asks a narrower, answerable question: what do the records actually say — and what happens when the same question is asked again, alone and at higher resolution?",
    second:
      "It audits what a culler's records say about stage disagreement, repeat stability, and cost. It never claims human ground truth."
  },
  study: {
    label: "What was run",
    pipeline:
      "77 openly licensed photos (Wikimedia Commons, CC BY 2.0) → 9 nine-up contact sheets (triage reads, relative context) → 21 dedicated reads (1536 px, one photo each) → 21 face crops (enrichment) → 16 repeat reads (8 groups × 2, identical settings).",
    model: "gemini-3-flash-preview",
    calls: "67 provider calls, 135 judgment records, 34m23s wall clock.",
    provenance:
      "Every number on this page reproduces from the frozen artifacts in the repository: examples/open-demo/run-2026-10-03 (audit.json, report.md, RUN-NOTES.md)."
  },
  flips: {
    title: "Relative reads flatter.",
    copy:
      "The triage pass judges a photo inside a 9-up sheet; the dedicated pass reads each finalist alone. Of 21 paired finalists, 6 flipped — every one downward: 2 accept→reject, 4 accept→maybe; 15 stayed accept.",
    intro: "The six flips, with the actual photographs:",
    transitions: [
      { count: 15, from: "accept", to: "accept", tone: "slate" },
      { count: 4, from: "accept", to: "maybe", tone: "amber" },
      { count: 2, from: "accept", to: "reject", tone: "red" }
    ] satisfies Array<{ count: number; from: Verdict; to: Verdict; tone: TransitionTone }>
  },
  stability: {
    title: "Ranking is not stability.",
    copy:
      "The top eight finalists were read twice under identical settings. All 8 groups came back robust — identical verdicts, composite spread within the v1 threshold (mostly 0; one spread of 3, still robust). A verdict that survives a re-read is evidence; a rank position is not.",
    spreads: [0, 0, 0, 0, 0, 0, 0, 3]
  },
  cost: {
    title: "Skepticism was cheap.",
    copy:
      "Estimated total across 67 calls: $0.273687 (pinned price table, documented in the repository). Record-level accounting keeps known / estimated / unknown distinct — never guessed: known $0, estimated 67 records, unknown 68 (triage siblings with no billed call of their own).",
    rows: [
      ["triage", "$0.0775845", "9 calls"],
      ["dedicated", "$0.102256", "21"],
      ["face", "$0.0537015", "21"],
      ["repeat", "$0.040145", "16"]
    ],
    tokens: "80,928 in · 18,559 out · 59,182 thinking"
  },
  reproduce: {
    title: "Run it, inspect it.",
    code: [
      "git clone https://github.com/rmax-ai/cull-audit",
      "cd cull-audit",
      "uv venv && uv pip install -e .",
      "python -m cull_audit demo --output tmp/demo   # keyless, image-free"
    ],
    note:
      "The optional reference runner uses your own provider key and a dry-run gate first; the demo above needs no network beyond the initial clone/install.",
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
      "One licensed set, one model snapshot, one prompt configuration: these are demonstration receipts, not a benchmark. No claim of human ground truth; provider outputs drift; aesthetic judgment stays with people. The value is the audit itself — the evidence flips are visible at all."
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

export const sections = {
  links: {
    github: "https://github.com/rmax-ai/cull-audit",
    license: attribution.licenseUrl
  }
};
