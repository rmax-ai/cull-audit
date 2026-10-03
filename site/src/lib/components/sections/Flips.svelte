<script lang="ts">
  import Section from "$lib/components/ui/Section.svelte";
import { attribution, meta, type Verdict } from "$lib/data/meta";

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

  <div class="mt-12 grid overflow-hidden rounded-xl border border-slate-800 sm:grid-cols-3">
    {#each meta.flips.transitions as transition}
      <div class={`transition-bar transition-${transition.tone}`}>
        <strong>{transition.count}</strong><span>{transition.from} → {transition.to}</span>
      </div>
    {/each}
  </div>

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
