<script>
  // Frise d'une personne : ses visages aux âges connus, ordonnés, et la photo à dater placée
  // à l'âge qu'elle aurait l'année choisie.
  import { api, visage } from '../lib/api.svelte.js'
  let { personId, nom, naissance, annee, scanAsset, scanFace } = $props()
  let f = $state(null)
  let erreur = $state('')

  $effect(() => {
    const id = personId
    f = null
    api.get(`/api/personnes/${id}/frise`).then((r) => (f = r)).catch((e) => (erreur = e.message))
  })

  const ageIci = $derived(naissance ? annee - Number(naissance.slice(0, 4)) : null)
  const elements = $derived.by(() => {
    if (!f) return []
    const liste = f.elements.map((e) => ({ ...e, ici: false }))
    liste.push({ ici: true, asset_id: scanAsset, face_id: scanFace, age: ageIci, date: String(annee) })
    return liste.sort((a, b) => (a.age ?? 0) - (b.age ?? 0))
  })
</script>

<div class="mt-3">
  <p class="text-sm"><span class="font-semibold">{nom}</span>
    {#if naissance}<span class="secondaire"> · naissance en {naissance.slice(0, 4)}</span>{/if}</p>
  {#if erreur}
    <p class="text-sm text-alerte">{erreur}</p>
  {:else if !f}
    <p class="secondaire text-sm">Frise en préparation…</p>
  {:else if f.elements.length === 0}
    <p class="secondaire text-sm">Aucune photo datée de cette personne pour comparer.</p>
  {:else}
    <ol class="mt-2 flex snap-x gap-2 overflow-x-auto pb-2" aria-label="Frise de {nom}">
      {#each elements as e (e.ici ? 'ici' : e.asset_id)}
        <li class="w-[84px] shrink-0 snap-start text-center">
          <img src={visage(e.asset_id, e.face_id)} alt={e.ici ? 'Cette photo' : `${nom} à ${Math.round(e.age)} ans`}
               loading="lazy" width="84" height="84"
               class="aspect-square w-full rounded-md object-cover {e.ici ? 'ring-2 ring-or' : 'opacity-90'}" />
          <p class="mt-1 text-xs leading-tight" class:text-or={e.ici}>
            {e.ici ? 'cette photo' : e.date.slice(0, 4)}<br />
            <span class:secondaire={!e.ici}>{e.age !== null ? `${Math.round(e.age)} ans` : ''}</span>
          </p>
        </li>
      {/each}
    </ol>
  {/if}
</div>
