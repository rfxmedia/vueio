import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js'
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js'
import { MTLLoader } from 'three/addons/loaders/MTLLoader.js'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'
import { DRACOLoader, DRACO_GLTF_CONFIG } from 'three/addons/loaders/DRACOLoader.js'
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js'
import { TGALoader } from 'three/addons/loaders/TGALoader.js'
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import { modelPreviewUrl } from './modelThumbnails'

export async function fetchModelBytes(url, signal, onProgress, priority = 'auto') {
  const response = await fetch(url, { credentials: 'same-origin', signal, priority })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : 'The model could not be loaded. Try again.')
  }
  const limit = 128 * 1024 * 1024
  const total = Number(response.headers.get('Content-Length'))
  if (total > limit) throw new Error('This model is too large for a browser preview. Export a smaller GLB.')
  const reader = response.body.getReader()
  const chunks = []
  let received = 0
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      received += value.byteLength
      if (received > limit) throw new Error('This model is too large for a browser preview. Export a smaller GLB.')
      chunks.push(value)
      onProgress?.(total ? Math.min(100, received / total * 100) : null)
    }
  } finally {
    await reader.cancel().catch(() => {})
  }
  const buffer = new Uint8Array(received)
  let offset = 0
  for (const chunk of chunks) { buffer.set(chunk, offset); offset += chunk.byteLength }
  return buffer.buffer
}

export function disposeModel(root) {
  const resources = new Set()
  root?.traverse(object => {
    if (object.geometry) resources.add(object.geometry)
    if (object.skeleton) resources.add(object.skeleton)
    for (const material of (Array.isArray(object.material) ? object.material : [object.material])) {
      if (!material) continue
      resources.add(material)
      for (const value of Object.values(material)) if (value?.isTexture) resources.add(value)
    }
  })
  for (const resource of resources) {
    resource.source?.data?.close?.()
    resource.dispose()
  }
}

const IMAGE_TYPES = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', avif: 'image/avif', bmp: 'image/bmp' }

// Exporters often keep the artist's absolute path or a moved folder. Match
// the longest trailing part of a declared companion path, never the network.
function companionUrl(dependencies, url) {
  if (/^blob:/.test(url) || /^data:(image\/(png|jpeg|webp)|application\/(octet-stream|gltf-buffer));base64,/i.test(url)) return url
  let name = url
  try { name = decodeURIComponent(url) } catch { /* Keep the raw name. */ }
  name = name.replace(/\\/g, '/').replace(/^\.\//, '')
  if (dependencies.has(name)) return dependencies.get(name)
  const wanted = name.toLowerCase()
  let found = 'data:,', length = 0
  for (const [dependency, blobUrl] of dependencies) {
    const parts = dependency.toLowerCase().split('/')
    for (let index = 0; index < parts.length; index++) {
      const suffix = parts.slice(index).join('/')
      if (suffix.length <= length) break
      if (wanted === suffix || wanted.endsWith(`/${suffix}`) || wanted.endsWith(` ${suffix}`)) { found = blobUrl; length = suffix.length; break }
    }
  }
  return found
}

function materialsOf(object) {
  return (Array.isArray(object.material) ? object.material : [object.material]).filter(Boolean)
}

// OBJ and FBX commonly use legacy Phong materials. Convert them to PBR so all
// formats respond to the same environment light.
function toStandardMaterial(material) {
  const replacement = new THREE.MeshStandardMaterial({ metalness: 0, roughness: 0.9 })
  for (const key of ['name', 'color', 'map', 'normalMap', 'normalMapType', 'normalScale', 'bumpMap', 'bumpScale', 'displacementMap', 'displacementScale', 'displacementBias', 'aoMap', 'aoMapIntensity', 'lightMap', 'lightMapIntensity', 'emissive', 'emissiveMap', 'emissiveIntensity', 'alphaMap', 'alphaTest', 'opacity', 'transparent', 'side', 'vertexColors', 'flatShading']) {
    if (material[key] !== undefined) replacement[key] = material[key]
  }
  // Blinn-Phong exponent to perceptual GGX roughness. A black specular color means a matte surface.
  if (material.isMeshPhongMaterial && Math.max(material.specular.r, material.specular.g, material.specular.b) >= 0.02) {
    replacement.roughness = THREE.MathUtils.clamp((2 / (material.shininess + 2)) ** 0.25, 0.25, 0.9)
  }
  return replacement
}

// Uncompressed textures use 4 bytes per texel and one third more for mipmaps.
// The budget holds four 4096 px maps or one 8192 px map at full resolution.
const TEXTURE_BUDGET = 64 * 1024 * 1024 * 4 * 4 / 3
// Viewers notice lower resolution on these maps first, so they are reduced last.
const DETAIL_MAPS = new Set(['map', 'normalMap', 'emissiveMap'])

// KTX2 files can store their own mip levels. Drop the largest levels to reduce them.
const hasLevels = texture => texture.isCompressedTexture || texture.mipmaps?.length > 1

function textureCost({ texture, steps }) {
  if (hasLevels(texture)) return texture.mipmaps.slice(steps).reduce((sum, level) => sum + level.data.byteLength, 0)
  const { width, height } = texture.image
  return Math.max(1, width >> steps) * Math.max(1, height >> steps) * 16 / 3
}

function canReduce({ texture, steps }) {
  if (hasLevels(texture)) return steps < texture.mipmaps.length - 1
  const { width, height, data } = texture.image
  // TGA files decode to RGBA bytes. Other data textures keep their resolution.
  if (data && !(data instanceof Uint8Array && data.length === width * height * 4)) return false
  return Math.max(width >> steps, height >> steps) > 1
}

function halveTexels({ data, width, height }) {
  const halfWidth = Math.max(1, width >> 1), halfHeight = Math.max(1, height >> 1)
  const result = new Uint8Array(halfWidth * halfHeight * 4)
  for (let y = 0; y < halfHeight; y++) {
    const top = Math.min(y * 2, height - 1) * width, bottom = Math.min(y * 2 + 1, height - 1) * width
    for (let x = 0; x < halfWidth; x++) {
      const left = Math.min(x * 2, width - 1), right = Math.min(x * 2 + 1, width - 1)
      for (let c = 0; c < 4; c++) {
        result[(y * halfWidth + x) * 4 + c] = (data[(top + left) * 4 + c] + data[(top + right) * 4 + c] + data[(bottom + left) * 4 + c] + data[(bottom + right) * 4 + c] + 2) >> 2
      }
    }
  }
  return { data: result, width: halfWidth, height: halfHeight }
}

// Halve one step at a time. Each 2:1 step averages all texels in every browser.
async function reduceTexture({ texture, textures, steps }) {
  if (hasLevels(texture)) {
    for (const each of textures) each.mipmaps = each.mipmaps.slice(steps)
    const { data, width, height } = texture.mipmaps[0]
    texture.source.data = texture.isCompressedTexture ? { width, height } : { data, width, height }
  } else if (texture.image.data) {
    let image = texture.image
    for (let step = 0; step < steps; step++) image = halveTexels(image)
    // Upload the new image, not a stored full-size level.
    for (const each of textures) each.mipmaps = []
    texture.source.data = image
  } else {
    const flipY = texture.flipY
    let image = texture.image
    for (let step = 0; step < steps; step++) {
      const next = await createImageBitmap(image, {
        resizeWidth: Math.max(1, image.width >> 1), resizeHeight: Math.max(1, image.height >> 1), resizeQuality: 'high',
        premultiplyAlpha: 'none', colorSpaceConversion: 'none', ...(flipY && !step ? { imageOrientation: 'flipY' } : {}),
      })
      image.close?.()
      image = next
    }
    // Uploads ignore flipY for an ImageBitmap, so the first step already flipped it.
    for (const each of textures) each.flipY = false
    texture.source.data = image
  }
  texture.source.needsUpdate = true
}

// Fit textures to the browser budget. Reduce the largest first and keep color
// and normal detail at the highest resolution. Returns true if any changed.
async function fitTextures(images, maxSize) {
  let total = 0
  for (const image of images) {
    const { width, height } = image.texture.image
    while (Math.max(width >> image.steps, height >> image.steps) > maxSize) {
      if (!canReduce(image)) throw new Error('A texture is larger than this browser can show. Export smaller textures.')
      image.steps++
    }
    total += textureCost(image)
  }
  while (total > TEXTURE_BUDGET) {
    let largest = null, largestWeight = 0
    for (const image of images) {
      const weight = textureCost(image) * (image.detail ? 1 : 2)
      if (weight > largestWeight && canReduce(image)) { largest = image; largestWeight = weight }
    }
    if (!largest) throw new Error('The textures exceed the browser preview budget. Export smaller textures.')
    total -= textureCost(largest)
    largest.steps++
    total += textureCost(largest)
  }
  const reduced = images.filter(image => image.steps)
  try {
    for (const image of reduced) await reduceTexture(image)
  } catch {
    throw new Error('This browser cannot reduce the textures. Export smaller textures.')
  }
  return reduced.length > 0
}

export async function loadModel(source, manifest, renderer, signal, onProgress, { maxTextureSize = 8192, priority = 'auto' } = {}) {
  const manager = new THREE.LoadingManager()
  const blobs = new Set()
  const warnings = new Set()
  const dependencies = new Map()
  let textureErrors = 0
  // The server authorizes declared companion files. A model may never make
  // arbitrary network requests or read other files next to a shared model.
  manager.setURLModifier(url => companionUrl(dependencies, url))
  manager.addHandler(/\.tga$/i, new TGALoader(manager))
  let textureLoads = 0
  const startItem = manager.itemStart.bind(manager), endItem = manager.itemEnd.bind(manager)
  let resolveTextures
  manager.itemStart = url => { textureLoads++; startItem(url) }
  manager.itemEnd = url => { endItem(url); if (--textureLoads === 0) resolveTextures?.() }
  manager.onError = () => { textureErrors++ }
  // The build serves these decoders as cached, compressed assets.
  const draco = new DRACOLoader().setDecoderPath(DRACO_GLTF_CONFIG).setWorkerLimit(1)
  const ktx = new KTX2Loader().setWorkerLimit(1).detectSupport(renderer)
  // KTX2 textures use the same companion-file guard. The decoder files load directly.
  const loadKtx = ktx.load.bind(ktx)
  ktx.load = (url, onLoad, onProgress, onError) => loadKtx(manager.resolveURL(url), onLoad, onProgress, error => { textureErrors++; onError(error) })
  // Stops the other downloads when one fails or the caller cancels.
  const downloads = new AbortController()
  const cancel = () => downloads.abort()
  signal.addEventListener('abort', cancel)
  let root, animations = []
  try {
    const libraries = new Map(), queue = [...(manifest.dependencies || [])]
    let failed = 0
    const download = async () => {
      for (let name = queue.shift(); name; name = queue.shift()) {
        let bytes
        try {
          bytes = await fetchModelBytes(modelPreviewUrl(source, 'dependency', { name }), downloads.signal, undefined, priority)
        } catch (error) {
          // Geometry buffers are required. The model shows without a material or texture file.
          if (downloads.signal.aborted || /\.bin$/i.test(name)) throw error
          failed++
          continue
        }
        if (downloads.signal.aborted) return
        if (/\.mtl$/i.test(name)) { libraries.set(name, new TextDecoder().decode(bytes)); continue }
        const url = URL.createObjectURL(new Blob([bytes], { type: IMAGE_TYPES[name.split('.').pop().toLowerCase()] || 'application/octet-stream' }))
        blobs.add(url)
        dependencies.set(name, url)
      }
    }
    // Three companion downloads at a time leave connections free for the rest of the app.
    const [buffer] = await Promise.all([fetchModelBytes(modelPreviewUrl(source, 'source'), downloads.signal, onProgress, priority), download(), download(), download()])
    signal.throwIfAborted()
    const ext = manifest.format
    if (ext === 'glb' || ext === 'gltf') {
      const loader = new GLTFLoader(manager).setDRACOLoader(draco).setKTX2Loader(ktx).setMeshoptDecoder(MeshoptDecoder)
      const gltf = await loader.parseAsync(buffer, '')
      root = gltf.scene
      animations = gltf.animations
    } else if (ext === 'fbx') {
      root = new FBXLoader(manager).parse(buffer, '')
      animations = root.animations || []
      root.traverse(object => {
        for (const material of materialsOf(object)) {
          if (material.map?.image?.src?.startsWith('blob:')) blobs.add(material.map.image.src)
        }
      })
    } else if (ext === 'obj') {
      const loader = new OBJLoader(manager)
      // Several material libraries merge into one. Texture names still resolve by file name.
      const names = (manifest.materials || []).filter(name => libraries.has(name))
      if (names.length) {
        const materials = new MTLLoader(manager).parse(names.map(name => libraries.get(name)).join('\n'), names[0].slice(0, names[0].lastIndexOf('/') + 1))
        materials.preload()
        loader.setMaterials(materials)
      }
      root = loader.parse(new TextDecoder().decode(buffer))
    } else if (ext === 'stl') {
      const geometry = new STLLoader().parse(buffer)
      root = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xb7bec2, roughness: 0.6, vertexColors: geometry.hasColors }))
      root.rotation.x = -Math.PI / 2
    } else throw new Error('This model format is not supported.')
    if (textureLoads) await new Promise(resolve => { resolveTextures = resolve })
    signal.throwIfAborted()
    const replacements = new Map()
    root.traverse(object => {
      if (!object.material) return
      const convert = material => {
        if (material.isMeshStandardMaterial || material.isMeshBasicMaterial) return material
        if (!replacements.has(material)) { replacements.set(material, toStandardMaterial(material)); material.dispose() }
        return replacements.get(material)
      }
      object.material = Array.isArray(object.material) ? object.material.map(convert) : convert(object.material)
    })
    let triangles = 0
    const images = new Map()
    const anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy())
    root.traverse(object => {
      if (object.isLight || object.isCamera) object.visible = false
      for (const material of materialsOf(object)) {
        for (const [key, texture] of Object.entries(material)) {
          if (!texture?.isTexture) continue
          // A texture that failed to load samples as black. Show the surface without it.
          if (!texture.image) { material[key] = null; material.needsUpdate = true; texture.dispose(); textureErrors ||= 1; continue }
          texture.anisotropy = anisotropy
          // Textures that share one image, such as a packed ORM map, count once.
          if (!images.has(texture.source)) images.set(texture.source, { texture, textures: new Set(), detail: false, steps: 0 })
          const image = images.get(texture.source)
          image.textures.add(texture)
          image.detail ||= DETAIL_MAPS.has(key)
        }
      }
      if (object.isMesh) triangles += (object.geometry.index?.count || object.geometry.attributes.position?.count || 0) / 3
    })
    if (!triangles) throw new Error('This file contains no visible mesh geometry.')
    if (triangles > 2_000_000) throw new Error('This model has more than 2 million triangles. Export a lighter review model.')
    if (await fitTextures([...images.values()], Math.min(renderer.capabilities.maxTextureSize, maxTextureSize))) {
      warnings.add('Some textures show at a lower resolution in this preview. The original files do not change.')
    }
    signal.throwIfAborted()
    const missingMaterials = manifest.missing_materials || 0, missing = manifest.missing_textures || 0
    if (missingMaterials) warnings.add(missingMaterials === 1 ? 'The material file is missing. Upload it to the model folder.' : `${missingMaterials} material files are missing. Upload them to the model folder.`)
    if (missing) warnings.add(missing === 1 ? 'A texture file is missing. Upload it to the model folder.' : `${missing} texture files are missing. Upload them to the model folder.`)
    if (manifest.skipped_files) warnings.add('Some material or texture files are too large for this preview. The model shows without them.')
    if (failed || (textureErrors && !missing && !manifest.skipped_files)) warnings.add('Some material or texture files did not load. The model shows without them.')
    return { root, animations, triangles, warnings }
  } catch (error) {
    disposeModel(root)
    throw error
  } finally {
    downloads.abort()
    signal.removeEventListener('abort', cancel)
    draco.dispose()
    ktx.dispose()
    for (const url of blobs) URL.revokeObjectURL(url)
  }
}

// Alembic frames are bounded, gzip-compressed triangle streams. Separate frames
// preserve changing topology without thousands of morph targets in GPU memory.
export function decodeModelFrame(buffer) {
  const header = new DataView(buffer)
  if (buffer.byteLength < 8 || header.getUint32(0, true) !== 0x314d5556) throw new Error('Invalid model frame.')
  const vertices = header.getUint32(4, true)
  if (vertices > 750_000 || vertices % 3 || buffer.byteLength !== 8 + vertices * 24) throw new Error('Invalid model frame size.')
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(buffer, 8, vertices * 3), 3))
  geometry.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(buffer, 8 + vertices * 12, vertices * 3), 3))
  const root = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xb7bec2, roughness: 0.6 }))
  return root
}

// Equirectangular sky, sun or moon, and ground, in linear light.
function skyTexture(night) {
  const width = 512, height = 256
  const pixels = new Float32Array(width * height * 4)
  const zenith = night ? [0.03, 0.045, 0.1] : [0.22, 0.42, 0.95]
  const horizon = night ? [0.09, 0.11, 0.18] : [0.85, 0.92, 1.05]
  const ground = night ? [0.02, 0.022, 0.03] : [0.2, 0.19, 0.17]
  // The key light is above the default camera's shoulder. The moon lights the model from the side.
  const light = (night ? new THREE.Vector3(-0.7, 0.8, 0.35) : new THREE.Vector3(0.55, 0.9, 0.65)).normalize()
  const tint = night ? [0.75, 0.85, 1] : [1, 0.95, 0.86]
  const direction = new THREE.Vector3()
  for (let y = 0; y < height; y++) {
    const elevation = ((y + 0.5) / height - 0.5) * Math.PI
    for (let x = 0; x < width; x++) {
      // The same mapping as three.js equirectUv().
      const around = ((x + 0.5) / width - 0.5) * Math.PI * 2
      direction.set(Math.cos(around) * Math.cos(elevation), Math.sin(elevation), Math.sin(around) * Math.cos(elevation))
      const angle = direction.angleTo(light)
      const disk = angle < (night ? 0.04 : 0.045) ? (night ? 45 : 90) : 0
      const glow = Math.exp(-angle * angle / (night ? 0.02 : 0.03)) * (night ? 1 : 3)
      const up = Math.max(0, Math.sin(elevation)) ** 0.5
      const offset = (y * width + x) * 4
      for (let c = 0; c < 3; c++) {
        const sky = horizon[c] + (zenith[c] - horizon[c]) * up
        pixels[offset + c] = (elevation < 0 ? ground[c] : sky) + (disk + glow) * tint[c]
      }
      pixels[offset + 3] = 1
    }
  }
  const texture = new THREE.DataTexture(pixels, width, height, THREE.RGBAFormat, THREE.FloatType)
  texture.mapping = THREE.EquirectangularReflectionMapping
  texture.needsUpdate = true
  return texture
}

export function createModelEnvironment(renderer, preset) {
  const generator = new THREE.PMREMGenerator(renderer)
  try {
    if (preset === 'daylight' || preset === 'night') {
      const texture = skyTexture(preset === 'night')
      const target = generator.fromEquirectangular(texture)
      texture.dispose()
      return target
    }
    const room = new RoomEnvironment()
    const target = generator.fromScene(room, 0.04)
    room.dispose()
    return target
  } finally {
    generator.dispose()
  }
}
