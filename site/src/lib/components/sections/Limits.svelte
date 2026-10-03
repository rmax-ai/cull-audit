<script lang="ts">
  import { base } from "$app/paths";
  import Section from "$lib/components/ui/Section.svelte";
  import { meta } from "$lib/data/meta";
</script>

<Section id="limits">
  <div class="grid gap-10 border-t border-slate-800 pt-16 md:grid-cols-[0.8fr_1.2fr] md:items-start">
    <div>
      <p class="eyebrow">07 / boundary</p>
      <h2 class="section-title">{meta.limits.title}</h2>
    </div>
    <div class="max-w-3xl">
      <p class="text-lg leading-8 text-slate-300">{meta.limits.copy}</p>
      <p class="mt-6 text-base leading-7 text-slate-400">{meta.limits.next}</p>
      <div class="mt-6 flex flex-wrap gap-x-6 gap-y-3 font-mono text-xs">
        {#each meta.limits.nextLinks as link}
          <a href={link[1]} target="_blank" rel="noreferrer" class="text-teal-300 hover:text-teal-200">{link[0]}</a>
        {/each}
      </div>
      <a href={`${base}/#study`} class="mt-8 inline-flex font-mono text-xs text-teal-300 hover:text-teal-200">Back to the protocol ↑</a>
    </div>
  </div>
</Section>
