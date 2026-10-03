<script lang="ts">
  import { base } from "$app/paths";
  import Section from "$lib/components/ui/Section.svelte";
  import { meta } from "$lib/data/meta";
</script>

<Section id="reproduce">
  <div class="grid gap-10 md:grid-cols-[0.8fr_1.2fr] md:items-start">
    <div>
      <p class="eyebrow">06 / method</p>
      <h2 class="section-title">{meta.reproduce.title}</h2>
    </div>
    <div>
      <pre class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950 p-5 font-mono text-xs leading-7 text-slate-300"><code>{meta.reproduce.code.join("\n")}</code></pre>
      <p class="mt-5 text-sm leading-6 text-slate-500">{meta.reproduce.note}</p>
      <div class="mt-7 flex flex-wrap gap-x-6 gap-y-3 font-mono text-xs">
        {#each meta.reproduce.links as link}
          <a href={link[1]} target="_blank" rel="noreferrer" class="text-teal-300 hover:text-teal-200">{link[0]}</a>
        {/each}
      </div>
    </div>
  </div>
  <div class="mt-14 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/60 p-3 sm:p-5">
    <img src={`${base}/dataflow.svg`} alt="Diagram of producer records flowing through validation and audit into evidence files" class="w-full min-w-[720px]" />
  </div>
</Section>
