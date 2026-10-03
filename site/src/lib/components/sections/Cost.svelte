<script lang="ts">
  import Section from "$lib/components/ui/Section.svelte";
  import { meta } from "$lib/data/meta";
</script>

<Section id="cost">
  <div class="grid gap-10 md:grid-cols-[0.8fr_1.2fr] md:items-start">
    <div>
      <p class="eyebrow">05 / accounting</p>
      <h2 class="section-title">{meta.cost.title}</h2>
    </div>
    <p class="max-w-3xl text-lg leading-8 text-slate-300">{meta.cost.copy}</p>
  </div>
  <div class="mt-12 grid gap-8 md:grid-cols-[1fr_0.75fr]">
    <div class="overflow-hidden rounded-xl border border-slate-800">
      {#each meta.cost.rows as row, index}
        <div class="grid grid-cols-[1fr_auto_auto] gap-4 border-b border-slate-800 px-5 py-4 font-mono text-xs last:border-0">
          <span class="text-slate-300">{row[0]}</span>
          <span class="text-slate-100">{row[1]}</span>
          <span class="text-slate-500">{row[2]}</span>
        </div>
        {#if index === 3}
          <div class="grid grid-cols-[1fr_auto] gap-4 bg-teal-400/10 px-5 py-4 font-mono text-xs">
            <span class="text-teal-200">estimated total</span>
            <strong class="font-normal text-teal-200">$0.273687</strong>
          </div>
        {/if}
      {/each}
    </div>
    <div class="rounded-xl border border-slate-800 bg-slate-900/40 p-5">
      <span class="font-mono text-[10px] uppercase tracking-[0.16em] text-slate-500">token envelope</span>
      <p class="mt-5 font-mono text-sm leading-7 text-slate-200">{meta.cost.tokens}</p>
      <div class="mt-7 h-px bg-slate-800"></div>
      <p class="mt-5 text-sm leading-6 text-slate-500">Known / estimated / unknown stay separate. No guessed bills.</p>
    </div>
  </div>
</Section>
