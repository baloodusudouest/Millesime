<script>
  import { api, pluriel, visage } from '../lib/api.svelte.js'
  import Visionneuse from '../components/Visionneuse.svelte'

  let d = $state(null)
  let suggestions = $state([])
  let noms = $state({})          // texte tapé par groupe
  let ouvert = $state(null)      // groupe dont la liste de suggestions est ouverte
  let fusion = $state({})        // person_id du groupe -> aperçu de fusion
  let erreur = $state('')
  let fait = $state([])          // { texte, journal }
  let grand = $state(null)       // { asset, face } affiché en grand

  const cle = (s) => (s || '').normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().replace(/\s+/g, ' ').trim()

  async function charger() {
    try {
      ;[d, suggestions] = await Promise.all([api.get('/api/nommer'), api.get('/api/nommer/suggestions')])
    } catch (e) { erreur = e.message }
  }
  charger()

  function proposer(g) {
    const t = cle(noms[g.person_id])
    if (!t) return suggestions.slice(0, 6)
    return suggestions.filter((s) => cle(s.nom).includes(t)).slice(0, 6)
  }
  function existant(g) {
    const t = cle(noms[g.person_id])
    return t ? suggestions.find((s) => cle(s.nom) === t) : null
  }

  async function preparerFusion(g, s) {
    ouvert = null
    noms[g.person_id] = s.nom
    erreur = ''
    try { fusion[g.person_id] = await api.get(`/api/nommer/${g.person_id}/apercu/${s.person_id}`) }
    catch (e) { erreur = e.message }
  }
  async function fusionner(g) {
    erreur = ''
    try {
      const r = await api.post(`/api/nommer/${g.person_id}/fusionner`, { cible: fusion[g.person_id].cible.person_id })
      fait = [{ texte: `${pluriel(r.visages, 'visage')} rattaché${r.visages > 1 ? 's' : ''} à ${r.cible} dans Immich.`, journal: r.journal }, ...fait].slice(0, 3)
      delete fusion[g.person_id]
      await charger()
    } catch (e) { erreur = e.message }
  }
  async function nommer(g, e) {
    e.preventDefault()
    const s = existant(g)
    if (s) return preparerFusion(g, s)
    erreur = ''
    try {
      const r = await api.post(`/api/nommer/${g.person_id}`, { nom: noms[g.person_id] })
      const j = (await api.get('/api/journal'))[0]
      fait = [{ texte: `${r.nom} : ${pluriel(g.visages, 'visage')} nommé${g.visages > 1 ? 's' : ''} dans Immich.`, journal: j?.id }, ...fait].slice(0, 3)
      await charger()
    } catch (err) { erreur = err.message }
  }
  async function ignorer(g) {
    await api.post(`/api/nommer/${g.person_id}/ignorer`)
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

<h1 class="millesime text-4xl font-semibold">Nommer</h1>
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
  {#if d.groupes.length === 0}
    <p class="mt-10 text-lg">Tous les groupes de visages des scans ont un nom.</p>
  {:else}
    <ul class="mt-6 space-y-4">
      {#each d.groupes as g (g.person_id)}
        {@const f = fusion[g.person_id]}
        <li class="surface p-4">
          <div class="flex gap-1.5 overflow-x-auto">
            {#each g.exemples as e}
              <button class="shrink-0 rounded-md" onclick={() => (grand = { asset: e.asset_id, face: e.face_id })}
                      aria-label="Voir la photo entière">
                <img src={visage(e.asset_id, e.face_id)} alt="" width="72" height="72" loading="lazy"
                     class="aspect-square w-[72px] rounded-md object-cover" />
              </button>
            {/each}
          </div>
          <p class="secondaire mt-2 text-sm">
            {pluriel(g.visages, 'visage')}, dont {g.sur_non_datees} sur des photos à dater ·
            <a class="lien" href={g.lien_immich} target="_blank" rel="noopener">voir dans Immich</a>
          </p>

          {#if f}
            <!-- Aperçu avant fusion : les deux groupes côte à côte -->
            <div class="mt-4 rounded-md border border-or/60 p-3">
              <p class="font-semibold">Rattacher ce groupe à {f.cible.nom} ?</p>
              <p class="secondaire text-sm">Vérifie que c'est bien la même personne. Tu pourras annuler depuis le journal.</p>
              <p class="secondaire mt-3 text-xs">Visages de {f.cible.nom} déjà connus</p>
              <div class="mt-1 flex gap-1.5 overflow-x-auto">
                {#each f.cible.exemples as e}
                  <button class="shrink-0 rounded-md" onclick={() => (grand = { asset: e.asset_id, face: e.face_id })} aria-label="Voir la photo entière">
                    <img src={visage(e.asset_id, e.face_id)} alt="" width="72" height="72" loading="lazy"
                         class="aspect-square w-[72px] rounded-md object-cover ring-1 ring-or/60" />
                  </button>
                {/each}
              </div>
              <div class="mt-3 flex flex-wrap gap-2">
                <button class="bouton bouton-confirmer" onclick={() => fusionner(g)}>Rattacher à {f.cible.nom}</button>
                <button class="bouton" onclick={() => delete fusion[g.person_id]}>Revenir</button>
              </div>
            </div>
          {:else}
            <form class="relative mt-3 flex flex-wrap gap-2" onsubmit={(e) => nommer(g, e)}>
              <label class="sr-only" for="nom-{g.person_id}">Nom</label>
              <input id="nom-{g.person_id}" class="min-w-0 flex-1" placeholder="Prénom NOM"
                     autocomplete="off" bind:value={noms[g.person_id]}
                     onfocus={() => (ouvert = g.person_id)} oninput={() => (ouvert = g.person_id)}
                     onkeydown={(e) => e.key === 'Escape' && (ouvert = null)}
                     role="combobox" aria-expanded={ouvert === g.person_id} aria-controls="sug-{g.person_id}" />
              <button class="bouton bouton-principal" disabled={!noms[g.person_id] || noms[g.person_id].trim().length < 2}>
                {existant(g) ? 'Rattacher…' : 'Nommer'}
              </button>
              <button type="button" class="bouton" onclick={() => ignorer(g)}>Ignorer</button>
              {#if ouvert === g.person_id && proposer(g).length}
                <ul id="sug-{g.person_id}" role="listbox"
                    class="surface absolute left-0 right-0 top-full z-10 mt-1 max-h-72 overflow-y-auto p-1 shadow-xl sm:right-48">
                  {#each proposer(g) as s (s.person_id)}
                    <li role="option" aria-selected="false">
                      <button type="button" class="flex w-full items-center justify-between gap-3 rounded px-3 py-2.5 text-left hover:bg-verre"
                              onmousedown={(e) => { e.preventDefault(); preparerFusion(g, s) }}>
                        <span>{s.nom}</span>
                        <span class="secondaire text-xs">{s.sur_scans ? pluriel(s.sur_scans, 'scan') : 'hors scans'}{s.naissance ? ` · ${s.naissance.slice(0, 4)}` : ''}</span>
                      </button>
                    </li>
                  {/each}
                </ul>
              {/if}
            </form>
          {/if}
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

{#if grand}<Visionneuse asset={grand.asset} face={grand.face} fermer={() => (grand = null)} />{/if}
