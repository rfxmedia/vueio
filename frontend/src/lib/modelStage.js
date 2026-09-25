import * as THREE from 'three'
import { HorizontalBlurShader } from 'three/addons/shaders/HorizontalBlurShader.js'
import { VerticalBlurShader } from 'three/addons/shaders/VerticalBlurShader.js'
import { createModelEnvironment, disposeModel, loadModel } from './modelPreview'
import { modelPreviewUrl } from './modelThumbnails'

export const THUMBNAIL_WIDTH = 960, THUMBNAIL_HEIGHT = 540
const BACKDROP = [[0, '#3b4046'], [0.55, '#212428'], [1, '#131517']]
export const modelBackdrop = `radial-gradient(circle at 50% 40%, ${BACKDROP.map(([at, color]) => `${color} ${at * 100}%`).join(', ')})`

export function createModelRenderer(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'low-power' })
  renderer.setClearColor(0x000000, 0)
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.NeutralToneMapping
  return renderer
}

// Candidate views. The weights prefer a classic three-quarter view from the front.
const VIEWS = []
for (const [elevation, lift] of [[8, 0.9], [22, 1], [36, 0.95], [52, 0.86]]) {
  for (const [azimuth, turn] of [[35, 1], [-35, 0.97], [12, 0.95], [-12, 0.93], [60, 0.95], [-60, 0.93], [90, 0.88], [-90, 0.86]]) {
    const z = new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(90 - elevation), THREE.MathUtils.degToRad(azimuth))
    const x = new THREE.Vector3(0, 1, 0).cross(z).normalize()
    VIEWS.push({ x, y: z.clone().cross(x), z, weight: lift * turn })
  }
}

// World-space surface points in the current pose, including skinning and morphs.
function modelPoints(root) {
  root.updateMatrixWorld(true)
  const meshes = []
  let total = 0
  root.traverseVisible(object => {
    if (!object.isMesh || !object.geometry?.attributes.position) return
    meshes.push(object)
    total += object.isInstancedMesh ? object.count * 8 : object.geometry.attributes.position.count
  })
  const stride = Math.max(1, Math.ceil(total / 60000))
  const values = []
  const point = new THREE.Vector3(), matrix = new THREE.Matrix4()
  const add = () => { if (Number.isFinite(point.x + point.y + point.z)) values.push(point.x, point.y, point.z) }
  for (const mesh of meshes) {
    if (mesh.isInstancedMesh) {
      if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox()
      const { min, max } = mesh.geometry.boundingBox
      for (let instance = 0; instance < mesh.count; instance += stride) {
        mesh.getMatrixAt(instance, matrix)
        matrix.premultiply(mesh.matrixWorld)
        for (let corner = 0; corner < 8; corner++) {
          point.set(corner & 1 ? max.x : min.x, corner & 2 ? max.y : min.y, corner & 4 ? max.z : min.z).applyMatrix4(matrix)
          add()
        }
      }
      continue
    }
    // Small parts keep at least 16 samples, so they are never lost.
    const count = mesh.geometry.attributes.position.count
    const step = Math.min(stride, Math.max(1, Math.floor(count / 16)))
    for (let index = 0; index < count; index += step) {
      mesh.getVertexPosition(index, point).applyMatrix4(mesh.matrixWorld)
      add()
    }
  }
  return values
}

// Place the camera so the model fills the frame from the view that shows
// the most of it. The fit uses real perspective, so off-center, very long,
// flat, tiny, and huge models are all framed tightly.
export function frameModel(root, camera, margin) {
  const points = modelPoints(root)
  const bounds = new THREE.Box3(), point = new THREE.Vector3()
  for (let i = 0; i < points.length; i += 3) bounds.expandByPoint(point.fromArray(points, i))
  if (bounds.isEmpty()) bounds.set(point.set(-1, -1, -1), new THREE.Vector3(1, 1, 1))
  const center = bounds.getCenter(new THREE.Vector3())
  let radius = 0
  for (let i = 0; i < points.length; i += 3) radius = Math.max(radius, center.distanceToSquared(point.fromArray(points, i)))
  radius = Math.sqrt(radius) || 1

  let view = VIEWS[0], best = -1
  for (const candidate of VIEWS) {
    const { x, y } = candidate
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (let i = 0; i < points.length; i += 3) {
      const px = points[i] * x.x + points[i + 1] * x.y + points[i + 2] * x.z
      const py = points[i] * y.x + points[i + 1] * y.y + points[i + 2] * y.z
      minX = Math.min(minX, px); maxX = Math.max(maxX, px); minY = Math.min(minY, py); maxY = Math.max(maxY, py)
    }
    const score = Math.sqrt((maxX - minX) * (maxY - minY)) * candidate.weight
    if (score > best) { best = score; view = candidate }
  }

  const { x, y, z } = view
  const tanY = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * margin, tanX = tanY * camera.aspect
  let offsetX = center.dot(x), offsetY = center.dot(y), eye = 0
  const middle = center.dot(z)
  for (let pass = 0; pass < 4; pass++) {
    // The nearest camera plane that keeps every point inside the margin.
    eye = middle + radius * 0.02
    for (let i = 0; i < points.length; i += 3) {
      point.fromArray(points, i)
      const depth = point.dot(z)
      eye = Math.max(eye, depth + radius * 0.02, depth + Math.abs(point.dot(x) - offsetX) / tanX, depth + Math.abs(point.dot(y) - offsetY) / tanY)
    }
    if (pass === 3) break
    // Center the projected bounds, then fit again.
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (let i = 0; i < points.length; i += 3) {
      point.fromArray(points, i)
      const depth = eye - point.dot(z)
      const nx = (point.dot(x) - offsetX) / depth, ny = (point.dot(y) - offsetY) / depth
      minX = Math.min(minX, nx); maxX = Math.max(maxX, nx); minY = Math.min(minY, ny); maxY = Math.max(maxY, ny)
    }
    offsetX += (minX + maxX) / 2 * (eye - middle)
    offsetY += (minY + maxY) / 2 * (eye - middle)
  }
  const target = new THREE.Vector3().addScaledVector(x, offsetX).addScaledVector(y, offsetY).addScaledVector(z, middle)
  camera.position.copy(target).addScaledVector(z, eye - middle)
  camera.up.set(0, 1, 0)
  camera.lookAt(target)
  clipCamera(camera, center, radius)
  return { target, center, radius, bounds }
}

// Tight clipping planes keep depth precision high at every zoom level.
export function clipCamera(camera, center, radius) {
  const distance = camera.position.distanceTo(center)
  camera.near = Math.max(radius * 0.001, distance - radius * 4)
  camera.far = distance + radius * 4
  camera.updateProjectionMatrix()
}

// A soft contact shadow from a depth view below the model (the three.js
// contact shadow technique). It grounds the model without shadow maps.
export class ContactShadow {
  constructor() {
    this.group = new THREE.Group()
    this.target = new THREE.WebGLRenderTarget(512, 512)
    this.blurTarget = new THREE.WebGLRenderTarget(512, 512)
    const geometry = new THREE.PlaneGeometry(1, 1).rotateX(Math.PI / 2)
    this.plane = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ map: this.target.texture, transparent: true, opacity: 0.75, depthWrite: false, toneMapped: false }))
    this.plane.renderOrder = 1
    this.blurPlane = new THREE.Mesh(geometry)
    this.blurPlane.visible = false
    this.camera = new THREE.OrthographicCamera(-0.5, 0.5, 0.5, -0.5, 0, 1)
    this.camera.rotation.x = Math.PI / 2
    this.group.add(this.plane, this.blurPlane, this.camera)
    this.depth = new THREE.MeshDepthMaterial({ depthTest: false, depthWrite: false })
    this.depth.onBeforeCompile = shader => {
      shader.fragmentShader = shader.fragmentShader.replace('gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );', 'gl_FragColor = vec4( vec3( 0.0 ), 1.0 - fragCoordZ );')
    }
    this.horizontal = new THREE.ShaderMaterial({ ...HorizontalBlurShader, uniforms: THREE.UniformsUtils.clone(HorizontalBlurShader.uniforms), depthTest: false })
    this.vertical = new THREE.ShaderMaterial({ ...VerticalBlurShader, uniforms: THREE.UniformsUtils.clone(VerticalBlurShader.uniforms), depthTest: false })
  }

  place(bounds) {
    const size = bounds.getSize(new THREE.Vector3())
    const width = Math.max(size.x, size.z, size.y * 0.5) * 1.6 || 1
    this.group.position.set((bounds.min.x + bounds.max.x) / 2, bounds.min.y - width * 0.002, (bounds.min.z + bounds.max.z) / 2)
    this.plane.scale.set(width, -1, width)
    this.blurPlane.scale.set(width, 1, width)
    Object.assign(this.camera, { left: -width / 2, right: width / 2, top: width / 2, bottom: -width / 2, far: Math.max(size.y * 0.6, width * 0.01) })
    this.camera.updateProjectionMatrix()
  }

  render(renderer, scene) {
    const target = renderer.getRenderTarget()
    this.plane.visible = false
    scene.overrideMaterial = this.depth
    renderer.setRenderTarget(this.target)
    renderer.render(scene, this.camera)
    scene.overrideMaterial = null
    this.plane.visible = true
    this.blur(renderer, 3)
    this.blur(renderer, 1.2)
    renderer.setRenderTarget(target)
  }

  blur(renderer, amount) {
    this.blurPlane.visible = true
    this.blurPlane.material = this.horizontal
    this.horizontal.uniforms.tDiffuse.value = this.target.texture
    this.horizontal.uniforms.h.value = amount / 256
    renderer.setRenderTarget(this.blurTarget)
    renderer.render(this.blurPlane, this.camera)
    this.blurPlane.material = this.vertical
    this.vertical.uniforms.tDiffuse.value = this.blurTarget.texture
    this.vertical.uniforms.v.value = amount / 256
    renderer.setRenderTarget(this.target)
    renderer.render(this.blurPlane, this.camera)
    this.blurPlane.visible = false
  }

  dispose() {
    this.target.dispose()
    this.blurTarget.dispose()
    this.plane.geometry.dispose()
    for (const material of [this.plane.material, this.depth, this.horizontal, this.vertical]) material.dispose()
  }
}

// Render a 16:9 thumbnail at twice its size, then scale it down on the studio backdrop.
export function captureThumbnail(renderer, scene, root, shadow) {
  const camera = new THREE.PerspectiveCamera(30, THUMBNAIL_WIDTH / THUMBNAIL_HEIGHT)
  shadow.place(frameModel(root, camera, 0.82).bounds)
  const canvas = document.createElement('canvas')
  canvas.width = THUMBNAIL_WIDTH
  canvas.height = THUMBNAIL_HEIGHT
  const context = canvas.getContext('2d')
  const x = THUMBNAIL_WIDTH / 2, y = THUMBNAIL_HEIGHT * 0.4
  const gradient = context.createRadialGradient(x, y, 0, x, y, Math.hypot(x, THUMBNAIL_HEIGHT - y))
  for (const [at, color] of BACKDROP) gradient.addColorStop(at, color)
  context.fillStyle = gradient
  context.fillRect(0, 0, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
  const size = renderer.getSize(new THREE.Vector2()), ratio = renderer.getPixelRatio()
  try {
    shadow.render(renderer, scene)
    renderer.setPixelRatio(2)
    renderer.setSize(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT, false)
    renderer.render(scene, camera)
    // The drawing buffer is still valid in the task that rendered it.
    context.imageSmoothingQuality = 'high'
    context.drawImage(renderer.domElement, 0, 0, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
  } finally {
    renderer.setPixelRatio(ratio)
    renderer.setSize(size.x, size.y, false)
  }
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('The thumbnail could not be created.')), 'image/jpeg', 0.9))
}

// Load a model without a viewer and render its thumbnail, pose frame 0 of the first animation.
export async function renderModelThumbnail(source) {
  const renderer = createModelRenderer(document.createElement('canvas'))
  const scene = new THREE.Scene(), shadow = new ContactShadow()
  let root, environment
  try {
    const response = await fetch(modelPreviewUrl(source, 'manifest'), { credentials: 'same-origin' })
    const manifest = await response.json()
    if (!response.ok || !manifest.needs_thumbnail || manifest.format === 'abc') return null
    environment = createModelEnvironment(renderer, 'studio')
    scene.environment = environment.texture
    const loaded = await loadModel(source, manifest, renderer, new AbortController().signal)
    root = loaded.root
    if (loaded.animations.length) {
      const mixer = new THREE.AnimationMixer(root)
      mixer.clipAction(loaded.animations[0]).play()
      mixer.setTime(0)
    }
    scene.add(root, shadow.group)
    return { blob: await captureThumbnail(renderer, scene, root, shadow), generation: manifest.thumbnail_generation }
  } finally {
    disposeModel(root)
    environment?.dispose()
    shadow.dispose()
    renderer.dispose()
    renderer.forceContextLoss()
  }
}
