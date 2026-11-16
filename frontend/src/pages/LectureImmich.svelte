<script>
  // 2.12.0 : réglages d'usage qui venaient de la stack : libellé des numérisations et relecture d'Immich.
  // Gardés dans Millésime, sauvegardés chaque nuit par l'Anneau (voir « Restaurer les réglages »).
  import { api } from '../lib/api.svelte.js'
  let { change = () => {} } = $props()     // prévient Réglages pour rafraîchir les autres tuiles

  let r = $state(null)            // { reglages, chambre_noire }
  let prefixe = $state('')
  let minutes = $state(60)
  let erreur = $state('')
  let dit = $state('')
  let occupe = $state(false)

  function prendre(x) { r = x; prefixe = x.reglages.tag_prefixe; minutes = x.reglages.synchro_minutes }
  api.get('/api/reglages').then(prendre).catch((e) => (erreur = e.message))

  const modifie = $derived(r && (prefixe.trim() !== r.reglages.tag_prefixe || Number(minutes) !== r.reglages.synchro_minutes))
  async function enregistrer() {
    occupe = true; erreur = ''; dit = ''
    try {
      // un nombre mal tapé part tel quel : le serveur répond par un message clair
      const n = Number(minutes)
      prendre(await api.put('/api/reglages', { tag_prefixe: prefixe, synchro_minutes: Number.isInteger(n) ? n : String(minutes) }))
      dit = 'Réglages enregistrés.'
      change()
    } catch (e) { erreur = e.message }
    occupe = false
  }
</script>

<section class="surface mt-4 p-4" aria-labelledby="titre-lecture">
  <h2 id="titre-lecture" class="text-lg font-semibold">Lecture d'Immich</h2>
  <p class="secondaire mt-1 text-sm">Le libellé des numérisations est le début des tags : « <em>libellé</em>/Non datée » pour les scans
    sans date, « <em>libellé</em>/AAAA-MM » pour ceux qui portent un tampon.
    {r?.chambre_noire ? 'Chambre noire est reliée : c\'est son libellé qui compte, celui-ci ne sert que si elle ne répond plus jamais.' : ''}</p>
  {#if erreur}<p class="mt-3 text-alerte" role="alert">{erreur}</p>{/if}
  {#if dit}<p class="mt-3 text-sm" role="status">{dit}</p>{/if}
  {#if r}
    <form class="mt-3 grid gap-3 sm:grid-cols-2" novalidate onsubmit={(e) => { e.preventDefault(); enregistrer() }}>
      <label class="grid gap-1 text-sm"><span>Libellé des numérisations{r.chambre_noire ? ' (facultatif)' : ''}</span>
        <input class="champ" bind:value={prefixe} maxlength="120" autocomplete="off" /></label>
      <label class="grid gap-1 text-sm"><span>Relire Immich toutes les … minutes (5 à 1440)</span>
        <input class="champ" type="number" inputmode="numeric" min="5" max="1440" step="1" bind:value={minutes} /></label>
      <p class="sm:col-span-2"><button class="bouton" type="submit" disabled={occupe || !modifie}>Enregistrer</button></p>
    </form>
  {:else if !erreur}
    <p class="secondaire mt-3 text-sm">Chargement…</p>
  {/if}
</section>
