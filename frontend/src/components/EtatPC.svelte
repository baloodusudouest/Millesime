<script>
  // État du calculateur du PC : non disponible, disponible, en attente, calcul en cours (barre + temps restant).
  // compact : pastille de l'en-tête (lien vers l'écran Calcul).
  import { pc, dateCourte } from '../lib/api.svelte.js'
  let { compact = false } = $props()

  const titre = $derived({
    en_cours: 'Calcul en cours sur le PC',
    en_attente: 'PC disponible, calcul imminent',
    disponible: 'PC disponible',
    indisponible: 'PC non disponible',
    jamais_vu: 'Calculateur jamais lancé',
  }[pc.etat] ?? '')
  const nomPc = $derived(pc.machine ? ` (${pc.machine})` : '')
  const actif = $derived(pc.etat === 'en_cours' || pc.etat === 'en_attente' || pc.etat === 'disponible')
</script>

{#if pc.etat}
  {#if compact}
    <a href="#connexion/pc" class="flex items-center gap-2 rounded-md px-2 py-1 text-xs" title={titre}>
      <span class="pastille" class:allumee={actif} class:pulse={pc.etat === 'en_cours'} aria-hidden="true"></span>
      <span class="secondaire">{pc.etat === 'en_cours' ? `PC ${pc.pourcentage} %` : actif ? 'PC prêt' : 'PC éteint'}</span>
      <span class="sr-only">{titre}</span>
    </a>
  {:else}
    <section class="surface rounded-lg p-4" aria-live="polite">
      <p class="flex items-center gap-2 font-semibold">
        <span class="pastille" class:allumee={actif} class:pulse={pc.etat === 'en_cours'} aria-hidden="true"></span>
        {titre}{nomPc}
      </p>

      {#if pc.etat === 'en_cours'}
        <div class="mt-3 h-2 overflow-hidden rounded-full bg-filet" role="progressbar"
             aria-valuemin="0" aria-valuemax={pc.total} aria-valuenow={pc.fait}
             aria-label="{pc.fait} visages analysés sur {pc.total}">
          <div class="h-full bg-or transition-[width] duration-700" style="width: {pc.pourcentage}%"></div>
        </div>
        <p class="mt-2 flex flex-wrap justify-between gap-x-4 text-sm">
          <span><strong class="text-etiquette">{pc.fait}</strong> / {pc.total} visages · {pc.pourcentage} %</span>
          <span class="secondaire">{pc.reste_min === null ? 'estimation du temps restant…' : pc.reste_min < 1 ? 'moins d’une minute' : `encore ~${pc.reste_min} min`}</span>
        </p>
      {:else if pc.etat === 'en_attente'}
        <p class="secondaire mt-1 text-sm">{pc.restants} visage{pc.restants > 1 ? 's' : ''} en attente : le PC les prend à son prochain passage (moins de 5 min).</p>
      {:else if pc.etat === 'disponible'}
        <p class="secondaire mt-1 text-sm">Rien à calculer. Le PC revérifie toutes les 5 min et Millésime relit Immich au passage (dernier contact il y a {pc.il_y_a_min} min).</p>
      {:else if pc.etat === 'indisponible'}
        <p class="secondaire mt-1 text-sm">Dernier contact {dateCourte(pc.le)}. {pc.restants ? `${pc.restants} visage${pc.restants > 1 ? 's' : ''} attendent : allume` : 'Pour le prochain calcul, allume'} le PC et ouvre Docker Desktop.</p>
      {:else}
        <p class="secondaire mt-1 text-sm">Voir le mode d'emploi dans <a class="lien" href="#connexion/pc">Calcul sur le PC</a>.</p>
      {/if}
    </section>
  {/if}
{/if}

<style>
  .pastille { width: 0.6rem; height: 0.6rem; border-radius: 9999px; background: var(--color-champ); flex: none; }
  .pastille.allumee { background: var(--color-or); }
  .pulse { animation: pulse 1.6s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.35; } }
  @media (prefers-reduced-motion: reduce) { .pulse { animation: none; } }
</style>
