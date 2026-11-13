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
    try { await api.post(`/api/journal/${j.id}/annuler`); await charger() } catch (e) { erreur = e.message }
  }
  function libelle(j) {
    if (j.action === 'valider') return `Datée ${j.apres.tag?.split('/').pop() ?? ''}, album « ${j.apres.album} »`
    if (j.action === 'plusieurs') return 'Mise de côté : plusieurs années'
    if (j.action === 'nommer') return `Groupe de visages nommé « ${j.apres.nom} »`
    if (j.action === 'detacher') return `Visage retiré de ${j.avant.nom || 'la personne'} (ce n'était pas elle)`
    if (j.action === 'fusionner') return `${j.avant.faces?.length ?? 0} visages rattachés à ${j.apres.cible_nom}`
    return j.action
  }
</script>

{#if integre}<h2 class="text-lg font-semibold">Journal</h2>{:else}<h1 class="titre-page">Journal</h1>{/if}
<p class="secondaire mt-2">Chaque écriture dans Immich, avec ce qu'il y avait avant. Annuler remet la date, le tag et l'album d'origine.</p>
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
          <p class="secondaire text-sm">{dateCourte(j.le)}{j.annule_le ? ` · annulée le ${dateCourte(j.annule_le)}` : ''}{j.apres.erreur ? ' · écriture interrompue' : ''}</p>
        </div>
        {#if !j.annule_le}
          <button class="bouton" onclick={() => annuler(j)}>Annuler</button>
        {/if}
      </li>
    {/each}
  </ul>
{:else if !erreur}
  <p class="secondaire mt-6">Chargement…</p>
{/if}
