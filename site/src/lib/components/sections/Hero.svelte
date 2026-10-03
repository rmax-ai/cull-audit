<script lang="ts">
  import { base } from "$app/paths";
  import { meta } from "$lib/data/meta";
</script>

<section class="relative overflow-hidden border-b border-slate-800/80">
  <div class="absolute inset-0 bg-[radial-gradient(circle_at_70%_20%,rgba(20,184,166,0.09),transparent_32%),linear-gradient(180deg,rgba(15,23,42,0.7),transparent)]"></div>
  <div class="relative max-w-6xl mx-auto px-6 pt-24 pb-16 md:pt-32 md:pb-24">
    <div class="max-w-4xl">
      <p class="font-mono text-xs tracking-[0.18em] uppercase text-teal-400">{meta.hero.kicker}</p>
      <h1 class="mt-5 max-w-4xl text-5xl font-semibold tracking-[-0.055em] text-slate-100 sm:text-6xl md:text-7xl">
        {meta.hero.title}
      </h1>
      <p class="mt-7 max-w-3xl text-lg leading-8 text-slate-400 md:text-xl">{meta.hero.sub}</p>
      <div class="mt-9 flex flex-wrap gap-3">
        <a class="button button-primary" href={`${base}/#study`}>{meta.hero.links.study}</a>
        <a class="button button-quiet" href={meta.hero.toolUrl} target="_blank" rel="noreferrer">{meta.hero.links.tool}</a>
        <a class="button button-quiet" href={meta.hero.releaseUrl} target="_blank" rel="noreferrer">{meta.hero.links.release}</a>
      </div>
    </div>
    <div class="mt-16 flex flex-wrap items-center gap-x-2 gap-y-2 border-y border-slate-800 py-5 font-mono text-[11px] leading-5 text-slate-400">
      {#each meta.stats as stat, index}
        {#if index > 0}<span class="px-2 text-slate-700" aria-hidden="true">·</span>{/if}
        <span class="py-1">{stat}</span>
      {/each}
    </div>
  </div>
</section>
