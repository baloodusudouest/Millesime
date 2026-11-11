<script>
  import { api } from '../lib/api.svelte.js'
  import NommerGroupe from '../components/NommerGroupe.svelte'
  import Visionneuse from '../components/Visionneuse.svelte'

  let { cible = null } = $props()   // groupe à mettre en avant (#nommer/<id>)
  let d = $state(null)
  let suggestions = $state([])
  let erreur = $state('')
  let fait = $state([])           // { texte, journal }
  let grand = $state(null)

  async function charger() {
    try {
      ;[d, suggestions] = await Promise.all([api.get('/api/nommer'), api.get('/api/nommer/suggestions')])
    } catch (e) { erreur = e.message }
  }
  charger().then(() => {
    if (cible) setTimeout(() => document.getElementById(`groupe-${cible}`)?.scrollIntoView({ block: 'start' }), 50)
  })

  // le groupe demandé passe en tête de liste
  const groupes = $derived(d ? [...d.groupes].sort((a, b) => (b.person_id === cible) - (a.person_id === cible)) : [])

  async function apres(m) {
    if (m) fait = [m, ...fait].slice(0, 3)
    await charger()
  }
  async function annuler(f) {
    erreur = ''
    try {
      await api.post(`/api/journal/${f.journal}/annuler`)
      fait = fait.filter((x) => x !== f)
      await charger()
    } catch (e) { erreur = e.message }
  }
</script>

<h1 class="titre-page">Nommer</h1>
<p class="secondaire mt-2 max-w-2xl">
  Groupes de visages qu'Immich a reconnus sur les scans, sans leur donner de nom. Tape un nouveau nom, ou choisis
  une personne qui existe déjà dans Immich pour y rattacher le groupe. Touche un visage pour voir la photo entière.
</p>

{#each fait as f}
  <p class="mt-3 flex items-center gap-3 text-sm text-or" role="status">
    <span class="flex-1">{f.texte}</span>
    {#if f.journal}<button class="bouton min-h-9" onclick={() => annuler(f)}>Annuler</button>{/if}
  </p>
{/each}
{#if erreur}<p class="mt-3 text-alerte" role="alert">{erreur}</p>{/if}

{#if d}
  {#if groupes.length === 0}
    <p class="mt-10 text-lg">Tous les groupes de visages des scans ont un nom.</p>
  {:else}
    <ul class="mt-6 space-y-4">
      {#each groupes as g (g.person_id)}
        <li><NommerGroupe groupe={g} {suggestions} surligne={g.person_id === cible} onfait={apres}
                          onvoir={(e) => (grand = { asset: e.asset_id, face: e.face_id })} /></li>
      {/each}
    </ul>
  {/if}

  {#if d.sans_naissance.length}
    <section class="mt-10">
      <h2 class="font-semibold">Personnes sans date de naissance</h2>
      <p class="secondaire text-sm">Leur visage ne peut pas servir à dater. Ajoute leur date dans carnet, qui la recopie dans Immich.</p>
      <ul class="mt-3 divide-y divide-filet border-y border-filet">
        {#each d.sans_naissance as p}
          <li class="flex justify-between py-2.5"><span>{p.nom}</span><span class="secondaire">{p.scans} scan{p.scans > 1 ? 's' : ''}</span></li>
        {/each}
      </ul>
    </section>
  {/if}
{:else if !erreur}
  <p class="secondaire mt-6">Chargement…</p>
{/if}

{#if grand}<Visionneuse asset={grand.asset} face={grand.face} fermer={() => (grand = null)} />{/if}
