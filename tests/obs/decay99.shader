// The case that decides whether long phosphors are usable in OBS.
//
// A P7 radar tail or a Tektronix storage tube does not halve per frame -- it
// decays by a whisker each frame over seconds. In 8-bit UNORM with
// round-to-nearest, 0.99 * (1/255) rounds straight back to 1/255: the tail
// STICKS at one LSB and never reaches black, leaving a permanent smear. In
// fp16 it keeps going.
//
//   .b  phase counter, one LSB per frame
//   .g  state: held at 1.0 for 30 frames, then multiplied by 0.99 per frame
//   .r  survival counter: one LSB per frame the state is still non-zero
uniform texture2d previous_output;

float4 mainImage(VertData v_in) : TARGET
{
    float4 prev = previous_output.Sample(textureSampler, v_in.uv);
    float phase = min(1.0, prev.b + (1.0 / 255.0));
    bool seed = prev.b < (30.0 / 255.0);
    float v = seed ? 1.0 : prev.g * 0.99;
    float n = seed ? 0.0 : min(1.0, prev.r + (v > 0.0 ? (1.0 / 255.0) : 0.0));
    return float4(n, v, phase, 1.0);
}
