<script lang="ts">
  import { base } from "$app/paths";
  import Section from "$lib/components/ui/Section.svelte";
  import { meta } from "$lib/data/meta";
</script>

<Section>
  <div class="grid gap-10 md:grid-cols-[0.8fr_1.2fr] md:items-start">
    <div>
      <p class="eyebrow">01 / premise</p>
      <h2 class="section-title">A score is a lead,<br class="hidden md:block" /> not a verdict.</h2>
    </div>
    <div class="max-w-3xl text-lg leading-8 text-slate-300">
      <p>{meta.problem.first}</p>
      <p class="mt-6 border-l-2 border-teal-400/60 pl-5 text-base leading-7 text-slate-400">{meta.problem.second}</p>
      <a href={`${base}/#study`} class="mt-7 inline-flex font-mono text-xs text-teal-300 transition hover:text-teal-200">Follow the receipts <span class="ml-2">↓</span></a>
    </div>
  </div>
  <div class="mt-14 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60 p-3 sm:p-5">
    <img src={`${base}/dataflow.svg`} alt="Diagram of producer records flowing through validation and audit into evidence files" class="w-full min-w-[720px]" />
    <p class="mt-2 font-mono text-[10px] text-slate-500 md:hidden">Scroll horizontally to see the full diagram ↗</p>
  </div>
</Section>
