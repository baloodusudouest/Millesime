<script>
  import { api, pluriel, visage } from '../lib/api.svelte.js'
  let d = $state(null)
  let noms = $state({})
  let erreur = $state('')
  let fait = $state([])

  async function charger() {
    try { d = await api.get('/api/nommer') } catch (e) { erreur = e.message }
  }
  charger()

  async function nommer(g, e) {
    e.preventDefault()
    erreur = ''
    try {
      const r = await api.post(`/api/nommer/${g.person_id}`, { nom: noms[g.person_id] })
      fait = [`${r.nom} : ${pluriel(g.visages, 'visage')} nommés dans Immich`, ...fait].slice(0, 3)
      await charger()
    } catch (err) { erreur = err.message }
  }
  async function ignorer(g) {
    await api.post(`/api/nommer/${g.person_id}/ignorer`)
    await charger()
  }
</script>

<h1 class="millesime text-4xl font-semibold">Nommer</h1>
<p class="secondaire mt-2 max-w-2xl">
  Groupes de visages qu'Immich a reconnus sur les scans, sans leur donner de nom. Un nom écrit ici est
  enregistré dans Immich. Si un groupe mélange plusieurs personnes ou en double une autre, corrige-le
  dans Immich : Millésime ne fusionne jamais.
</p>

{#each fait as f}<p class="mt-3 text-sm text-or" role="status">{f}</p>{/each}
{#if erreur}<p class="mt-3 text-alerte" role="alert">{erreur}</p>{/if}

{#if d}
  {#if d.groupes.length === 0}
    <p class="mt-10 text-lg">Tous les groupes de visages des scans ont un nom.</p>
  {:else}
    <ul class="mt-6 space-y-4">
      {#each d.groupes as g (g.person_id)}
        <li class="surface p-4">
          <div class="flex gap-1.5 overflow-x-auto">
            {#each g.exemples as e}
              <img src={visage(e.asset_id, e.face_id)} alt="" width="72" height="72" loading="lazy"
                   class="aspect-square w-[72px] shrink-0 rounded-md object-cover" />
            {/each}
          </div>
          <p class="secondaire mt-2 text-sm">
            {pluriel(g.visages, 'visage')}, dont {g.sur_non_datees} sur des photos à dater ·
            <a class="lien" href={g.lien_immich} target="_blank" rel="noopener">voir dans Immich</a>
          </p>
          <form class="mt-3 flex flex-wrap gap-2" onsubmit={(e) => nommer(g, e)}>
            <label class="sr-only" for="nom-{g.person_id}">Nom</label>
            <input id="nom-{g.person_id}" class="min-w-0 flex-1" placeholder="Prénom NOM" autocomplete="off"
                   bind:value={noms[g.person_id]} />
            <button class="bouton bouton-principal" disabled={!noms[g.person_id] || noms[g.person_id].trim().length < 2}>Nommer</button>
            <button type="button" class="bouton" onclick={() => ignorer(g)}>Ignorer</button>
          </form>
        </li>
      {/each}
    </ul>
  {/if}

  {#if d.sans_naissance.length}
    <section class="mt-10">
      <h2 class="font-semibold">Personnes sans date de naissance</h2>
      <p class="secondaire text-sm">Leur visage ne peut pas servir à dater. Ajoute leur date dans carnet, qui la recopie dans Immich.</p>
      <ul class="mt-3 divide-y divide-filet border-y border-filet">
        {#each d.sans_naissance as p}
          <li class="flex justify-between py-2.5"><span>{p.nom}</span><span class="secondaire">{pluriel(p.scans, 'scan')}</span></li>
        {/each}
      </ul>
    </section>
  {/if}
{:else if !erreur}
  <p class="secondaire mt-6">Chargement…</p>
{/if}
