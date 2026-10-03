<script lang="ts">
  let { tag = "section", id = "", children } = $props();
</script>

<svelte:element this={tag} {id} class="py-16 px-6 max-w-6xl mx-auto relative" style="scroll-margin-top:4rem">
  {@render children()}
</svelte:element>
