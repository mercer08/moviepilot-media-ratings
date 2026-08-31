/* MoviePilot app-shell cache migration for the multi-source ratings UI v1.5.0. */
'use strict'

self.addEventListener('install', () => self.skipWaiting())

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const cacheNames = await caches.keys()
    const staleCaches = cacheNames.filter(name =>
      name.includes('precache') ||
      name.startsWith('api-cache-') ||
      name.startsWith('image-cache-') ||
      name.startsWith('tmdb-image-cache-')
    )
    await Promise.all(staleCaches.map(name => caches.delete(name)))
    await self.clients.claim()
  })())
})

self.addEventListener('fetch', event => {
  if (event.request.mode === 'navigate') {
    event.stopImmediatePropagation()
    event.respondWith(fetch(event.request))
  }
})

importScripts('/service-worker-origin.js')
