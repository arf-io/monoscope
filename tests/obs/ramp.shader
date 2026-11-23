// Verification 1: is `previous_output` this filter's OWN previous output?
// If it is, this ramps to white over ~100 frames regardless of the source.
// If it is not self-feedback, the output stays at a constant 0.01.
uniform texture2d previous_output;

float4 mainImage(VertData v_in) : TARGET
{
    float4 prev = previous_output.Sample(textureSampler, v_in.uv);
    return float4(prev.rgb + 0.01, 1.0);
}
