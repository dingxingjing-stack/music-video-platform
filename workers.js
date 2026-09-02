addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  const url = new URL(request.url)

  // Skip caching for service worker and workbox files
  if (url.pathname.endsWith('sw.js') || url.pathname.includes('workbox-')) {
    const response = await ASSETS.fetch(request)
    // Ensure no-cache header
    const newResponse = new Response(response.body, response)
    newResponse.headers.set('Cache-Control', 'no-cache')
    return newResponse
  }

  // For all other requests, try to serve asset
  return await ASSETS.fetch(request)
}