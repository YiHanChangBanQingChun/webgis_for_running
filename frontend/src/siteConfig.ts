import manifest from '../public-demo/manifest.json'

export const isStaticDemo = import.meta.env.MODE === 'pages'
export const demoManifest = manifest
export const assetUrl = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\//, '')}`
