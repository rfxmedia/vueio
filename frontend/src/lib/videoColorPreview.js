export function isVideoColorPreviewActive(mode) {
  return mode === 'lut'
}

const VERTEX_SHADER = `#version 300 es
  in vec2 a_position;
  out vec2 v_texCoord;
  void main() {
    gl_Position = vec4(a_position, 0.0, 1.0);
    v_texCoord = (a_position + 1.0) * 0.5;
  }
`

const FRAGMENT_SHADER = `#version 300 es
  precision highp float;
  precision highp sampler3D;
  uniform sampler2D u_video;
  uniform sampler3D u_lut;
  uniform vec3 u_domainMin;
  uniform vec3 u_domainMax;
  uniform int u_size;
  in vec2 v_texCoord;
  out vec4 outColor;

  vec3 sampleLut(ivec3 point) {
    return texelFetch(u_lut, point, 0).rgb;
  }

  void main() {
    vec3 source = texture(u_video, v_texCoord).rgb;
    vec3 position = clamp((source - u_domainMin) / (u_domainMax - u_domainMin), 0.0, 1.0)
      * float(u_size - 1);
    ivec3 base = min(ivec3(floor(position)), ivec3(u_size - 2));
    vec3 f = position - vec3(base);
    // Sort the fractional coordinates to select one of the cell's six tetrahedra.
    ivec3 first;
    ivec3 second;
    vec3 weights;
    if (f.r >= f.g) {
      if (f.g >= f.b) {
        first = ivec3(1, 0, 0); second = ivec3(1, 1, 0); weights = f.rgb;
      } else if (f.r >= f.b) {
        first = ivec3(1, 0, 0); second = ivec3(1, 0, 1); weights = f.rbg;
      } else {
        first = ivec3(0, 0, 1); second = ivec3(1, 0, 1); weights = f.brg;
      }
    } else {
      if (f.r >= f.b) {
        first = ivec3(0, 1, 0); second = ivec3(1, 1, 0); weights = f.grb;
      } else if (f.g >= f.b) {
        first = ivec3(0, 1, 0); second = ivec3(0, 1, 1); weights = f.gbr;
      } else {
        first = ivec3(0, 0, 1); second = ivec3(0, 1, 1); weights = f.bgr;
      }
    }
    vec3 color = (1.0 - weights.x) * sampleLut(base)
      + (weights.x - weights.y) * sampleLut(base + first)
      + (weights.y - weights.z) * sampleLut(base + second)
      + weights.z * sampleLut(base + ivec3(1));
    outColor = vec4(color, 1.0);
  }
`

function compileShader(gl, type, source) {
  const shader = gl.createShader(type)
  if (!shader) throw new Error('Could not prepare the LUT preview')
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader)
    throw new Error('Could not prepare the LUT preview')
  }
  return shader
}

export function createVideoColorPreviewRenderer(canvas) {
  const gl = canvas?.getContext('webgl2', {
    alpha: false, antialias: false, depth: false, desynchronized: true,
    preserveDrawingBuffer: false, premultipliedAlpha: false,
  })
  if (!gl) throw new Error('LUT previews need a browser with WebGL 2 support')

  let program, vertexShader, fragmentShader, positionBuffer, videoTexture, lutTexture
  let uploadedLut = null
  let uploadedVideoWidth = 0
  let uploadedVideoHeight = 0
  const maxTextureSize = gl.getParameter(gl.MAX_TEXTURE_SIZE)
  function destroy() {
    gl.deleteTexture(videoTexture)
    gl.deleteTexture(lutTexture)
    gl.deleteBuffer(positionBuffer)
    gl.deleteProgram(program)
    gl.deleteShader(vertexShader)
    gl.deleteShader(fragmentShader)
    uploadedLut = null
  }

  try {
    vertexShader = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER)
    fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER)
    program = gl.createProgram()
    positionBuffer = gl.createBuffer()
    videoTexture = gl.createTexture()
    lutTexture = gl.createTexture()
    if (!program || !positionBuffer || !videoTexture || !lutTexture) throw new Error('Could not prepare the LUT preview')
    gl.attachShader(program, vertexShader)
    gl.attachShader(program, fragmentShader)
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error('Could not prepare the LUT preview')

    gl.useProgram(program)
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW)
    const positionLocation = gl.getAttribLocation(program, 'a_position')
    gl.enableVertexAttribArray(positionLocation)
    gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0)
    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, videoTexture)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    gl.activeTexture(gl.TEXTURE1)
    gl.bindTexture(gl.TEXTURE_3D, lutTexture)
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MIN_FILTER, gl.NEAREST)
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_R, gl.CLAMP_TO_EDGE)
    gl.uniform1i(gl.getUniformLocation(program, 'u_video'), 0)
    gl.uniform1i(gl.getUniformLocation(program, 'u_lut'), 1)
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE)
  } catch (error) {
    destroy()
    throw error
  }

  const sizeLocation = gl.getUniformLocation(program, 'u_size')
  const minLocation = gl.getUniformLocation(program, 'u_domainMin')
  const maxLocation = gl.getUniformLocation(program, 'u_domainMax')

  function render(video, lut, width, height) {
    if (!video || Number(video.readyState || 0) < 2) return false
    if (!lut) throw new Error('Load a .cube file to preview a LUT')
    if (gl.isContextLost()) throw new Error('The LUT preview graphics context was lost. Try enabling it again.')
    const sourceWidth = Number(video.videoWidth)
    const sourceHeight = Number(video.videoHeight)
    if (sourceWidth > maxTextureSize || sourceHeight > maxTextureSize) {
      throw new Error('This video is too large for LUT preview on this device. Select a lower playback quality.')
    }
    const targetWidth = Math.max(1, Math.round(width || video.videoWidth || 1))
    const targetHeight = Math.max(1, Math.round(height || video.videoHeight || 1))
    if (canvas.width !== targetWidth) canvas.width = targetWidth
    if (canvas.height !== targetHeight) canvas.height = targetHeight
    gl.viewport(0, 0, targetWidth, targetHeight)
    gl.useProgram(program)
    if (uploadedLut !== lut) {
      gl.activeTexture(gl.TEXTURE1)
      gl.bindTexture(gl.TEXTURE_3D, lutTexture)
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false)
      gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGBA32F, lut.size, lut.size, lut.size, 0, gl.RGBA, gl.FLOAT, lut.data)
      if (gl.getError() !== gl.NO_ERROR) throw new Error('Could not load this LUT into the graphics device')
      gl.uniform1i(sizeLocation, lut.size)
      gl.uniform3fv(minLocation, lut.domainMin)
      gl.uniform3fv(maxLocation, lut.domainMax)
      uploadedLut = lut
    }
    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, videoTexture)
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video)
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
    if (uploadedVideoWidth !== sourceWidth || uploadedVideoHeight !== sourceHeight) {
      if (gl.getError() !== gl.NO_ERROR) throw new Error('Could not render this video with the LUT on this device')
      uploadedVideoWidth = sourceWidth
      uploadedVideoHeight = sourceHeight
    }
    return true
  }
  return Object.freeze({ render, destroy })
}

export function drawVideoColorPreviewFrame(targetContext, video, lut, width, height) {
  const canvas = document.createElement('canvas')
  const renderer = createVideoColorPreviewRenderer(canvas)
  try {
    if (!renderer.render(video, lut, width, height)) throw new Error('No video frame is ready yet')
    targetContext.drawImage(canvas, 0, 0, width, height)
  } finally {
    renderer.destroy()
    canvas.getContext('webgl2')?.getExtension('WEBGL_lose_context')?.loseContext()
  }
}
