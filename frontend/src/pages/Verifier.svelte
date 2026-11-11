<script>
  import { api, visage } from '../lib/api.svelte.js'
  let liste = $state(null)
  let erreur = $state('')
  api.get('/api/suspects').then((r) => (liste = r)).catch((e) => (erreur = e.message))

  const parPersonne = $derived.by(() => {
    const g = {}
    for (const s of liste || []) (g[s.person_id] ||= { nom: s.nom, items: [] }).items.push(s)
    return Object.entries(g)
  })
</script>

<h1 class="titre-page">À vérifier</h1>
<p class="secondaire mt-2 max-w-2xl">
  Sur des scans datés par tampon, ces visages paraissent beaucoup plus jeunes ou plus âgés que l'âge connu de la
  personne. Souvent, le groupe de visages Immich mélange deux personnes (un parent et son enfant), ou la date de
  naissance est fausse. Vérifie dans Immich ou dans carnet.
</p>
{#if erreur}<p class="mt-3 text-alerte" role="alert">{erreur}</p>{/if}

{#if liste && liste.length === 0}
  <p class="mt-10 text-lg">Aucun visage suspect.</p>
{:else if liste}
  {#each parPersonne as [pid, g] (pid)}
    <section class="mt-8">
      <h2 class="font-semibold">{g.nom} <span class="secondaire font-normal">· {g.items.length} visage{g.items.length > 1 ? 's' : ''}</span></h2>
      <ul class="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {#each g.items as s (s.face_id)}
          <li class="surface p-2 text-sm">
            <img src={visage(s.asset_id, s.face_id)} alt="" loading="lazy" class="aspect-square w-full rounded-md object-cover" />
            <p class="mt-1.5">{s.date.slice(0, 7)} : {Math.round(s.age_connu)} ans connus</p>
            <p class="secondaire">paraît {Math.round(s.age_estime)} ans ({s.ecart > 0 ? '+' : ''}{Math.round(s.ecart)})</p>
          </li>
        {/each}
      </ul>
    </section>
  {/each}
{:else if !erreur}
  <p class="secondaire mt-6">Chargement…</p>
{/if}
