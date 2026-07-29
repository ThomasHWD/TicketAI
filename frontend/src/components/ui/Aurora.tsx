import { useEffect, useRef } from "react";

/**
 * Aurora — fond animé WebGL (portage react-bits « Aurora-JS-CSS »).
 *
 * La version originale de react-bits dépend de `ogl`. Pour éviter d'ajouter
 * une dépendance externe, ce composant est réécrit en WebGL2 natif : même
 * shader (bruit simplex + rampe de couleurs), rendu identique, aucune lib.
 */

export interface AuroraProps {
  colorStops?: [string, string, string];
  amplitude?: number;
  blend?: number;
  speed?: number;
  /** Temps forcé (sinon dérivé de requestAnimationFrame). */
  time?: number;
  className?: string;
}

const VERT = `#version 300 es
in vec2 position;
void main() {
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

const FRAG = `#version 300 es
precision highp float;

uniform float uTime;
uniform float uAmplitude;
uniform vec3 uColorStops[3];
uniform vec2 uResolution;
uniform float uBlend;

out vec4 fragColor;

vec3 permute(vec3 x) {
  return mod(((x * 34.0) + 1.0) * x, 289.0);
}

float snoise(vec2 v) {
  const vec4 C = vec4(
    0.211324865405187, 0.366025403784439,
    -0.577350269189626, 0.024390243902439
  );
  vec2 i  = floor(v + dot(v, C.yy));
  vec2 x0 = v - i + dot(i, C.xx);
  vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
  vec4 x12 = x0.xyxy + C.xxzz;
  x12.xy -= i1;
  i = mod(i, 289.0);

  vec3 p = permute(
    permute(i.y + vec3(0.0, i1.y, 1.0))
    + i.x + vec3(0.0, i1.x, 1.0)
  );

  vec3 m = max(
    0.5 - vec3(
      dot(x0, x0),
      dot(x12.xy, x12.xy),
      dot(x12.zw, x12.zw)
    ),
    0.0
  );
  m = m * m;
  m = m * m;

  vec3 x = 2.0 * fract(p * C.www) - 1.0;
  vec3 h = abs(x) - 0.5;
  vec3 ox = floor(x + 0.5);
  vec3 a0 = x - ox;
  m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);

  vec3 g;
  g.x = a0.x * x0.x + h.x * x0.y;
  g.yz = a0.yz * x12.xz + h.yz * x12.yw;
  return 130.0 * dot(m, g);
}

struct ColorStop {
  vec3 color;
  float position;
};

#define COLOR_RAMP(colors, factor, finalColor) {                 \
  int index = 0;                                                 \
  for (int i = 0; i < 2; i++) {                                  \
     ColorStop currentColor = colors[i];                         \
     bool isInBetween = currentColor.position <= factor;         \
     index = int(mix(float(index), float(i), float(isInBetween))); \
  }                                                              \
  ColorStop currentColor = colors[index];                        \
  ColorStop nextColor = colors[index + 1];                       \
  float range = nextColor.position - currentColor.position;      \
  float lerpFactor = (factor - currentColor.position) / range;   \
  finalColor = mix(currentColor.color, nextColor.color, lerpFactor); \
}

void main() {
  vec2 uv = gl_FragCoord.xy / uResolution;

  ColorStop colors[3];
  colors[0] = ColorStop(uColorStops[0], 0.0);
  colors[1] = ColorStop(uColorStops[1], 0.5);
  colors[2] = ColorStop(uColorStops[2], 1.0);

  vec3 rampColor;
  COLOR_RAMP(colors, uv.x, rampColor);

  float height = snoise(vec2(uv.x * 2.0 + uTime * 0.1, uTime * 0.25)) * 0.5 * uAmplitude;
  height = exp(height);
  height = (uv.y * 2.0 - height + 0.2);
  float intensity = 0.6 * height;

  float midPoint = 0.20;
  float auroraAlpha = smoothstep(midPoint - uBlend * 0.5, midPoint + uBlend * 0.5, intensity);

  vec3 auroraColor = intensity * rampColor;

  fragColor = vec4(auroraColor * auroraAlpha, auroraAlpha);
}
`;

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const int = parseInt(full, 16);
  return [((int >> 16) & 255) / 255, ((int >> 8) & 255) / 255, (int & 255) / 255];
}

function compileShader(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader {
  const shader = gl.createShader(type)!;
  gl.shaderSource(shader, src);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`Aurora shader compile error: ${log}`);
  }
  return shader;
}

export default function Aurora({
  colorStops = ["#10b981", "#a7f3d0", "#059669"],
  amplitude = 1.0,
  blend = 0.5,
  speed = 1.0,
  time,
  className,
}: AuroraProps) {
  // Les props sont lues dans la boucle d'animation via une ref pour éviter
  // de recréer le contexte WebGL à chaque rendu.
  const propsRef = useRef({ colorStops, amplitude, blend, speed, time });
  propsRef.current = { colorStops, amplitude, blend, speed, time };

  const ctnDom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctn = ctnDom.current;
    if (!ctn) return;

    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2", {
      alpha: true,
      premultipliedAlpha: true,
      antialias: true,
    });
    if (!gl) return; // WebGL2 indisponible → pas de fond animé (dégradation gracieuse)

    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    canvas.style.backgroundColor = "transparent";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.display = "block";

    const program = gl.createProgram()!;
    const vs = compileShader(gl, gl.VERTEX_SHADER, VERT);
    const fs = compileShader(gl, gl.FRAGMENT_SHADER, FRAG);
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(`Aurora program link error: ${gl.getProgramInfoLog(program)}`);
    }
    gl.useProgram(program);

    // Triangle plein écran (couvre tout le viewport clip-space).
    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const posLoc = gl.getAttribLocation(program, "position");
    gl.enableVertexAttribArray(posLoc);
    gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

    const uTime = gl.getUniformLocation(program, "uTime");
    const uAmplitude = gl.getUniformLocation(program, "uAmplitude");
    const uColorStops = gl.getUniformLocation(program, "uColorStops");
    const uResolution = gl.getUniformLocation(program, "uResolution");
    const uBlend = gl.getUniformLocation(program, "uBlend");

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = ctn!.offsetWidth;
      const height = ctn!.offsetHeight;
      canvas.width = Math.max(1, Math.floor(width * dpr));
      canvas.height = Math.max(1, Math.floor(height * dpr));
      gl!.viewport(0, 0, canvas.width, canvas.height);
      gl!.uniform2f(uResolution, canvas.width, canvas.height);
    }
    window.addEventListener("resize", resize);
    ctn.appendChild(canvas);
    resize();

    // Respecte prefers-reduced-motion : on rend une seule frame figée plutôt
    // que d'animer en continu (moins de mouvement, moins de charge GPU).
    const reduceMotion =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

    let animateId = 0;
    const update = (t: number) => {
      const p = propsRef.current;
      const now = p.time ?? t * 0.01;

      gl.useProgram(program);
      gl.uniform1f(uTime, now * (p.speed ?? 1.0) * 0.1);
      gl.uniform1f(uAmplitude, p.amplitude ?? 1.0);
      gl.uniform1f(uBlend, p.blend ?? 0.5);
      const stops = p.colorStops ?? colorStops;
      gl.uniform3fv(uColorStops, new Float32Array(stops.flatMap(hexToRgb)));

      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.bindVertexArray(vao);
      gl.drawArrays(gl.TRIANGLES, 0, 3);

      if (!reduceMotion) animateId = requestAnimationFrame(update);
    };
    if (reduceMotion) {
      update(0); // frame statique unique
    } else {
      animateId = requestAnimationFrame(update);
    }

    return () => {
      cancelAnimationFrame(animateId);
      window.removeEventListener("resize", resize);
      if (canvas.parentNode === ctn) ctn.removeChild(canvas);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={ctnDom} className={className ?? "w-full h-full"} />;
}
