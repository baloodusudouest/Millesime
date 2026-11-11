<script>
  import { api, apercu, visage } from '../lib/api.svelte.js'
  import Frise from '../components/Frise.svelte'

  let { statut } = $props()
  let liste = $state([])
  let position = $state(0)
  let s = $state(null)
  let annee = $state(null)
  let marge = $state(2)
  let confirmer = $state(false)
  let occupe = $state(false)
  let erreur = $state('')
  let message = $state(null)   // { texte, journal }

  async function chargerListe() {
    erreur = ''
    liste = await api.get(`/api/scans?statut=${statut}`)
    position = 0
    await chargerScan()
  }
  async function chargerScan() {
    s = null
    confirmer = false
    if (!liste.length || position >= liste.length) return
    s = await api.get(`/api/scans/${liste[position].asset_id}`)
    const anneesVisages = (s.details.visages || []).map((v) => v.annee)
    annee = s.annee_proposee ?? (anneesVisages.length ? Math.floor(anneesVisages[0]) : s.details?.voisins?.mediane ?? 1990)
    marge = s.marge ?? 3
  }
  $effect(() => { statut; chargerListe().catch((e) => (erreur = e.message)) })

  const parFace = $derived(Object.fromEntries((s?.details?.visages || []).map((v) => [v.face_id, v])))
  const personnes = $derived((s?.details?.visages || []).filter((v) => v.person_id))
  const modifie = $derived(s && (annee !== s.annee_proposee || marge !== s.marge))
  const haute = $derived(s?.annee_envoi || new Date().getFullYear())

  function changer(d) { annee = Math.min(haute, annee + d); confirmer = false }
  function changerMarge(d) { marge = Math.max(0, Math.min(10, marge + d)); confirmer = false }

  async function valider() {
    if (marge > 2 && !confirmer) { confirmer = true; return }
    occupe = true
    erreur = ''
    try {
      const r = await api.post(`/api/scans/${s.asset_id}/valider`, { annee, marge })
      message = { texte: `Datée ${annee} ±${marge}, rangée dans « ${r.album} ».`, journal: r.journal }
      liste.splice(position, 1)
      await chargerScan()
    } catch (e) { erreur = e.message }
    occupe = false
  }
  async function plusieurs() {
    occupe = true
    try {
      const r = await api.post(`/api/scans/${s.asset_id}/plusieurs`)
      message = { texte: 'Mise de côté : plusieurs années sur ce scan.', journal: r.journal }
      liste.splice(position, 1)
      await chargerScan()
    } catch (e) { erreur = e.message }
    occupe = false
  }
  function passer() { position = (position + 1) % Math.max(1, liste.length); chargerScan() }
  async function annuler() {
    try {
      await api.post(`/api/journal/${message.journal}/annuler`)
      message = null
      await chargerListe()
    } catch (e) { erreur = e.message }
  }
</script>

{#if message}
  <div class="surface mb-4 flex items-center gap-3 p-3" role="status">
    <p class="flex-1 text-sm">{message.texte}</p>
    <button class="bouton" onclick={annuler}>Annuler</button>
    <button class="secondaire px-2" onclick={() => (message = null)} aria-label="Fermer">✕</button>
  </div>
{/if}
{#if erreur}<p class="mb-4 text-alerte" role="alert">{erreur}</p>{/if}

{#if !s && liste.length === 0}
  <div class="py-16 text-center">
    <p class="millesime text-4xl font-semibold">{statut === 'a_dater' ? 'Tout est daté' : 'Rien à trancher'}</p>
    <p class="secondaire mx-auto mt-3 max-w-md">
      {#if statut === 'a_dater'}Les photos restantes attendent le calcul sur le PC, ou sont à trancher.
      {:else}Les cas douteux apparaîtront ici : marge trop large, visages en désaccord, aucun visage exploitable.{/if}
    </p>
    <p class="mt-6 flex justify-center gap-3">
      <a class="bouton" href="#calcul">Calcul sur le PC</a>
      <a class="bouton" href={statut === 'a_dater' ? '#trancher' : '#nommer'}>{statut === 'a_dater' ? 'À trancher' : 'Nommer des visages'}</a>
    </p>
  </div>
{:else if s}
  <p class="secondaire mb-3 text-sm">{statut === 'a_dater' ? 'À dater' : 'À trancher'} : photo {position + 1} sur {liste.length}</p>

  <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
    <!-- Photo et visages -->
    <figure class="relative self-start overflow-hidden rounded-lg bg-verre-2">
      <img src={apercu(s.asset_id)} alt="Scan à dater" class="block w-full" />
      {#each s.visages as v}
        {@const iv = parFace[v.face_id]}
        <div class="absolute rounded-sm border-2 {iv ? 'border-or' : 'border-etiquette/50 border-dashed'}"
             style="left:{(100 * v.x1) / v.img_w}%; top:{(100 * v.y1) / v.img_h}%; width:{(100 * (v.x2 - v.x1)) / v.img_w}%; height:{(100 * (v.y2 - v.y1)) / v.img_h}%">
          <span class="absolute left-0 top-full mt-0.5 whitespace-nowrap rounded bg-verre/85 px-1 text-[11px]">
            {v.person_nom || 'sans nom'}{iv ? ` · ${Math.round(iv.age)} ans` : ''}
          </span>
        </div>
      {/each}
    </figure>

    <!-- Millésime proposé et actions -->
    <section aria-label="Année">
      {#if s.raison}<p class="mb-3 rounded-md border border-alerte/50 px-3 py-2 text-sm text-alerte">{s.raison}</p>{/if}

      <div class="flex items-center gap-2">
        <button class="bouton w-11 px-0 text-xl" onclick={() => changer(-1)} aria-label="Année précédente">−</button>
        <p class="millesime flex-1 text-center text-7xl font-semibold leading-none" aria-live="polite">{annee}</p>
        <button class="bouton w-11 px-0 text-xl" onclick={() => changer(1)} aria-label="Année suivante" disabled={annee >= haute}>+</button>
      </div>
      <div class="mt-2 flex items-center justify-center gap-2 text-sm">
        <button class="bouton min-h-9 w-9 px-0" onclick={() => changerMarge(-1)} aria-label="Réduire la marge">−</button>
        <span class="w-28 text-center">marge ±{marge} an{marge > 1 ? 's' : ''}</span>
        <button class="bouton min-h-9 w-9 px-0" onclick={() => changerMarge(1)} aria-label="Élargir la marge">+</button>
      </div>
      {#if s.annee_proposee !== null}
        <p class="secondaire mt-2 text-center text-sm">
          {modifie ? `Proposé par l'indice : ${s.annee_proposee} ±${s.marge}` : 'Proposé par l’indice MiVOLO calibré'}
        </p>
      {/if}

      <div class="mt-5 grid gap-2">
        <button class="bouton {confirmer ? 'bouton-confirmer' : 'bouton-principal'}" onclick={valider} disabled={occupe}>
          {confirmer ? `Confirmer ${annee} ±${marge}` : `Valider ${annee}`}
        </button>
        {#if confirmer}<p class="secondaire text-center text-xs">Marge large : confirme que tu as comparé avec la frise.</p>{/if}
        <div class="grid grid-cols-2 gap-2">
          <button class="bouton" onclick={passer} disabled={occupe || liste.length < 2}>Passer</button>
          <button class="bouton" onclick={plusieurs} disabled={occupe}>Plusieurs années</button>
        </div>
      </div>

      <dl class="mt-6 space-y-2 text-sm">
        {#if s.details.bornes}
          <div class="flex justify-between gap-3"><dt class="secondaire">Pas avant</dt>
            <dd>{s.details.bornes.basse_souple} <span class="secondaire">(naissance la plus récente)</span></dd></div>
        {/if}
        <div class="flex justify-between gap-3"><dt class="secondaire">Pas après</dt><dd>{haute} <span class="secondaire">(envoi du scan)</span></dd></div>
        {#if s.details.voisins}
          <div class="flex justify-between gap-3"><dt class="secondaire">Même envoi</dt>
            <dd>{s.details.voisins.min}–{s.details.voisins.max} <span class="secondaire">({s.details.voisins.n} déjà datées)</span></dd></div>
        {/if}
        {#if s.details.sans_nom}
          <div class="flex justify-between gap-3"><dt class="secondaire">Visages sans nom</dt>
            <dd><a class="lien" href="#nommer">{s.details.sans_nom} à nommer</a></dd></div>
        {/if}
        {#if s.details.sans_naissance}
          <div class="flex justify-between gap-3"><dt class="secondaire">Sans date de naissance</dt>
            <dd>{s.details.sans_naissance} <span class="secondaire">(à compléter dans carnet)</span></dd></div>
        {/if}
      </dl>
    </section>
  </div>

  {#if personnes.length}
    <section class="mt-8" aria-labelledby="titre-frises">
      <h2 id="titre-frises" class="font-semibold">Comparer avec les frises</h2>
      <p class="secondaire text-sm">Les photos datées de chaque personne, rangées par âge. La photo à dater est placée à l'âge qu'elle aurait en {annee}.</p>
      {#each personnes as p (p.face_id)}
        <Frise personId={p.person_id} nom={p.nom} naissance={p.naissance} {annee} scanAsset={s.asset_id} scanFace={p.face_id} />
      {/each}
    </section>
  {/if}
{:else}
  <p class="secondaire">Chargement…</p>
{/if}
