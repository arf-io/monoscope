// Runtime proof shader for the phosphor-feedback Ghostty fork.
// Each frame adds a small increment to the previous frame's own output
// (iChannel1). If per-pass feedback works, the screen ramps from blue to
// red over ~1-2 seconds. If the pipeline were stateless, it would remain
// stuck at the first increment (near-black blue) forever.
void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord.xy / iResolution.xy;
    float prev = texture(iChannel1, uv).r;
    float v = min(prev + 0.004, 1.0);
    fragColor = vec4(v, v * 0.2, 1.0 - v, 1.0);
}
