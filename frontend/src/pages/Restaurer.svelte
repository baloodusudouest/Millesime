<script>
  // 2.12.0 : « Restaurer les réglages » : l'Anneau garde chaque nuit les réglages de Millésime.
  // On choisit une date, on voit ce qui changerait (actuel → sauvegardé), on confirme. Rien n'est écrit dans Immich.
  import { api, dateJour } from '../lib/api.svelte.js'
  let { change = () => {} } = $props()

  const NOMS = { tag_prefixe: 'Libellé des numérisations', synchro_minutes: 'Relecture d\'Immich (minutes)',
                 album_non_datees: 'Album des non datés', modele_album: 'Album par année', libelles: 'Libellés suivis' }
  let dates = $state(null)
  let le = $state('')
  let vue = $state(null)          // { le, version, differences }
  let erreur = $state('')
  let dit = $state('')
  let occupe = $state(false)

  const montrer = (v) => Array.isArray(v) ? (v.map((x) => x.libelle ?? x).join(', ') || 'aucun')
                                          : (v === '' || v === null || v === undefined ? '(vide)' : String(v))
  async function ouvrir() {
    occupe = true; erreur = ''; dit = ''; vue = null
    try { dates = (await api.get('/api/restaurer')).dates; le = dates[0] ?? '' } catch (e) { erreur = e.message }
    occupe = false
  }
  async function voir() {
    if (!le) return
    occupe = true; erreur = ''; dit = ''
    try { vue = await api.get(`/api/restaurer?le=${encodeURIComponent(le)}`) } catch (e) { erreur = e.message; vue = null }
    occupe = false
  }
  async function confirmer() {
    occupe = true; erreur = ''
    try { const r = await api.post('/api/restaurer', { le }); dit = r.message; vue = null; change() } catch (e) { erreur = e.message }
    occupe = false
  }
</script>

<section class="surface mt-4 p-4" aria-labelledby="titre-restaurer">
  <h2 id="titre-restaurer" class="text-lg font-semibold">Restaurer les réglages</h2>
  <p class="secondaire mt-1 text-sm">Chaque nuit, l'Anneau garde une copie des réglages de Millésime (lecture d'Immich, noms d'albums,
    libellés suivis), jamais un mot de passe ni une clé. Restaurer ne change que ces réglages : rien n'est écrit dans Immich.</p>
  {#if erreur}<p class="mt-3 text-alerte" role="alert">{erreur}</p>{/if}
  {#if dit}<p class="mt-3 text-sm" role="status">{dit}</p>{/if}
  {#if dates === null}
    <p class="mt-3"><button class="bouton" onclick={ouvrir} disabled={occupe}>{occupe ? 'Lecture chez l\'Anneau…' : 'Voir les sauvegardes'}</button></p>
  {:else}
    <form class="mt-3 flex flex-wrap items-end gap-2" onsubmit={(e) => { e.preventDefault(); voir() }}>
      <label class="grid min-w-0 flex-1 gap-1 text-sm"><span>Sauvegarde du</span>
        <select class="champ" bind:value={le} onchange={() => (vue = null)}>
          {#each dates as d (d)}<option value={d}>{dateJour(d)}</option>{/each}
        </select></label>
      <button class="bouton" type="submit" disabled={occupe || !le}>Voir les différences</button>
    </form>
    {#if vue}
      {#if vue.differences.length === 0}
        <p class="mt-3 text-sm">Rien ne diffère : les réglages actuels sont ceux de cette sauvegarde.</p>
      {:else}
        <ul class="mt-3 grid gap-2" aria-label="Différences avec la sauvegarde">
          {#each vue.differences as d (d.cle)}
            <li class="rounded-lg border border-filet px-3 py-2 text-sm">
              <p class="font-medium">{NOMS[d.cle] ?? d.cle}</p>
              <p class="break-words"><span class="secondaire">{montrer(d.actuel)}</span> → <strong>{montrer(d.sauve)}</strong></p>
            </li>
          {/each}
        </ul>
        <p class="mt-3 flex flex-wrap gap-2">
          <button class="bouton bouton-principal" onclick={confirmer} disabled={occupe}>Restaurer {vue.differences.length} réglage{vue.differences.length > 1 ? 's' : ''}</button>
          <button class="bouton" onclick={() => (vue = null)}>Garder les réglages actuels</button>
        </p>
        {#if vue.version}<p class="secondaire mt-2 text-sm">Sauvegarde faite par Millésime {vue.version}.</p>{/if}
      {/if}
    {/if}
  {/if}
</section>
