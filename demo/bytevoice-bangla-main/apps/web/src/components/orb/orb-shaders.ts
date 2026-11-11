const SIMPLEX_NOISE = /* glsl */ `
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(
    i.z + vec4(0.0, i1.z, i2.z, 1.0))
    + i.y + vec4(0.0, i1.y, i2.y, 1.0))
    + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
  p0 *= norm.x;
  p1 *= norm.y;
  p2 *= norm.z;
  p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}
`;

export const ORB_VERTEX_SHADER = /* glsl */ `
uniform float uTime;
uniform float uAmplitude;
uniform float uFrequency;
uniform float uRipple;
varying vec3 vNormal;
varying vec3 vViewDirection;
varying float vDisplacement;

${SIMPLEX_NOISE}

void main() {
  float broad = snoise(position * uFrequency + vec3(uTime * 0.6, uTime * 0.4, 0.0));
  float fine = snoise(position * uFrequency * 3.1 - vec3(0.0, uTime * 1.3, uTime));
  float displacement = broad * uAmplitude + fine * uRipple;
  vec3 displaced = position + normal * displacement;
  vec4 worldPosition = modelMatrix * vec4(displaced, 1.0);
  vNormal = normalize(normalMatrix * normal);
  vViewDirection = normalize(cameraPosition - worldPosition.xyz);
  vDisplacement = displacement;
  gl_Position = projectionMatrix * viewMatrix * worldPosition;
}
`;

export const ORB_FRAGMENT_SHADER = /* glsl */ `
uniform vec3 uCoreColor;
uniform vec3 uSurfaceColor;
uniform vec3 uGlowColor;
uniform float uGlowStrength;
uniform float uSaturation;
varying vec3 vNormal;
varying vec3 vViewDirection;
varying float vDisplacement;

void main() {
  float facing = clamp(dot(normalize(vNormal), normalize(vViewDirection)), 0.0, 1.0);
  float fresnel = pow(1.0 - facing, 2.4);
  float band = smoothstep(-0.25, 0.35, vDisplacement);
  vec3 body = mix(uCoreColor, uSurfaceColor, band);
  vec3 color = body * (0.6 + 0.5 * facing) + uGlowColor * fresnel * uGlowStrength;
  float luminance = dot(color, vec3(0.299, 0.587, 0.114));
  color = mix(vec3(luminance), color, uSaturation);
  gl_FragColor = vec4(color, 1.0);
}
`;

export const RING_VERTEX_SHADER = /* glsl */ `
uniform float uTime;
uniform float uSpin;
uniform float uPulse;
uniform float uPointSize;
attribute float aSeed;
varying float vAlpha;

void main() {
  float angle = atan(position.z, position.x) + uTime * uSpin * (0.6 + aSeed * 0.8);
  float radius = length(position.xz) * (1.0 + uPulse * sin(uTime * 3.0 + aSeed * 12.0) * 0.06);
  vec3 moved = vec3(cos(angle) * radius, position.y + sin(uTime * 0.8 + aSeed * 20.0) * 0.03, sin(angle) * radius);
  vec4 viewPosition = modelViewMatrix * vec4(moved, 1.0);
  gl_PointSize = uPointSize * (0.5 + aSeed) * (3.0 / -viewPosition.z);
  vAlpha = 0.35 + 0.65 * aSeed;
  gl_Position = projectionMatrix * viewPosition;
}
`;

export const RING_FRAGMENT_SHADER = /* glsl */ `
uniform vec3 uColor;
uniform float uOpacity;
varying float vAlpha;

void main() {
  vec2 centered = gl_PointCoord - vec2(0.5);
  float distanceFromCenter = length(centered);
  if (distanceFromCenter > 0.5) discard;
  float softness = smoothstep(0.5, 0.0, distanceFromCenter);
  gl_FragColor = vec4(uColor, softness * vAlpha * uOpacity);
}
`;
