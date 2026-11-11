// Appels à l'API Millésime. Une réponse 401 renvoie à l'écran de connexion.
export const session = $state({ connecte: null, version: '' })

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

export function dateCourte(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
