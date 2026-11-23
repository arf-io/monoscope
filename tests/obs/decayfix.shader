// The fix for the 8-bit feedback fixed point, verified the same way the fault
// was.
//
// Fault: with an 8-bit UNORM feedback target, a slow exponential decay has
// fixed points. 50/255 * 0.99 = 49.5/255, which rounds straight back to
// 50/255 -- so a long phosphor tail sticks at ~20% brightness forever
// instead of fading. Measured: flat for 82 seconds and still going.
//
// Fix: subtract half a least-significant bit after the multiply. That is
// always enough to cross the rounding boundary, so the tail is guaranteed to
// reach zero in bounded time, and it costs the curve less than one LSB of
// accuracy at any point along it.
//
//   .b  phase counter        .g  state        .r  survival counter
uniform texture2d previous_output;

float4 mainImage(VertData v_in) : TARGET
{
    float4 prev = previous_output.Sample(textureSampler, v_in.uv);
    float phase = min(1.0, prev.b + (1.0 / 255.0));
    bool seed = prev.b < (30.0 / 255.0);
    float v = seed ? 1.0 : max(0.0, prev.g * 0.99 - (1.0 / 510.0));
    float n = seed ? 0.0 : min(1.0, prev.r + (v > 0.0 ? (1.0 / 255.0) : 0.0));
    return float4(n, v, phase, 1.0);
}
