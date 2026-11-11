<script>
  // Un groupe de visages sans nom : vignettes (touchées = photo en grand), champ de nom avec les
  // suggestions d'Immich, rattachement à une personne existante après aperçu, Ignorer.
  // Utilisé par l'écran Nommer et, en version compacte, sous la photo de l'écran Dater.
  import { api, pluriel, visage } from '../lib/api.svelte.js'

  let { groupe, suggestions, compact = false, onfait, onvoir, surligne = false } = $props()
  let nom = $state('')
  let ouvert = $state(false)
  let apercu = $state(null)
  let erreur = $state('')
  let occupe = $state(false)

  const cle = (s) => (s || '').normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().replace(/\s+/g, ' ').trim()
  const proposees = $derived.by(() => {
    const t = cle(nom)
    return (t ? suggestions.filter((s) => cle(s.nom).includes(t)) : suggestions).slice(0, 6)
  })
  const existant = $derived(cle(nom) ? suggestions.find((s) => cle(s.nom) === cle(nom)) : null)

  async function preparer(s) {
    ouvert = false
    nom = s.nom
    erreur = ''
    try { apercu = await api.get(`/api/nommer/${groupe.person_id}/apercu/${s.person_id}`) } catch (e) { erreur = e.message }
  }
  async function rattacher() {
    occupe = true
    erreur = ''
    try {
      const r = await api.post(`/api/nommer/${groupe.person_id}/fusionner`, { cible: apercu.cible.person_id })
      onfait?.({ texte: `${pluriel(r.visages, 'visage')} rattaché${r.visages > 1 ? 's' : ''} à ${r.cible} dans Immich.`, journal: r.journal })
    } catch (e) { erreur = e.message }
    occupe = false
  }
  async function nommer(e) {
    e.preventDefault()
    if (existant) return preparer(existant)
    occupe = true
    erreur = ''
    try {
      const r = await api.post(`/api/nommer/${groupe.person_id}`, { nom })
      const j = (await api.get('/api/journal'))[0]
      onfait?.({ texte: `${r.nom} : ${pluriel(groupe.visages || 1, 'visage')} nommé${(groupe.visages || 1) > 1 ? 's' : ''} dans Immich.`, journal: j?.id })
    } catch (err) { erreur = err.message }
    occupe = false
  }
  async function ignorer() {
    await api.post(`/api/nommer/${groupe.person_id}/ignorer`)
    onfait?.(null)
  }
</script>

<div id="groupe-{groupe.person_id}" class="surface scroll-mt-20 {compact ? 'p-3' : 'p-4'} {surligne ? 'ring-2 ring-or' : ''}">
  <div class="flex gap-3">
    <div class="flex shrink-0 gap-1.5 overflow-x-auto {compact ? '' : 'max-w-full'}">
      {#each (compact ? groupe.exemples.slice(0, 1) : groupe.exemples) as e}
        <button class="shrink-0 rounded-md" onclick={() => onvoir?.(e)} aria-label="Voir la photo entière">
          <img src={visage(e.asset_id, e.face_id)} alt="" width={compact ? 64 : 72} height={compact ? 64 : 72} loading="lazy"
               class="aspect-square rounded-md object-cover {compact ? 'w-16' : 'w-[72px]'}" />
        </button>
      {/each}
    </div>
    {#if compact}
      <p class="secondaire self-center text-sm">
        {groupe.visages ? `Groupe Immich de ${pluriel(groupe.visages, 'visage')}` : 'Groupe Immich sans nom'}{groupe.masque ? ', personne masquée dans Immich' : ''}
        {#if groupe.lien_immich}· <a class="lien" href={groupe.lien_immich} target="_blank" rel="noopener">voir dans Immich</a>{/if}
      </p>
    {/if}
  </div>
  {#if !compact}
    <p class="secondaire mt-2 text-sm">
      {pluriel(groupe.visages, 'visage')}, dont {groupe.sur_non_datees} sur des photos à dater ·
      <a class="lien" href={groupe.lien_immich} target="_blank" rel="noopener">voir dans Immich</a>
    </p>
  {/if}

  {#if apercu}
    <div class="mt-3 rounded-md border border-or/60 p-3">
      <p class="font-semibold">Rattacher ce groupe à {apercu.cible.nom} ?</p>
      <p class="secondaire text-sm">Vérifie que c'est bien la même personne. Tu pourras annuler depuis le journal.</p>
      <p class="secondaire mt-3 text-xs">Visages de {apercu.cible.nom} déjà connus</p>
      <div class="mt-1 flex gap-1.5 overflow-x-auto">
        {#each apercu.cible.exemples as e}
          <button class="shrink-0 rounded-md" onclick={() => onvoir?.(e)} aria-label="Voir la photo entière">
            <img src={visage(e.asset_id, e.face_id)} alt="" width="64" height="64" loading="lazy"
                 class="aspect-square w-16 rounded-md object-cover ring-1 ring-or/60" />
          </button>
        {/each}
      </div>
      <div class="mt-3 flex flex-wrap gap-2">
        <button class="bouton bouton-confirmer" onclick={rattacher} disabled={occupe}>Rattacher à {apercu.cible.nom}</button>
        <button class="bouton" onclick={() => (apercu = null)}>Revenir</button>
      </div>
    </div>
  {:else}
    <form class="relative mt-3 flex flex-wrap gap-2" onsubmit={nommer}>
      <label class="sr-only" for="nom-{groupe.person_id}">Nom</label>
      <input id="nom-{groupe.person_id}" class="min-w-0 flex-1" placeholder="Prénom NOM" autocomplete="off"
             bind:value={nom} onfocus={() => (ouvert = true)} oninput={() => (ouvert = true)}
             onblur={() => setTimeout(() => (ouvert = false), 150)}
             onkeydown={(e) => e.key === 'Escape' && (ouvert = false)}
             role="combobox" aria-expanded={ouvert} aria-controls="sug-{groupe.person_id}" />
      <button class="bouton bouton-principal" disabled={occupe || nom.trim().length < 2}>{existant ? 'Rattacher…' : 'Nommer'}</button>
      <button type="button" class="bouton" onclick={ignorer}>Ignorer</button>
      {#if ouvert && proposees.length}
        <ul id="sug-{groupe.person_id}" role="listbox"
            class="surface absolute left-0 right-0 top-full z-10 mt-1 max-h-72 overflow-y-auto p-1 shadow-xl sm:right-48">
          {#each proposees as s (s.person_id)}
            <li role="option" aria-selected="false">
              <button type="button" class="flex w-full items-center justify-between gap-3 rounded px-3 py-2.5 text-left hover:bg-verre"
                      onmousedown={(e) => { e.preventDefault(); preparer(s) }}>
                <span>{s.nom}</span>
                <span class="secondaire text-xs">{s.sur_scans ? pluriel(s.sur_scans, 'scan') : 'hors scans'}{s.naissance ? ` · ${s.naissance.slice(0, 4)}` : ''}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </form>
  {/if}
  {#if erreur}<p class="mt-2 text-sm text-alerte" role="alert">{erreur}</p>{/if}
</div>
