const SOURCE_MODE = 'source'

export const VIDEO_COLOR_PREVIEW_OPTIONS = Object.freeze([
  Object.freeze({
    value: SOURCE_MODE,
    label: 'Source',
    hint: 'No display transform',
  }),
  Object.freeze({
    value: 'arri-logc3-rec709',
    label: 'ARRI LogC3',
    hint: 'EI 400 to Rec.709',
  }),
  Object.freeze({
    value: 'arri-logc4-rec709',
    label: 'ARRI LogC4',
    hint: 'AWG4 to Rec.709',
  }),
  Object.freeze({
    value: 'sony-slog3-rec709',
    label: 'Sony S-Log3',
    hint: 'S-Gamut3.Cine to Rec.709',
  }),
  Object.freeze({
    value: 'blackmagic-film-gen5-rec709',
    label: 'Blackmagic Film Gen 5',
    hint: 'Wide Gamut to Rec.709',
  }),
  Object.freeze({
    value: 'canon-log3-rec709',
    label: 'Canon Log 3',
    hint: 'Cinema Gamut to Rec.709',
  }),
  Object.freeze({
    value: 'panasonic-vlog-rec709',
    label: 'Panasonic V-Log',
    hint: 'V-Gamut to Rec.709',
  }),
  Object.freeze({
    value: 'red-log3g10-rec709',
    label: 'RED Log3G10',
    hint: 'Wide Gamut RGB to Rec.709',
  }),
])

const VALID_MODES = new Set(VIDEO_COLOR_PREVIEW_OPTIONS.map(option => option.value))

export function normalizeVideoColorPreviewMode(value) {
  const normalized = String(value || '').trim().toLowerCase()
  return VALID_MODES.has(normalized) ? normalized : SOURCE_MODE
}

export function isVideoColorPreviewActive(value) {
  return normalizeVideoColorPreviewMode(value) !== SOURCE_MODE
}

const VERTEX_SHADER = `
  attribute vec2 a_position;
  varying vec2 v_texCoord;

  void main() {
    gl_Position = vec4(a_position, 0.0, 1.0);
    v_texCoord = (a_position + 1.0) * 0.5;
  }
`

const FRAGMENT_SHADER = `
  precision highp float;

  uniform sampler2D u_video;
  uniform int u_transform;
  varying vec2 v_texCoord;

  float decodeLogC3(float value) {
    const float cut = 0.139142;
    const float a = 5.555556;
    const float b = 0.064901;
    const float c = 0.256598;
    const float d = 0.383999;
    const float e = 5.571960;
    const float f = 0.092795;
    return value > cut
      ? (pow(10.0, (value - d) / c) - b) / a
      : (value - f) / e;
  }

  float decodeLogC4(float value) {
    return (pow(2.0, (value + 0.2959083927) / 0.0647954196) - 64.0) / 2231.8263091;
  }

  float decodeSLog3(float value) {
    const float cut = 171.2102946929 / 1023.0;
    return value >= cut
      ? pow(10.0, (value * 1023.0 - 420.0) / 261.5) * 0.19 - 0.01
      : (value * 1023.0 - 95.0) * 0.01125 / (171.2102946929 - 95.0);
  }

  float decodeBlackmagicFilmGen5(float value) {
    const float a = 0.0869287607;
    const float b = 0.0054940724;
    const float c = 0.5300133392;
    const float d = 8.2836059324;
    const float e = 0.0924657534;
    const float logCut = d * 0.005 + e;
    return value < logCut ? (value - e) / d : exp((value - c) / a) - b;
  }

  float decodeCanonLog3(float value) {
    if (value < 0.097465473) {
      return -(pow(10.0, (0.12783901 - value) / 0.36726845) - 1.0) / 14.98325;
    }
    if (value <= 0.15277891) return (value - 0.12512219) / 1.9754798;
    return (pow(10.0, (value - 0.12240537) / 0.36726845) - 1.0) / 14.98325;
  }

  float decodeVLog(float value) {
    return value < 0.181
      ? (value - 0.125) / 5.6
      : pow(10.0, (value - 0.598206) / 0.241514) - 0.00873;
  }

  float decodeLog3G10(float value) {
    float linear = value < 0.0
      ? value / 15.1927
      : (pow(10.0, value / 0.224282) - 1.0) / 155.975327;
    return linear - 0.01;
  }

  vec3 decodeLogC3(vec3 value) {
    return vec3(decodeLogC3(value.r), decodeLogC3(value.g), decodeLogC3(value.b));
  }

  vec3 decodeLogC4(vec3 value) {
    return vec3(decodeLogC4(value.r), decodeLogC4(value.g), decodeLogC4(value.b));
  }

  vec3 decodeSLog3(vec3 value) {
    return vec3(decodeSLog3(value.r), decodeSLog3(value.g), decodeSLog3(value.b));
  }

  vec3 decodeBlackmagicFilmGen5(vec3 value) {
    return vec3(
      decodeBlackmagicFilmGen5(value.r),
      decodeBlackmagicFilmGen5(value.g),
      decodeBlackmagicFilmGen5(value.b)
    );
  }

  vec3 decodeCanonLog3(vec3 value) {
    return 0.9 * vec3(decodeCanonLog3(value.r), decodeCanonLog3(value.g), decodeCanonLog3(value.b));
  }

  vec3 decodeVLog(vec3 value) {
    return vec3(decodeVLog(value.r), decodeVLog(value.g), decodeVLog(value.b));
  }

  vec3 decodeLog3G10(vec3 value) {
    return vec3(decodeLog3G10(value.r), decodeLog3G10(value.g), decodeLog3G10(value.b));
  }

  vec3 logC3ToLinearRec709(vec3 value) {
    mat3 gamut = mat3(
       1.617523, -0.070573, -0.021102,
      -0.537287,  1.334613, -0.226954,
      -0.080237, -0.264040,  1.248056
    );
    return gamut * decodeLogC3(value);
  }

  vec3 logC4ToLinearRec709(vec3 value) {
    mat3 gamut = mat3(
       1.8931234427, -0.2057003583, -0.0127057429,
      -0.7808815036,  1.3402574894, -0.1521848758,
      -0.1122419390, -0.1345571311,  1.1648906187
    );
    return gamut * decodeLogC4(value);
  }

  vec3 sLog3ToLinearRec709(vec3 value) {
    mat3 gamut = mat3(
       1.6269474097, -0.1785155271, -0.0444361150,
      -0.5401385389,  1.4179409275, -0.1959199662,
      -0.0868088709, -0.2394254003,  1.2403560812
    );
    return gamut * decodeSLog3(value);
  }

  vec3 blackmagicFilmGen5ToLinearRec709(vec3 value) {
    mat3 gamut = mat3(
       1.5684244798, -0.0863597560, -0.0520418621,
      -0.5227054517,  1.3449478133, -0.2491415367,
      -0.0457191400, -0.2585611599,  1.3009172709
    );
    return gamut * decodeBlackmagicFilmGen5(value);
  }

  vec3 canonLog3ToLinearRec709(vec3 value) {
    mat3 gamut = mat3(
       1.9238612959, -0.2043108482, -0.0236850210,
      -0.7987606632,  1.4958985098, -0.4201270110,
      -0.1251006327, -0.2915876616,  1.4438120320
    );
    return gamut * decodeCanonLog3(value);
  }

  vec3 vLogToLinearRec709(vec3 value) {
    mat3 gamut = mat3(
       1.8065758837, -0.1700903431, -0.0252057840,
      -0.6956972741,  1.3059552161, -0.1544683294,
      -0.1108786096, -0.1358648730,  1.1796741134
    );
    return gamut * decodeVLog(value);
  }

  vec3 log3G10ToLinearRec709(vec3 value) {
    mat3 gamut = mat3(
       1.9819760180, -0.1781431821, -0.1017959660,
      -0.9004318366,  1.5004683579, -0.5352634592,
      -0.0815441813, -0.3223251759,  1.6370594252
    );
    return gamut * decodeLog3G10(value);
  }

  vec3 mapToDisplay(vec3 value) {
    vec3 linear = max(value, vec3(0.0));
    float luminance = dot(linear, vec3(0.2126, 0.7152, 0.0722));
    linear /= 1.0 + luminance;
    return pow(clamp(linear, 0.0, 1.0), vec3(1.0 / 2.4));
  }

  void main() {
    vec4 source = texture2D(u_video, v_texCoord);
    vec3 color = source.rgb;
    if (u_transform == 1) color = mapToDisplay(logC3ToLinearRec709(color));
    if (u_transform == 2) color = mapToDisplay(logC4ToLinearRec709(color));
    if (u_transform == 3) color = mapToDisplay(sLog3ToLinearRec709(color));
    if (u_transform == 4) color = mapToDisplay(blackmagicFilmGen5ToLinearRec709(color));
    if (u_transform == 5) color = mapToDisplay(canonLog3ToLinearRec709(color));
    if (u_transform == 6) color = mapToDisplay(vLogToLinearRec709(color));
    if (u_transform == 7) color = mapToDisplay(log3G10ToLinearRec709(color));
    gl_FragColor = vec4(color, 1.0);
  }
`

function compileShader(gl, type, source) {
  const shader = gl.createShader(type)
  if (!shader) throw new Error('Could not prepare the color preview')
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader)
    throw new Error('Could not prepare the color preview')
  }
  return shader
}

function createProgram(gl) {
  const vertexShader = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER)
  const fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER)
  const program = gl.createProgram()
  if (!program) throw new Error('Could not prepare the color preview')
  gl.attachShader(program, vertexShader)
  gl.attachShader(program, fragmentShader)
  gl.linkProgram(program)
  gl.deleteShader(vertexShader)
  gl.deleteShader(fragmentShader)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    gl.deleteProgram(program)
    throw new Error('Could not prepare the color preview')
  }
  return program
}

function getTransformIndex(mode) {
  if (mode === 'arri-logc3-rec709') return 1
  if (mode === 'arri-logc4-rec709') return 2
  if (mode === 'sony-slog3-rec709') return 3
  if (mode === 'blackmagic-film-gen5-rec709') return 4
  if (mode === 'canon-log3-rec709') return 5
  if (mode === 'panasonic-vlog-rec709') return 6
  if (mode === 'red-log3g10-rec709') return 7
  return 0
}

export function createVideoColorPreviewRenderer(canvas) {
  if (!canvas?.getContext) throw new Error('Color preview is not available in this browser')

  const gl = canvas.getContext('webgl', {
    alpha: false,
    antialias: false,
    depth: false,
    desynchronized: true,
    preserveDrawingBuffer: false,
    premultipliedAlpha: false,
    powerPreference: 'high-performance',
  })
  if (!gl) throw new Error('Color preview is not available in this browser')

  const program = createProgram(gl)
  const positionBuffer = gl.createBuffer()
  const texture = gl.createTexture()
  if (!positionBuffer || !texture) throw new Error('Could not prepare the color preview')

  const positionLocation = gl.getAttribLocation(program, 'a_position')
  const videoLocation = gl.getUniformLocation(program, 'u_video')
  const transformLocation = gl.getUniformLocation(program, 'u_transform')

  gl.useProgram(program)
  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
    -1, -1,
     1, -1,
    -1,  1,
     1,  1,
  ]), gl.STATIC_DRAW)
  gl.enableVertexAttribArray(positionLocation)
  gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0)

  gl.activeTexture(gl.TEXTURE0)
  gl.bindTexture(gl.TEXTURE_2D, texture)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true)
  gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE)
  gl.uniform1i(videoLocation, 0)

  function render(video, mode, width, height) {
    if (!video || Number(video.readyState || 0) < 2) return false
    if (gl.isContextLost()) throw new Error('The color preview graphics context was lost')

    const targetWidth = Math.max(1, Math.round(Number(width) || Number(video.videoWidth) || 1))
    const targetHeight = Math.max(1, Math.round(Number(height) || Number(video.videoHeight) || 1))
    if (canvas.width !== targetWidth) canvas.width = targetWidth
    if (canvas.height !== targetHeight) canvas.height = targetHeight

    gl.viewport(0, 0, targetWidth, targetHeight)
    gl.useProgram(program)
    gl.bindTexture(gl.TEXTURE_2D, texture)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video)
    gl.uniform1i(transformLocation, getTransformIndex(normalizeVideoColorPreviewMode(mode)))
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
    return true
  }

  function destroy() {
    gl.deleteTexture(texture)
    gl.deleteBuffer(positionBuffer)
    gl.deleteProgram(program)
  }

  return Object.freeze({ render, destroy })
}

export function drawVideoColorPreviewFrame(targetContext, video, mode, width, height) {
  const canvas = document.createElement('canvas')
  const renderer = createVideoColorPreviewRenderer(canvas)
  try {
    if (!renderer.render(video, mode, width, height)) {
      throw new Error('No video frame is ready yet')
    }
    targetContext.drawImage(canvas, 0, 0, width, height)
  } finally {
    renderer.destroy()
  }
}
