/**
 * Pós-processamento "de foto": profundidade de campo (usa a profundidade real da cena, então
 * respeita o recorte das folhas), brilho do sol (bloom) e tratamento de cor com vinheta e grão.
 */
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { FullScreenQuad, Pass } from "three/examples/jsm/postprocessing/Pass.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { ShaderPass } from "three/examples/jsm/postprocessing/ShaderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";

/** Desfoque por disco (16 amostras em espiral) com raio = círculo de confusão de lente fina. */
class ProfundidadeDeCampo extends Pass {
  readonly material: THREE.ShaderMaterial;
  private quad: FullScreenQuad;

  constructor(private camera: THREE.PerspectiveCamera) {
    super();
    this.material = new THREE.ShaderMaterial({
      depthTest: false,
      depthWrite: false,
      uniforms: {
        tCor: { value: null },
        tProf: { value: null },
        uTexel: { value: new THREE.Vector2() },
        uPerto: { value: camera.near },
        uLonge: { value: camera.far },
        uFoco: { value: 10 },
        uForca: { value: 1 },
        uRaio: { value: 6 },
      },
      vertexShader: /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
      fragmentShader: /* glsl */ `
        uniform sampler2D tCor; uniform sampler2D tProf; uniform vec2 uTexel;
        uniform float uPerto; uniform float uLonge; uniform float uFoco; uniform float uForca; uniform float uRaio;
        varying vec2 vUv;
        float distancia(vec2 uv) {
          float z = textureLod(tProf, uv, 0.0).x * 2.0 - 1.0;
          return 2.0 * uPerto * uLonge / (uLonge + uPerto - z * (uLonge - uPerto));
        }
        void main() {
          vec4 base = texture2D(tCor, vUv);
          float d = distancia(vUv);
          float coc = clamp(abs(d - uFoco) / max(d, 0.1) * 1.4, 0.0, 1.0) * uForca;
          // o disco do sol do céu físico passa do limite do HalfFloat: limita antes do brilho (bloom)
          base.rgb = min(base.rgb, vec3(40.0));
          if (coc < 0.02) { gl_FragColor = base; return; }
          vec3 soma = base.rgb; float peso = 1.0;
          for (int i = 0; i < 16; i++) {
            float a = float(i) * 2.39996;
            float r = sqrt(float(i) + 0.5) / 4.0;
            vec2 uv = vUv + vec2(cos(a), sin(a)) * r * coc * uRaio * uTexel;
            // não deixa o fundo desfocado "vazar" sobre o que está em foco na frente
            float dv = distancia(uv);
            float w = dv < d - 0.5 ? clamp(abs(dv - uFoco) / max(dv, 0.1) * 1.4 * uForca, 0.0, 1.0) : 1.0;
            soma += min(textureLod(tCor, uv, 0.0).rgb, vec3(40.0)) * w; peso += w;
          }
          gl_FragColor = vec4(soma / peso, base.a);
        }`,
    });
    this.quad = new FullScreenQuad(this.material);
  }

  setSize(l: number, a: number) {
    this.material.uniforms.uTexel.value.set(1 / l, 1 / a);
  }

  render(renderer: THREE.WebGLRenderer, writeBuffer: THREE.WebGLRenderTarget, readBuffer: THREE.WebGLRenderTarget) {
    const u = this.material.uniforms;
    u.tCor.value = readBuffer.texture;
    u.tProf.value = readBuffer.depthTexture;
    u.uPerto.value = this.camera.near;
    u.uLonge.value = this.camera.far;
    renderer.setRenderTarget(this.renderToScreen ? null : writeBuffer);
    this.quad.render(renderer);
  }
}

const GradeDeCor = {
  uniforms: { tDiffuse: { value: null }, uTempo: { value: 0 }, uVinheta: { value: 0.6 }, uGrao: { value: 0.03 }, uQuente: { value: 0.5 } },
  vertexShader: /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse; uniform float uTempo; uniform float uVinheta; uniform float uGrao; uniform float uQuente;
    varying vec2 vUv;
    float h(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
    void main() {
      vec3 c = texture2D(tDiffuse, vUv).rgb;
      float r = length((vUv - 0.5) * vec2(1.0, 1.2));
      c *= mix(1.0, 1.0 - smoothstep(0.35, 0.95, r), uVinheta);
      // tons quentes de fim de tarde: sombras levemente âmbar, altas luzes douradas
      float luma = dot(c, vec3(0.299, 0.587, 0.114));
      vec3 quente = mix(c * vec3(1.06, 0.98, 0.86), c * vec3(1.16, 0.94, 0.68), smoothstep(0.35, 0.95, luma));
      c = mix(c, quente + vec3(0.025, 0.012, 0.0) * (1.0 - luma), uQuente);
      c += (h(vUv * 1024.0 + fract(uTempo) * 61.0) - 0.5) * uGrao;
      gl_FragColor = vec4(c, 1.0);
    }`,
};

export class PosProcessamento {
  readonly composer: EffectComposer;
  readonly dof: ProfundidadeDeCampo;
  readonly bloom: UnrealBloomPass;
  readonly grade: ShaderPass;

  constructor(renderer: THREE.WebGLRenderer, cena: THREE.Scene, camera: THREE.PerspectiveCamera) {
    const alvo = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, depthTexture: new THREE.DepthTexture(1, 1) });
    this.composer = new EffectComposer(renderer, alvo);
    // O composer clona o alvo para o 2º buffer, e o clone da DepthTexture divide a mesma textura na GPU:
    // ler a profundidade de um buffer enquanto desenha no outro viraria um laço de realimentação (tela preta).
    this.composer.renderTarget2.depthTexture = new THREE.DepthTexture(1, 1);
    this.composer.addPass(new RenderPass(cena, camera));
    this.dof = new ProfundidadeDeCampo(camera);
    this.composer.addPass(this.dof);
    this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.35, 0.45, 2.6); // só o sol e as lâmpadas
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
    this.grade = new ShaderPass(GradeDeCor);
    this.composer.addPass(this.grade);
  }

  redimensionar(l: number, a: number, pixelRatio: number) {
    this.composer.setPixelRatio(pixelRatio);
    this.composer.setSize(l, a);
    this.bloom.resolution.set((l * pixelRatio) / 2, (a * pixelRatio) / 2); // bloom em meia resolução
  }
}
