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
    <div>
      <p class="max-w-3xl text-lg leading-8 text-slate-300">{meta.limits.copy}</p>
      <a href={`${base}/#study`} class="mt-8 inline-flex font-mono text-xs text-teal-300 hover:text-teal-200">Back to the protocol ↑</a>
    </div>
  </div>
</Section>
