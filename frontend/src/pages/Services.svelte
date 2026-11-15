<script>
  // 2.0 : « Connexion », une tuile par service, comme dans carnet. (Connexion.svelte est la page
  // du mot de passe : ne pas la confondre.)
  import { api, dateCourte, pluriel, pc, versImmich } from '../lib/api.svelte.js'
  import { ICONES } from '../lib/icones.js'
  import Calcul from './Calcul.svelte'
  let { service = null } = $props()      // #connexion/<service>
  let a = $state(null)
  let erreur = $state('')
  let synchro = $state(false)
  let choisi = $state(service)
  $effect(() => { choisi = service })

  async function charger() {
    try { a = await api.get('/api/accueil') } catch (e) { erreur = e.message }
  }
  charger()
  async function synchroniser() {
    synchro = true; erreur = ''
    try { await api.post('/api/synchroniser'); await charger() } catch (e) { erreur = e.message }
    synchro = false
  }
  // un lecteur est « branché » s'il est venu lire dans les dernières heures
  const recent = (iso, heures) => !!iso && Date.now() - new Date(iso).getTime() < heures * 3600e3
  const pcActif = $derived(['en_cours', 'en_attente', 'disponible'].includes(pc.etat))
  const services = $derived([
    { cle: 'immich', nom: 'Immich', ok: !!a?.derniere_synchro,
      resume: a?.derniere_synchro ? `relu ${dateCourte(a.derniere_synchro.le)}` : 'jamais relu' },
    { cle: 'pc', nom: 'Calculateur du PC', ok: pcActif,
      resume: pc.etat === 'en_cours' ? `calcul en cours, ${pc.pourcentage} %` : pcActif ? 'prêt' : pc.etat === 'jamais_vu' ? 'jamais lancé' : 'éteint' },
    { cle: 'carnet', nom: 'carnet', ok: recent(a?.lu_par?.carnet, 48),
      resume: a?.lu_par?.carnet ? `a lu l'état ${dateCourte(a.lu_par.carnet)}` : 'n\'est jamais venu lire' },
    { cle: 'ha', nom: 'Home Assistant', ok: recent(a?.lu_par?.ha, 2),
      resume: !a?.lu_par?.ha_ouvert ? 'adresse fermée (pas de jeton)' : a?.lu_par?.ha ? `a lu l'état ${dateCourte(a.lu_par.ha)}` : 'n\'est jamais venu lire' },
    { cle: 'chambre_noire', nom: 'Chambre noire', ok: !!a?.chambre_noire?.noms && !a?.chambre_noire?.erreur,
      resume: !a?.chambre_noire?.relie ? 'non reliée (pas de jeton)' : a.chambre_noire.erreur ? 'ne répond pas' : a.chambre_noire.noms ? `noms lus ${dateCourte(a.chambre_noire.noms.le)}` : 'jamais lue' },
  ])
</script>

<h1 class="titre-page">Connexion</h1>
{#if erreur}<p class="mt-3 text-alerte" role="alert">{erreur}</p>{/if}

<nav class="tuiles mt-4" aria-label="Services">
  {#each services as s (s.cle)}
    <button class="tuile" aria-pressed={choisi === s.cle} onclick={() => (location.hash = choisi === s.cle ? '#connexion' : '#connexion/' + s.cle)}>
      <span class="flex items-start justify-between">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{@html ICONES[s.cle]}</svg>
        <span class="voyant" class:allume={s.ok} aria-hidden="true"></span>
      </span>
      <span class="nom-tuile font-semibold">{s.nom}</span>
      <span class="resume">{s.resume}</span>
    </button>
  {/each}
</nav>

{#if !choisi}
  <p class="secondaire mt-4">Touche un service pour voir son état et ce que Millésime fait avec lui.</p>
{:else if choisi === 'immich'}
  <section class="surface mt-4 p-4" aria-label="Immich">
    <h2 class="text-lg font-semibold">Immich</h2>
    <p class="secondaire mt-1 text-sm">Millésime lit dans Immich les scans, les visages et les dates de naissance. Il n'y écrit qu'à ta demande :
      la date, un tag et l'album d'une photo validée, le nom d'un groupe de visages, une fusion. Chaque écriture est dans le journal
      (<a class="lien" href="#reglages">Réglages</a>) et peut s'annuler.</p>
    <p class="mt-3 text-sm">
      {#if a?.derniere_synchro}Dernière relecture : {dateCourte(a.derniere_synchro.le)}, {pluriel(a.derniere_synchro.scans, 'scan')} relus.{:else}Jamais relu.{/if}
      <span class="secondaire">Elle se refait toute seule chaque heure, et toutes les 15 min quand le PC est disponible.</span>
    </p>
    <p class="mt-3 flex flex-wrap gap-2">
      <button class="bouton bouton-principal" onclick={synchroniser} disabled={synchro}>{synchro ? 'Synchronisation…' : 'Synchroniser maintenant'}</button>
      <a class="bouton" href={versImmich('/')} target="_blank" rel="noopener">Ouvrir Immich</a>
    </p>
  </section>
{:else if choisi === 'pc'}
  <section class="surface mt-4 p-4" aria-label="Calculateur du PC">
    <h2 class="text-lg font-semibold">Calculateur du PC</h2>
    <Calcul integre />
  </section>
{:else if choisi === 'carnet'}
  <section class="surface mt-4 p-4" aria-label="carnet">
    <h2 class="text-lg font-semibold">carnet</h2>
    <p class="secondaire mt-1 text-sm">carnet vient lire l'état de Millésime (photos à dater, calcul en attente) avec un jeton, pour te rappeler
      d'allumer le PC. Millésime n'écrit rien dans carnet. Les dates de naissance qui manquent se complètent dans carnet, qui les envoie à Immich.</p>
    {#if a}<p class="mt-3 text-sm">{pluriel(a.compteurs.sans_naissance, 'personne')} des scans {a.compteurs.sans_naissance > 1 ? 'n\'ont' : 'n\'a'} pas de date de naissance :
      <a class="lien" href="#nommer">voir la liste</a>.</p>{/if}
    <p class="secondaire mt-3 text-sm">{a?.lu_par?.carnet ? `Dernière lecture : ${dateCourte(a.lu_par.carnet)}.` : 'carnet n\'est encore jamais venu lire.'}</p>
  </section>
{:else if choisi === 'ha'}
  <section class="surface mt-4 p-4" aria-label="Home Assistant">
    <h2 class="text-lg font-semibold">Home Assistant</h2>
    <p class="secondaire mt-1 text-sm">Home Assistant lit toutes les 10 minutes les nombres de Millésime (photos à dater, à trancher, visages à analyser)
      et l'état du PC, jamais un nom. Quand au moins 20 visages attendent depuis une heure et que le PC est éteint, il te rappelle de l'allumer.
      Millésime n'écrit rien dans Home Assistant.</p>
    <p class="mt-3 text-sm">
      {#if !a?.lu_par?.ha_ouvert}Adresse fermée : pose <code>MILLESIME_JETON_HA</code> dans la stack.
      {:else if a?.lu_par?.ha}Dernière lecture : {dateCourte(a.lu_par.ha)}.
      {:else}Home Assistant n'est encore jamais venu lire (package <code>systeme/millesime.yaml</code>).{/if}
    </p>
  </section>
{:else if choisi === 'chambre_noire'}
  <section class="surface mt-4 p-4" aria-label="Chambre noire">
    <h2 class="text-lg font-semibold">Chambre noire</h2>
    <p class="secondaire mt-1 text-sm">Chambre noire envoie les photos numérisées dans Immich. À chaque relecture d'Immich, Millésime y lit le libellé,
      le tag et l'album des non datées réglés dans ses Réglages, et les suit. Millésime n'écrit rien dans Chambre noire.</p>
    {#if !a?.chambre_noire?.relie}
      <p class="mt-3 text-sm">Non reliée : pose <code>MILLESIME_JETON_CHAMBRE_NOIRE</code> dans la stack (même valeur que <code>CHAMBRE_NOIRE_JETON_MILLESIME</code>).
        En attendant, les noms viennent de la stack et de <a class="lien" href="#reglages">Réglages</a>.</p>
    {:else}
      {#if a.chambre_noire.noms}
        <dl class="mt-3 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
          <dt class="secondaire">Tag des non datées</dt><dd>{a.chambre_noire.noms.tag_non_datee}</dd>
          <dt class="secondaire">Album des non datées</dt><dd>{a.chambre_noire.noms.album_non_datees}</dd>
          <dt class="secondaire">Lu</dt><dd>{dateCourte(a.chambre_noire.noms.le)}</dd>
        </dl>
      {/if}
      {#if a.chambre_noire.erreur}<p class="mt-3 text-sm text-alerte" role="alert">Dernière lecture ratée ({dateCourte(a.chambre_noire.erreur.le)}) : {a.chambre_noire.erreur.detail}.
        {a.chambre_noire.noms ? 'Les derniers noms lus restent en usage.' : ''}</p>{/if}
      <p class="mt-3"><button class="bouton" onclick={synchroniser} disabled={synchro}>{synchro ? 'Lecture…' : 'Relire maintenant'}</button></p>
    {/if}
  </section>
{/if}

<style>
  .voyant { width: 0.6rem; height: 0.6rem; border-radius: 9999px; background: var(--color-champ); }
  .voyant.allume { background: var(--color-or); }
</style>
