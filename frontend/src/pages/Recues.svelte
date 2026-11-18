<script>
  // 2.13.0 : « Reçues des invités ». Les invités de Sillage disent « Pas la bonne année ? » sous une photo ;
  // Millésime lit ces avis chez Sillage (toutes les 15 min, ou « Relire ») et les montre une ligne par photo.
  // Rien n'est écrit dans Immich sans un geste de Julien : Accepter (l'année d'un avis), Corriger, Écarter.
  // Le mot libre des invités est affiché comme du texte (jamais en HTML brut) : Svelte l'échappe.
  import { api, dateCourte, dateJour, pluriel, session } from '../lib/api.svelte.js'

  let r = $state(null)
  let erreur = $state('')
  let occupe = $state(false)
  let message = $state(null)       // { texte, journal }
  let correction = $state(null)    // asset_id dont le champ « Corriger » est ouvert
  let anneeTapee = $state('')
  let confirmeTout = $state(false)

  const lignes = $derived(r?.lignes || [])
  const aConfirmer = $derived(r?.a_confirmer || [])
  const concordantes = $derived(lignes.filter((l) => l.tout_accepter))
  const etat = $derived(r?.sillage)

  async function charger() {
    erreur = ''
    try { r = await api.get('/api/recues') } catch (e) { erreur = e.message }
  }
  charger()

  async function relire() {
    occupe = true
    erreur = ''
    try { r = await api.post('/api/recues/relire') } catch (e) { erreur = e.message }
    occupe = false
  }

  function suite(res, texte) {
    message = { texte: texte + (res.confirme === false ? ' ' + res.message : ''), journal: res.journal }
  }

  async function geste(l, quoi, annee) {
    occupe = true
    erreur = ''
    try {
      const res = await api.post(`/api/recues/${encodeURIComponent(l.asset_id)}/${quoi}`, annee ? { annee } : {})
      suite(res, quoi === 'ecarter' ? 'Avis écarté : la date de la photo ne change pas.'
                                    : `Datée ${annee} (${res.tag.split('/').pop()}).`)
      correction = null
      await charger()
    } catch (e) { erreur = e.message }
    occupe = false
  }

  function corriger(l) {
    const a = Number(anneeTapee)
    if (!Number.isInteger(a) || a < 1880 || a > new Date().getFullYear()) { erreur = 'Année illisible : tape quatre chiffres, par exemple 1987.'; return }
    geste(l, 'corriger', a)
  }

  async function toutAccepter() {
    if (!confirmeTout) { confirmeTout = true; return }
    confirmeTout = false
    occupe = true
    erreur = ''
    try {
      const res = await api.post('/api/recues/tout-accepter')
      message = { texte: `${pluriel(res.faites, 'photo datée', 'photos datées')} d'après l'avis des invités.`
        + (res.a_confirmer ? ` ${res.a_confirmer} à confirmer chez Sillage.` : '') }
      if (res.erreurs.length) erreur = res.erreurs[0]
      await charger()
    } catch (e) { erreur = e.message }
    occupe = false
  }

  async function annuler() {
    occupe = true
    try {
      await api.post(`/api/journal/${message.journal}/annuler`)
      message = { texte: 'Date remise comme avant dans Immich. L\'avis reste fermé chez Sillage.' }
    } catch (e) { erreur = e.message }
    occupe = false
  }

  const marqueEnviron = (avis, annee) => avis.filter((a) => a.annee === annee).every((a) => a.environ)
</script>

<h1 class="titre-page">Reçues des invités</h1>
<p class="secondaire mt-1 text-sm">Les années que les invités proposent sous leurs photos, dans Sillage. Rien n'est écrit dans Immich sans ton clic ; une date acceptée s'annule depuis le journal.</p>

<div class="mt-3 flex flex-wrap items-center gap-3 text-sm" role="status">
  {#if etat && !etat.relie}
    <span class="alerte">Sillage n'est pas relié (MAISON_JETON vide dans la stack) : rien n'est lu.</span>
  {:else if etat}
    <span class="secondaire">{etat.lu ? `Lu chez Sillage le ${dateCourte(etat.lu.le)}` : 'Jamais lu chez Sillage'}</span>
    {#if etat.erreur}<span class="alerte">{etat.erreur.detail} : dernière lecture gardée.</span>{/if}
  {/if}
  <button class="bouton min-h-9" onclick={relire} disabled={occupe}>Relire</button>
</div>

{#if erreur}<p class="mt-3 text-alerte" role="alert">{erreur}</p>{/if}
{#if message}
  <div class="surface mt-3 flex items-center gap-3 p-3" role="status">
    <p class="flex-1 text-sm">{message.texte}</p>
    {#if message.journal}<button class="bouton min-h-9" onclick={annuler} disabled={occupe || session.lecture_seule}>Annuler</button>{/if}
    <button class="secondaire px-2" onclick={() => (message = null)} aria-label="Fermer">✕</button>
  </div>
{/if}

{#if !r && !erreur}
  <p class="secondaire mt-6">Chargement…</p>
{:else if r}
  {#if concordantes.length}
    <div class="mt-4">
      <button class="bouton bouton-confirmer" onclick={toutAccepter} disabled={occupe || session.lecture_seule}>
        {confirmeTout ? `Confirmer : accepter ${pluriel(concordantes.length, 'photo')}` : `Tout accepter (${concordantes.length})`}</button>
      <p class="secondaire mt-1 text-xs">Seulement les photos à un seul avis, qui tombe à deux ans près de l'estimation de Millésime.</p>
    </div>
  {/if}

  {#if !lignes.length}
    <p class="secondaire py-10 text-center">Aucune date signalée par les invités en attente.</p>
  {:else}
    <ul class="mt-4 space-y-3" aria-label="Photos signalées">
      {#each lignes as l (l.asset_id)}
        <li class="surface ligne p-3">
          <img class="vignette" src={`/api/vignette/${encodeURIComponent(l.asset_id)}`} alt="" loading="lazy" />
          <div class="min-w-0">
            <p class="text-sm">
              <span class="secondaire">Dans Immich :</span> {l.date_lisible ? dateJour(l.date_immich) : 'date illisible (Immich ne répond pas)'}
              {#if l.estimation}<span class="secondaire"> · Millésime :</span> <span class="millesime">{l.estimation.annee}</span> ±{l.estimation.marge}{/if}
            </p>
            {#if l.deja_changee}<p class="mt-1 text-xs text-or">Date déjà changée depuis l'avis.</p>{/if}
            <ul class="mt-2 space-y-1.5">
              {#each l.avis as a (a.id)}
                <li class="avis text-sm">
                  <span class="millesime text-lg font-semibold">{a.annee}</span>{#if a.environ}<span class="secondaire"> environ</span>{/if}
                  {#if a.mot}<span class="mot">« {a.mot} »</span>{/if}
                  <span class="secondaire block text-xs">{a.invites.length ? a.invites.join(', ') : 'Invitation sans prénom'} · {dateCourte(a.le)}{a.date_affichee ? ` · voyait ${dateJour(a.date_affichee)}` : ' · photo de « Aidez-moi à dater »'}</span>
                </li>
              {/each}
            </ul>
            <div class="mt-3 flex flex-wrap gap-2">
              {#each l.annees as an}
                <button class="bouton bouton-principal min-h-9" onclick={() => geste(l, 'accepter', an)} disabled={occupe || session.lecture_seule}>
                  Accepter {an}{marqueEnviron(l.avis, an) ? ' (±3)' : ''}</button>
              {/each}
              <button class="bouton min-h-9" onclick={() => { correction = l.asset_id; anneeTapee = String(l.estimation?.annee ?? l.annees[0]) }}
                      disabled={occupe || session.lecture_seule}>Corriger</button>
              <button class="bouton min-h-9" onclick={() => geste(l, 'ecarter')} disabled={occupe || session.lecture_seule}>Écarter</button>
            </div>
            {#if correction === l.asset_id}
              <div class="mt-2 flex flex-wrap items-center gap-2">
                <label class="text-sm" for={'annee-' + l.asset_id}>Année :</label>
                <input id={'annee-' + l.asset_id} class="champ annee" type="text" inputmode="numeric" maxlength="4" bind:value={anneeTapee} />
                <button class="bouton bouton-principal min-h-9" onclick={() => corriger(l)} disabled={occupe}>Dater</button>
                <button class="bouton min-h-9" onclick={() => (correction = null)}>Annuler</button>
              </div>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
  {/if}

  {#if aConfirmer.length}
    <h2 class="mt-8 font-semibold">À confirmer chez Sillage</h2>
    <p class="secondaire text-sm">Traitées ici, mais Sillage n'a pas encore répondu : la confirmation repart à la prochaine lecture, sans rien réécrire dans Immich.</p>
    <ul class="mt-2 space-y-2">
      {#each aConfirmer as l (l.asset_id)}
        <li class="surface ligne p-3 text-sm">
          <img class="vignette" src={`/api/vignette/${encodeURIComponent(l.asset_id)}`} alt="" loading="lazy" />
          <p>{l.issue === 'ecartee' ? 'Écartée' : l.issue === 'corrigee' ? 'Corrigée' : 'Acceptée'} · {pluriel(l.avis.length, 'avis', 'avis')}</p>
        </li>
      {/each}
    </ul>
  {/if}
{/if}

<style>
  .ligne { display: grid; grid-template-columns: 5.5rem minmax(0, 1fr); gap: 0.8rem; align-items: start; }
  .vignette { width: 5.5rem; height: 5.5rem; object-fit: cover; border-radius: 8px; background: var(--color-filet); }
  .mot { overflow-wrap: anywhere; margin-left: 0.35rem; }
  .annee { width: 6rem; }
  .alerte { color: var(--color-alerte); }
  @media (min-width: 900px) {
    .ligne { grid-template-columns: 8rem minmax(0, 1fr); }
    .vignette { width: 8rem; height: 8rem; }
  }
</style>
