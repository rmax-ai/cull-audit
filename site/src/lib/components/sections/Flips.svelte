<script lang="ts">
  import Section from "$lib/components/ui/Section.svelte";
import { attribution, meta, sheet, type Verdict } from "$lib/data/meta";

  const chipClass = (verdict: Verdict) =>
    verdict === "accept"
      ? "verdict-accept"
      : verdict === "maybe"
        ? "verdict-maybe"
        : "verdict-reject";
</script>

<Section id="flips">
  <div class="grid gap-10 md:grid-cols-[0.8fr_1.2fr] md:items-start">
    <div>
      <p class="eyebrow">03 / disagreement</p>
      <h2 class="section-title">{meta.flips.title}</h2>
    </div>
    <p class="max-w-3xl text-lg leading-8 text-slate-300">{meta.flips.copy}</p>
  </div>

  <div class="mt-12 rounded-xl border border-slate-800 bg-slate-900/40 p-6 sm:p-8">
    <p class="eyebrow">{sheet.label}</p>
    <p class="mt-4 max-w-3xl text-slate-300">{sheet.copy}</p>
    <div class="mt-6 grid max-w-3xl grid-cols-3 gap-2">
      {#each sheet.tiles as tile}
        <a
          href={tile.page}
          target="_blank"
          rel="noreferrer"
          class={`group relative block overflow-hidden rounded-md border bg-slate-950 ${tile.flip ? "border-amber-500/60" : "border-slate-800"}`}
        >
          <span class="absolute left-1.5 top-1.5 z-10 rounded bg-slate-950/80 px-1.5 font-mono text-[10px] text-slate-300">{tile.pos}</span>
          <img
            src={tile.image}
            alt={`${tile.title} — Nick Webb, CC BY 2.0, Wikimedia Commons`}
            loading="lazy"
            class="aspect-[3/2] w-full object-cover opacity-90 transition group-hover:opacity-100"
          />
          {#if tile.flip}
            <span class={`absolute bottom-1.5 right-1.5 rounded px-1.5 py-0.5 font-mono text-[10px] ${tile.flip.to === "reject" ? "bg-red-500/25 text-red-300" : "bg-amber-500/25 text-amber-300"}`}>
              → {tile.flip.to} {tile.flip.after}
            </span>
          {/if}
        </a>
      {/each}
    </div>
    <p class="mt-4 font-mono text-[11px] text-slate-500">{sheet.note}</p>
  </div>

  <div class="mt-12 grid overflow-hidden rounded-xl border border-slate-800 sm:grid-cols-3">
    {#each meta.flips.transitions as transition}
      <div class={`transition-bar transition-${transition.tone}`}>
        <strong>{transition.count}</strong><span>{transition.from} → {transition.to}</span>
      </div>
    {/each}
  </div>

  <p class="mt-6 max-w-3xl text-sm leading-6 text-slate-400">
    These six cards are every flip among the 21 paired photos — the complete set of verdict changes, nothing curated out.
  </p>

  <p class="mt-12 font-mono text-xs uppercase tracking-[0.14em] text-slate-500">{meta.flips.intro}</p>
  <div class="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
    {#each meta.flipsData as flip}
      <article class="group overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60">
        <a href={flip.page} target="_blank" rel="noreferrer" class="block overflow-hidden bg-slate-950">
          <img
            src={flip.image}
            alt={`${flip.title}, Wikimedia Commons photograph`}
            loading="lazy"
            class="aspect-[4/3] w-full rounded-t-xl border-b border-slate-800 object-cover transition duration-500 group-hover:scale-[1.03]"
          />
        </a>
        <div class="p-4">
          <div class="flex items-start justify-between gap-3">
            <a href={flip.page} target="_blank" rel="noreferrer" class="font-mono text-xs text-slate-200 hover:text-teal-300">{flip.filename} · {flip.title}</a>
            <span class="font-mono text-xs text-red-300">(−{flip.before - flip.after})</span>
          </div>
          <div class="mt-3 flex items-center gap-2 text-[11px]">
            <span class={`verdict-chip ${chipClass(flip.from)}`}>{flip.from} {flip.before}</span>
            <span class="text-slate-600">→</span>
            <span class={`verdict-chip ${chipClass(flip.to)}`}>{flip.to} {flip.after}</span>
          </div>
          <p class="mt-4 text-[11px] leading-5 text-slate-500">
            {attribution.creator} ·
            <a href={attribution.licenseUrl} target="_blank" rel="noreferrer" class="text-slate-400 underline decoration-slate-700 underline-offset-2 hover:text-teal-300">{attribution.license}</a>
            ·
            <a href={flip.page} target="_blank" rel="noreferrer" class="text-slate-400 underline decoration-slate-700 underline-offset-2 hover:text-teal-300">{attribution.source}</a>
          </p>
        </div>
      </article>
    {/each}
  </div>
</Section>
