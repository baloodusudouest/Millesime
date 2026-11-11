<script>
  // Photo entière en grand, avec le visage choisi encadré. Fermeture : Échap, clic sur le fond ou bouton.
  import { api, apercu } from '../lib/api.svelte.js'
  let { asset, face, fermer } = $props()
  let boite = $state(null)
  let dialogue

  $effect(() => {
    boite = null
    api.get(`/api/boite/${asset}/${face}`).then((b) => (boite = b)).catch(() => {})
    dialogue?.showModal()
  })
</script>

<dialog bind:this={dialogue} onclose={fermer} onclick={(e) => e.target === dialogue && dialogue.close()}
        class="m-auto max-h-[94dvh] max-w-[96vw] bg-transparent p-0 backdrop:bg-black/80" aria-label="Photo en grand">
  <figure>
    <!-- le cadre est positionné par rapport à l'image seule, pas à la légende -->
    <div class="relative">
      <img src={apercu(asset)} alt="Photo entière" class="block max-h-[84dvh] max-w-[96vw] rounded-lg" />
      {#if boite}
        <div class="pointer-events-none absolute rounded-sm border-2 border-or"
             style="left:{boite.x * 100}%; top:{boite.y * 100}%; width:{boite.l * 100}%; height:{boite.h * 100}%"></div>
      {/if}
    </div>
    <figcaption class="mt-2 flex items-center justify-between gap-3 text-sm text-etiquette">
      <span>{boite?.nom || 'Visage sans nom'}</span>
      <button class="bouton" onclick={() => dialogue.close()}>Fermer</button>
    </figcaption>
  </figure>
</dialog>
