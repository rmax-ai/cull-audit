<script lang="ts">
  import { base } from "$app/paths";
  import Section from "$lib/components/ui/Section.svelte";
  import { meta } from "$lib/data/meta";
</script>

<Section id="study">
  <div class="grid gap-10 md:grid-cols-[0.8fr_1.2fr]">
    <div>
      <p class="eyebrow">02 / protocol</p>
      <h2 class="section-title">{meta.study.label}</h2>
      <div class="mt-9 flex items-center gap-3 font-mono text-xs text-slate-500">
        <span class="h-2 w-2 rounded-full bg-teal-400"></span>
        frozen reference run
      </div>
    </div>
    <div>
      <p class="text-lg leading-8 text-slate-300">{meta.study.pipeline}</p>
      <div class="mt-8 grid gap-4 border-y border-slate-800 py-5 font-mono text-xs sm:grid-cols-2">
        <div>
          <span class="block text-slate-500">model</span>
          <strong class="mt-1 block font-normal text-slate-200">{meta.study.model}</strong>
        </div>
        <div>
          <span class="block text-slate-500">run envelope</span>
          <strong class="mt-1 block font-normal text-slate-200">{meta.study.calls}</strong>
        </div>
      </div>
    </div>
  </div>
  <div class="mt-14 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60 p-3 sm:p-5">
    <img src={`${base}/pipeline.svg`} alt="Diagram of the four audit passes from 77 photos to repeat reads" class="w-full min-w-[720px]" />
  </div>
  <p class="mt-5 max-w-4xl font-mono text-[11px] leading-6 text-slate-500">{meta.study.provenance}</p>
</Section>
