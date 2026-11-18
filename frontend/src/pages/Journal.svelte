<script>
  import { api, apercu, dateCourte } from '../lib/api.svelte.js'
  let { integre = false } = $props()   // 2.0 : affiché dans Réglages
  let liste = $state(null)
  let erreur = $state('')
  async function charger() {
    try { liste = await api.get('/api/journal') } catch (e) { erreur = e.message }
  }
  charger()
  async function annuler(j) {
    erreur = ''
    // M29 : une annulation incomplète le dit (visages qu'Immich a refusé de rendre)
    try { const r = await api.post(`/api/journal/${j.id}/annuler`); if (r?.message) erreur = r.message; await charger() } catch (e) { erreur = e.message }
  }
  const NOMS = { tag_prefixe: 'libellé des numérisations', synchro_minutes: 'relecture d\'Immich',
                 album_non_datees: 'album des non datés', modele_album: 'album par année', libelles: 'libellés suivis' }
  const REGLAGE = ['reglage_repris', 'reglages_restaures']
  function libelle(j) {
    // 2.13.0 : une photo datée sur l'avis d'un invité (Sillage) le dit ; une photo hors scans n'a pas d'album
    if (j.action === 'valider') return `Datée ${j.apres.tag?.split('/').pop() ?? ''}` + (j.apres.album ? `, album « ${j.apres.album} »` : '')
      + (j.apres.source ? ` (${j.apres.source})` : '')
    if (j.action === 'plusieurs') return 'Mise de côté : plusieurs années'
    if (j.action === 'nommer') return `Groupe de visages nommé « ${j.apres.nom} »`
    if (j.action === 'detacher') return `Visage retiré de ${j.avant.nom || 'la personne'} (ce n'était pas elle)`
    if (j.action === 'fusionner') return `${j.avant.faces?.length ?? 0} visages rattachés à ${j.apres.cible_nom}`
    if (j.action === 'reglage_repris') return `Réglage « ${NOMS[j.apres.cle] ?? j.apres.cle} » repris de la stack (${j.avant.variable})`
    if (j.action === 'reglages_restaures') return `Réglages restaurés depuis la sauvegarde du ${j.apres.le} (${j.apres.cles?.length ?? 0})`
    return j.action
  }
</script>

{#if integre}<h2 class="text-lg font-semibold">Journal</h2>{:else}<h1 class="titre-page">Journal</h1>{/if}
<p class="secondaire mt-2">Chaque écriture dans Immich, avec ce qu'il y avait avant. Annuler remet la date, le tag et l'album d'origine.
  Les réglages repris ou restaurés y sont notés aussi.</p>
{#if erreur}<p class="mt-3 text-alerte" role="alert">{erreur}</p>{/if}

{#if liste && liste.length === 0}
  <p class="mt-10 text-lg">Rien n'a encore été écrit.</p>
{:else if liste}
  <ul class="mt-6 divide-y divide-filet border-y border-filet">
    {#each liste as j (j.id)}
      <li class="flex items-center gap-3 py-3" class:opacity-50={j.annule_le}>
        {#if j.action === 'valider' || j.action === 'plusieurs'}
          <img src={apercu(j.asset_id)} alt="" width="56" height="56" loading="lazy" class="h-14 w-14 shrink-0 rounded object-cover" />
        {/if}
        <div class="min-w-0 flex-1">
          <p class="truncate">{libelle(j)}</p>
          <p class="secondaire text-sm">{dateCourte(j.le)}{j.annule_le ? ` · annulée le ${dateCourte(j.annule_le)}` : ''}{j.apres.erreur ? ' · écriture interrompue' : ''}{j.apres.non_defaits?.length ? ' · annulée en partie' : ''}</p>
        </div>
        {#if !j.annule_le && !REGLAGE.includes(j.action)}
          <button class="bouton" onclick={() => annuler(j)}>Annuler</button>
        {/if}
      </li>
    {/each}
  </ul>
{:else if !erreur}
  <p class="secondaire mt-6">Chargement…</p>
{/if}
