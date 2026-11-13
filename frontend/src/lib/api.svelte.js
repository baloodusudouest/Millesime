// Appels à l'API Millésime. Une réponse 401 renvoie à l'écran de connexion.
export const session = $state({ connecte: null, version: '', lecture_seule: false })

async function appel(methode, chemin, corps) {
  const r = await fetch(chemin, {
    method: methode,
    headers: corps ? { 'Content-Type': 'application/json' } : {},
    body: corps ? JSON.stringify(corps) : undefined,
    credentials: 'same-origin',
  })
  if (r.status === 401 && chemin !== '/api/connexion') {
    session.connecte = false
    throw new Error('Connexion nécessaire.')
  }
  const donnees = r.headers.get('content-type')?.includes('json') ? await r.json() : null
  if (!r.ok) throw new Error(donnees?.detail || `Erreur ${r.status}`)
  return donnees
}

export const api = {
  get: (c) => appel('GET', c),
  post: (c, corps = {}) => appel('POST', c, corps),
}

export const visage = (asset, face) => `/api/visage/${asset}/${face}`
export const apercu = (asset) => `/api/apercu/${asset}`

// Lien vers Immich ouvert dans le navigateur. Le serveur renvoie une adresse complète si
// MILLESIME_IMMICH_LIEN est défini, sinon un chemin (/photos/…) : Immich est alors cherché sur
// la même machine que Millésime (192.168.1.10, nom Tailscale…), port 2283.
export function versImmich(lien) {
  if (!lien || !lien.startsWith('/')) return lien
  return `http://${location.hostname}:2283${lien}`
}

export function pluriel(n, mot, motPluriel) {
  return `${n} ${n > 1 ? motPluriel || mot + 's' : mot}`
}

// Une date seule (« 12 avr. 2005 »), sans décalage de fuseau.
export function dateJour(iso) {
  if (!iso) return '—'
  const [a, m, j] = iso.slice(0, 10).split('-').map(Number)
  return new Date(a, m - 1, j).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function dateCourte(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

// État du calculateur du PC, partagé par l'en-tête, l'Accueil et l'écran Calcul.
// Interrogé toutes les 10 s pendant un calcul, toutes les 30 s sinon (et pas quand l'onglet est caché).
export const pc = $state({ etat: null })
let minuteur = null
export async function suivrePc() {
  clearTimeout(minuteur)
  if (session.connecte && !document.hidden) {
    try { Object.assign(pc, { pourcentage: null, reste_min: null, total: null, fait: null }, await api.get('/api/pc')) } catch {}
  }
  minuteur = setTimeout(suivrePc, pc.etat === 'en_cours' || pc.etat === 'en_attente' ? 10000 : 30000)
}
if (typeof document !== 'undefined') document.addEventListener('visibilitychange', () => !document.hidden && suivrePc())
