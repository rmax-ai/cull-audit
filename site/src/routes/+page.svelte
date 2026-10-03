<svelte:head>
  <title>cull-audit — The Flip Table</title>
  <meta
    name="description"
    content="A visual study of a 67-call reference run: where AI culling verdicts flip, why ranking is not stability, and what the skepticism cost."
  />
</svelte:head>

<script lang="ts">
  import { base } from "$app/paths";
  import Hero from "$lib/components/sections/Hero.svelte";
  import Problem from "$lib/components/sections/Problem.svelte";
  import Study from "$lib/components/sections/Study.svelte";
  import Flips from "$lib/components/sections/Flips.svelte";
  import Stability from "$lib/components/sections/Stability.svelte";
  import Cost from "$lib/components/sections/Cost.svelte";
  import Reproduce from "$lib/components/sections/Reproduce.svelte";
  import Limits from "$lib/components/sections/Limits.svelte";
</script>

<Hero />
<Problem />
<Study />
<Flips />
<Stability />
<Cost />
<Reproduce />
<Limits />

<div class="max-w-6xl mx-auto px-6 pb-8 text-right">
  <a href={`${base}/#top`} class="font-mono text-[11px] text-slate-600 transition hover:text-teal-300">return to top ↑</a>
</div>
