<script lang="ts">
  import { base } from "$app/paths";
  import { meta } from "$lib/data/meta";
  import "../app.css";
  let { children } = $props();
</script>

<header id="top" class="border-b border-slate-800/80 bg-slate-950/90 backdrop-blur sticky top-0 z-50">
  <div class="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
    <a href="{base}/" class="font-mono text-sm text-slate-100 tracking-tight">
      cull<span class="text-teal-400">-</span>audit
    </a>
    <nav class="flex items-center gap-5 text-sm text-slate-400">
      <a class="hover:text-slate-100" href="https://github.com/rmax-ai/cull-audit">GitHub ↗</a>
      <a class="hover:text-slate-100" href="https://github.com/rmax-ai/cull-audit/releases/tag/v0.1.0">v0.1.0 Release ↗</a>
    </nav>
  </div>
</header>

<main>
  {@render children()}
</main>

<footer class="border-t border-slate-800/80 mt-24">
  <div class="max-w-6xl mx-auto flex flex-col gap-5 px-6 py-10 text-sm text-slate-500 sm:flex-row sm:items-end sm:justify-between">
    <div class="max-w-3xl space-y-3">
      <p>cull-audit — a local-first verification harness for AI photo-culling pipelines. MIT licensed code.</p>
      <p>{meta.footer}</p>
    </div>
    <div class="flex gap-5 font-mono text-xs">
      <a class="hover:text-teal-300" href="{base}/#study">protocol</a>
      <a class="hover:text-teal-300" href="{base}/#limits">limits</a>
      <a class="hover:text-teal-300" href="https://github.com/rmax-ai/cull-audit">source ↗</a>
    </div>
  </div>
</footer>
