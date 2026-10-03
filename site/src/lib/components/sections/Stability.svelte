<script lang="ts">
  import Section from "$lib/components/ui/Section.svelte";
  import { meta } from "$lib/data/meta";
</script>

<Section id="stability">
  <div class="grid gap-10 md:grid-cols-[0.8fr_1.2fr] md:items-start">
    <div>
      <p class="eyebrow">04 / repeatability</p>
      <h2 class="section-title">{meta.stability.title}</h2>
    </div>
    <div class="max-w-3xl">
      <p class="text-lg leading-8 text-slate-300">{meta.stability.copy}</p>
      <p class="mt-5 font-mono text-xs text-slate-400">{meta.stability.metric}</p>
    </div>
  </div>
  <div class="mt-12 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
    {#each meta.stability.groups as group}
      <div class="rounded-lg border border-emerald-400/30 bg-emerald-400/10 p-4 text-center">
        <span class="block font-mono text-[10px] text-emerald-300/70">{group.id}</span>
        <strong class="mt-2 block font-mono text-lg font-normal text-emerald-200">robust</strong>
        <span class="mt-1 block font-mono text-[10px] text-emerald-300/70">spread {group.spread}</span>
      </div>
    {/each}
  </div>
  <p class="mt-5 max-w-3xl font-mono text-xs leading-6 text-slate-400">{meta.stability.boundary}</p>
</Section>
