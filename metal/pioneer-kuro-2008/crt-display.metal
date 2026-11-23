#pragma clang diagnostic ignored "-Wmissing-prototypes"
#pragma clang diagnostic ignored "-Wmissing-braces"

#include <metal_stdlib>
#include <simd/simd.h>

using namespace metal;

template<typename T, size_t Num>
struct spvUnsafeArray
{
    T elements[Num ? Num : 1];
    
    thread T& operator [] (size_t pos) thread
    {
        return elements[pos];
    }
    constexpr const thread T& operator [] (size_t pos) const thread
    {
        return elements[pos];
    }
    
    device T& operator [] (size_t pos) device
    {
        return elements[pos];
    }
    constexpr const device T& operator [] (size_t pos) const device
    {
        return elements[pos];
    }
    
    constexpr const constant T& operator [] (size_t pos) const constant
    {
        return elements[pos];
    }
    
    threadgroup T& operator [] (size_t pos) threadgroup
    {
        return elements[pos];
    }
    constexpr const threadgroup T& operator [] (size_t pos) const threadgroup
    {
        return elements[pos];
    }
};

// Implementation of the GLSL mod() function, which is slightly different than Metal fmod()
template<typename Tx, typename Ty>
inline Tx mod(Tx x, Ty y)
{
    return x - y * floor(x / y);
}

struct PowerEnv
{
    float hSpan;
    float vSpan;
    float bright;
    float focusMul;
    float sizeMul;
    float roll;
    float skew;
    float black;
};

struct GhostCrtUniforms
{
    float4 iResolution;
    float iTime;
    float iTimeDelta;
    int iFrame;
    float _pad0;
    float crt_brightness;
    float crt_contrast;
    float crt_focus;
    float crt_g2_screen;
    float crt_tint;
    float crt_saturation;
    float crt_color_temp;
    float crt_tube_gamma;
    float crt_geom_mode;
    float crt_curve_radius;
    float crt_corner_radius;
    float crt_bezel;
    float crt_h_size;
    float crt_v_size;
    float crt_h_pos;
    float crt_v_pos;
    float crt_pincushion;
    float crt_trapezoid;
    float crt_parallelogram;
    float crt_rotation;
    float crt_overscan;
    float crt_scan_lines;
    float crt_scan_min_width;
    float crt_scan_bloom;
    float crt_h_bandwidth;
    float crt_interlace;
    float crt_misconvergence;
    float crt_mask_type;
    float crt_mask_triads;
    float crt_mask_strength;
    float crt_mask_fade;
    float crt_damper_wires;
    float crt_phosphor;
    float crt_persistence;
    float crt_trail_tint;
    float crt_cursor_overdrive;
    float crt_era;
    float crt_warmup_time_scale;
    float crt_v_hold;
    float crt_h_hold;
    float crt_hum_amp;
    float crt_hum_period;
    float crt_emi_wobble;
    float crt_hv_breathing;
    float crt_abl;
    float crt_halation;
    float crt_diffusion;
    float crt_glass_tint;
    float crt_noise;
    float crt_retrace_lines;
    float crt_flicker;
    float crt_burnin_rate;
    float crt_burnin_visibility;
    float crt_burnin_vintage;
    float crt_vector_trace;
    float crt_vector_mode;
    float crt_vector_beam_core;
    float crt_vector_beam_halo;
    float crt_vector_dot_gain;
    float crt_vector_edge_threshold;
    float crt_vector_flicker;
    float crt_vector_grain;
    float crt_radar_overlay;
    float crt_radar_sweep;
    float crt_radar_sweep_rate;
    float crt_power_on;
    float crt_power_nonce;
    float crt_degauss_nonce;
    float crt_debug_state;
    float crt_dvst_auto_erase;
    float crt_dvst_hold_dim;
    float crt_dvst_orange_refresh;
    float crt_dvst_write_rate;
    float crt_erase_nonce;
    float crt_post_test;
    float crt_smooth_scroll;
    float crt_smooth_cell_px;
    float crt_rolling_scan;
    float crt_rolling_gain;
    float crt_scan_rate;
    float crt_pdp_dither;
    float crt_pdp_contour;
    float crt_pdp_black_floor;
};

constant spvUnsafeArray<float, 16> _2126 = spvUnsafeArray<float, 16>({ 0.0, 8.0, 2.0, 10.0, 12.0, 4.0, 14.0, 6.0, 3.0, 11.0, 1.0, 9.0, 15.0, 7.0, 13.0, 5.0 });

struct ghostcrtty_crt_display_out
{
    float4 FragColor [[color(0)]];
};

static inline __attribute__((always_inline))
float4 _CRT_SAMPLE(texture2d<float> t, sampler tSmplr, thread const float2& uv)
{
    return t.sample(tSmplr, float2(uv.x, 1.0 - uv.y));
}

static inline __attribute__((always_inline))
float hash12(thread const float2& p)
{
    float3 p3 = fract(p.xyx * 0.103100001811981201171875);
    p3 += float3(dot(p3, p3.yzx + float3(33.3300018310546875)));
    return fract((p3.x + p3.y) * p3.z);
}

static inline __attribute__((always_inline))
PowerEnv powerEnvelope(thread const float& seq, thread const float& warm, thread const float& powerState, thread const float& nonce, constant GhostCrtUniforms& gcu)
{
    PowerEnv e;
    e.hSpan = 1.0;
    e.vSpan = 1.0;
    e.bright = 1.0;
    e.focusMul = 1.0;
    e.sizeMul = 1.0;
    e.roll = 0.0;
    e.skew = 0.0;
    e.black = 0.0;
    float tSettle = fast::max(warm / fast::max((45.0 * gcu.crt_warmup_time_scale) * 6.6700000762939453125, 1.0), 0.0);
    float thermal = 1.0 - (0.25 * exp((-tSettle) * 3.0));
    float2 param = float2(nonce, 11.69999980926513671875);
    float jitter = 0.85000002384185791015625 + (0.300000011920928955078125 * hash12(param));
    if (powerState > 0.5)
    {
        e.bright = smoothstep(0.0500000007450580596923828125, 0.449999988079071044921875, seq) * thermal;
        e.focusMul = mix(1.14999997615814208984375, 1.0, smoothstep(0.0500000007450580596923828125, 2.0, seq));
    }
    else
    {
        e.bright = 1.0 - smoothstep(0.0, 0.119999997317790985107421875, seq);
        e.black = step(0.119999997317790985107421875, seq);
    }
    return e;
}

static inline __attribute__((always_inline))
float4 stateAt(thread float2& uv, constant GhostCrtUniforms& gcu, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float2 res = gcu.iResolution.xy;
    uv.y = fast::max(uv.y, 2.5 / res.y);
    float2 param = uv;
    return _CRT_SAMPLE(previousPassTexture, previousPassTextureSmplr, param);
}

static inline __attribute__((always_inline))
float3 collapseLine(thread const float& u, constant GhostCrtUniforms& gcu, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float3 acc = float3(0.0);
    for (int i = 0; i < 12; i++)
    {
        float2 param = float2(u, (float(i) + 0.5) / 12.0);
        float4 _1209 = stateAt(param, gcu, previousPassTexture, previousPassTextureSmplr);
        acc += _1209.xyz;
    }
    return acc / float3(12.0);
}

static inline __attribute__((always_inline))
float3 collapseAll(constant GhostCrtUniforms& gcu, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float3 acc = float3(0.0);
    for (int y = 0; y < 4; y++)
    {
        for (int x = 0; x < 4; x++)
        {
            float2 param = (float2(float(x), float(y)) + float2(0.5)) / float2(4.0);
            float4 _1248 = stateAt(param, gcu, previousPassTexture, previousPassTextureSmplr);
            acc += _1248.xyz;
        }
    }
    return acc / float3(16.0);
}

static inline __attribute__((always_inline))
float3 collapseLight(thread const float2& pFace, thread const PowerEnv& env, constant GhostCrtUniforms& gcu, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float aspect = gcu.iResolution.x / gcu.iResolution.y;
    float spotV = fast::max(env.vSpan, 0.006000000052154064178466796875) * (1.0 + (0.60000002384185791015625 * (env.focusMul - 1.0)));
    float spotH = fast::max(env.hSpan, 0.006000000052154064178466796875 / aspect);
    float gy = exp(((-0.5) * (pFace.y / spotV)) * (pFace.y / spotV));
    float3 content;
    if (env.hSpan > 0.5)
    {
        float u = fast::clamp((pFace.x * 0.5) + 0.5, 0.0, 1.0);
        float param = u;
        content = collapseLine(param, gcu, previousPassTexture, previousPassTextureSmplr);
    }
    else
    {
        float gx = exp(((-0.5) * (pFace.x / spotH)) * (pFace.x / spotH));
        content = collapseAll(gcu, previousPassTexture, previousPassTextureSmplr);
        gy *= gx;
    }
    float skirt = exp(((-0.5) * (pFace.y / (spotV * 6.0))) * (pFace.y / (spotV * 6.0)));
    if (env.hSpan <= 0.5)
    {
        float sx = exp(((-0.5) * (pFace.x / (spotH * 6.0))) * (pFace.x / (spotH * 6.0)));
        skirt *= sx;
    }
    float3 core = content * env.bright;
    float coreLum = dot(core, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625));
    core = mix(core, float3(coreLum), float3(smoothstep(1.5, 6.0, coreLum) * 0.5));
    return (core * gy) + ((core * skirt) * 0.119999997317790985107421875);
}

static inline __attribute__((always_inline))
float3 whitePoint(thread const float3& c, constant GhostCrtUniforms& gcu)
{
    float t = fast::clamp((gcu.crt_color_temp - 6500.0) / 2800.0, -1.0, 1.0);
    float3 _1802;
    if (t >= 0.0)
    {
        _1802 = mix(float3(1.0), float3(0.882000029087066650390625, 0.954999983310699462890625, 1.17999994754791259765625), float3(t));
    }
    else
    {
        _1802 = mix(float3(1.0), float3(1.1150000095367431640625, 1.0099999904632568359375, 0.8450000286102294921875), float3(-t));
    }
    float3 gains = _1802;
    return c * gains;
}

static inline __attribute__((always_inline))
float3 maskWeight(thread const float2& fragCoord, constant GhostCrtUniforms& gcu)
{
    float triadPx = gcu.iResolution.x / float(int(gcu.crt_mask_triads));
    float dark = 1.0 - gcu.crt_mask_strength;
    float ph = fract(fragCoord.x / triadPx) * 3.0;
    float3 m = float3(dark);
    if (ph < 1.0)
    {
        m.x = 1.0;
    }
    else
    {
        if (ph < 2.0)
        {
            m.y = 1.0;
        }
        else
        {
            m.z = 1.0;
        }
    }
    return m;
}

static inline __attribute__((always_inline))
float2 warpToContent(thread float2& p, thread const PowerEnv& env, thread const float& apl, thread const float& dgWobble, constant GhostCrtUniforms& gcu)
{
    float rc = cos(gcu.crt_rotation);
    float rs = sin(gcu.crt_rotation);
    p = float2x2(float2(rc, -rs), float2(rs, rc)) * p;
    p.x += ((gcu.crt_parallelogram + env.skew) * p.y);
    p.x *= (1.0 + (gcu.crt_trapezoid * p.y));
    p.x *= (1.0 + ((gcu.crt_pincushion * ((p.y * p.y) - 0.5)) * 2.0));
    float breathe = 1.0 + ((gcu.crt_hv_breathing * 0.0599999986588954925537109375) * apl);
    p.x += ((dgWobble * 0.006000000052154064178466796875) * sin(gcu.iTime * 61.0));
    p.y += ((dgWobble * 0.0040000001899898052215576171875) * sin((gcu.iTime * 47.0) + 1.7000000476837158203125));
    float2 span = float2(gcu.crt_h_size * env.hSpan, gcu.crt_v_size * env.vSpan);
    span *= ((breathe * env.sizeMul) * (1.0 + gcu.crt_overscan));
    p /= fast::max(span, float2(9.9999997473787516355514526367188e-05));
    p -= (float2(gcu.crt_h_pos, gcu.crt_v_pos) * 2.0);
    return (p * 0.5) + float2(0.5);
}

static inline __attribute__((always_inline))
float3 pdpMask(thread const float2& fragCoord, thread const float3& emitted, constant GhostCrtUniforms& gcu)
{
    float cellW = gcu.iResolution.x / float(int(gcu.crt_mask_triads));
    float2 f = fract(fragCoord / float2(fast::max(cellW, 1.0)));
    float hOpen = smoothstep(0.2599999904632568359375, 0.3400000035762786865234375, f.y);
    float sub = fract(f.x * 3.0);
    float vOpen = smoothstep(0.07999999821186065673828125, 0.1599999964237213134765625, sub) * (1.0 - smoothstep(0.839999973773956298828125, 0.920000016689300537109375, sub));
    float ph = floor(f.x * 3.0);
    float3 m = float3(0.0);
    if (ph < 0.5)
    {
        m.x = 1.0;
    }
    else
    {
        if (ph < 1.5)
        {
            m.y = 1.0;
        }
        else
        {
            m.z = 1.0;
        }
    }
    float3 open = (m * hOpen) * vOpen;
    float lum = fast::clamp(dot(emitted, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625)), 0.0, 1.0);
    float strength = gcu.crt_mask_strength * (1.0 - (gcu.crt_mask_fade * lum));
    return mix(float3(1.0), open * 2.0, float3(strength));
}

static inline __attribute__((always_inline))
float burnEfficiency(thread const float2& cuv, thread const float& dose, constant GhostCrtUniforms& gcu)
{
    float wear = smoothstep(0.0, 1.0, dose);
    if (false)
    {
        float rows = 24.0;
        float rowPh = fract(cuv.y * rows);
        float rowGhost = smoothstep(0.1500000059604644775390625, 0.5, rowPh) * smoothstep(0.85000002384185791015625, 0.5, rowPh);
        float rowWeight = (0.3499999940395355224609375 + (0.64999997615814208984375 * step(cuv.y, 1.0 / rows))) + (0.449999988079071044921875 * step(1.0 - (1.0 / rows), cuv.y));
        float margin = smoothstep(0.100000001490116119384765625, 0.0199999995529651641845703125, cuv.x) * 0.5;
        float2 c = cuv - float2(0.5);
        float panel = exp((-dot(c * float2(1.0, 1.39999997615814208984375), c * float2(1.0, 1.39999997615814208984375))) * 2.2000000476837158203125) * 0.4000000059604644775390625;
        float vintage = fast::clamp((((rowGhost * rowWeight) * 0.550000011920928955078125) + margin) + panel, 0.0, 1.0);
        wear = fast::max(wear, (vintage * 0.0) * 0.800000011920928955078125);
    }
    return 1.0 - ((0.3499999940395355224609375 * gcu.crt_burnin_visibility) * wear);
}

static inline __attribute__((always_inline))
void mainImage(thread float4& fragColor, thread const float2& fragCoord, thread int& g_contentMode, thread float& g_seq, thread float& g_aspect, thread float& g_shiftY, thread float& g_ilOffset, constant GhostCrtUniforms& gcu, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float2 res = gcu.iResolution.xy;
    g_contentMode = 0;
    g_seq = 0.0;
    g_aspect = res.x / res.y;
    g_shiftY = 0.0;
    g_ilOffset = 0.0;
    float2 param = float2(0.5) / res;
    float4 sP0 = _CRT_SAMPLE(previousPassTexture, previousPassTextureSmplr, param);
    float2 param_1 = float2(1.5, 0.5) / res;
    float4 sP1 = _CRT_SAMPLE(previousPassTexture, previousPassTextureSmplr, param_1);
    float seqClock = sP0.x;
    float powerNonce = sP0.y;
    float powerState = sP0.w;
    float warmClock = sP1.x;
    float apl = sP1.y;
    float dgClock = sP1.z;
    float dgAuto = 0.0;
    if (powerState > 0.5)
    {
        dgAuto = exp((-seqClock) / 0.449999988079071044921875);
    }
    float dgWobble = fast::max(exp((-dgClock) / 0.449999988079071044921875) * step(dgClock, 2.5), dgAuto);
    float param_2 = seqClock;
    float param_3 = warmClock;
    float param_4 = powerState;
    float param_5 = powerNonce;
    PowerEnv env = powerEnvelope(param_2, param_3, param_4, param_5, gcu);
    if (env.black > 0.5)
    {
        fragColor = float4(float3(0.0035000001080334186553955078125 * (1.0 - gcu.crt_glass_tint)), 1.0);
        return;
    }
    if (env.vSpan < 0.180000007152557373046875)
    {
        float2 pC = ((fragCoord / res) * 2.0) - float2(1.0);
        float2 param_6 = pC;
        PowerEnv param_7 = env;
        float3 lightC = collapseLight(param_6, param_7, gcu, previousPassTexture, previousPassTextureSmplr);
        float3 param_8 = lightC;
        float3 emittedC = whitePoint(param_8, gcu);
        float2 param_9 = fragCoord;
        emittedC *= maskWeight(param_9, gcu);
        emittedC *= gcu.crt_glass_tint;
        float2 qC = abs(pC) - float2(1.0 - gcu.crt_corner_radius);
        float cdC = (length(fast::max(qC, float2(0.0))) + fast::min(fast::max(qC.x, qC.y), 0.0)) - gcu.crt_corner_radius;
        float cmC = 1.0 - smoothstep(-0.0040000001899898052215576171875, 0.00200000009499490261077880859375, cdC);
        emittedC *= cmC;
        emittedC += float3((0.0035000001080334186553955078125 * (1.0 - gcu.crt_glass_tint)) * cmC);
        fragColor = float4(fast::max(emittedC, float3(0.0)), 1.0);
        return;
    }
    float2 pP = ((fragCoord / res) * 2.0) - float2(1.0);
    float2 param_10 = pP;
    PowerEnv param_11 = env;
    float param_12 = apl;
    float param_13 = 0.0;
    float2 _2009 = warpToContent(param_10, param_11, param_12, param_13, gcu);
    float2 cuvP = _2009;
    bool _2012 = cuvP.x < 0.0;
    bool _2019;
    if (!_2012)
    {
        _2019 = cuvP.x > 1.0;
    }
    else
    {
        _2019 = _2012;
    }
    bool _2026;
    if (!_2019)
    {
        _2026 = cuvP.y < 0.0;
    }
    else
    {
        _2026 = _2019;
    }
    bool _2033;
    if (!_2026)
    {
        _2033 = cuvP.y > 1.0;
    }
    else
    {
        _2033 = _2026;
    }
    if (_2033)
    {
        fragColor = float4(0.00200000009499490261077880859375, 0.00200000009499490261077880859375, 0.00200000009499490261077880859375, 1.0);
        return;
    }
    cuvP.y = fast::max(cuvP.y, 2.5 / res.y);
    float2 param_14 = cuvP;
    float4 s = _CRT_SAMPLE(previousPassTexture, previousPassTextureSmplr, param_14);
    float3 lightP = s.xyz;
    float3 floorC = float3(1.0, 0.85000002384185791015625, 0.60000002384185791015625) * gcu.crt_pdp_black_floor;
    lightP = fast::max(lightP, floorC * env.bright);
    if (gcu.crt_pdp_dither > 0.0)
    {
        float lum = dot(lightP, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625));
        if (lum < 0.0500000007450580596923828125)
        {
            float cellW = res.x / float(int(gcu.crt_mask_triads));
            float2 cell = floor(fragCoord / float2(fast::max(cellW, 1.0)));
            int bi = int(mod(cell.x + (mod(float(gcu.iFrame / 2), 2.0) * 2.0), 4.0)) + (4 * int(mod(cell.y + mod(float(gcu.iFrame / 4), 2.0), 4.0)));
            float thresh = (_2126[bi] + 0.5) / 16.0;
            float lsb = 0.008000000379979610443115234375 * gcu.crt_pdp_dither;
            float q = (floor(lum / lsb) + step(thresh, fract(lum / lsb))) * lsb;
            lightP *= (q / fast::max(lum, 9.9999997473787516355514526367188e-06));
        }
    }
    float3 param_15 = lightP;
    float3 emittedP = whitePoint(param_15, gcu) * env.bright;
    float2 param_16 = fragCoord;
    float3 param_17 = emittedP;
    emittedP *= pdpMask(param_16, param_17, gcu);
    float2 param_18 = cuvP;
    float param_19 = s.w;
    emittedP *= burnEfficiency(param_18, param_19, gcu);
    emittedP *= (1.0 + (((gcu.crt_flicker * 2.0) * sin(60.946895599365234375 * gcu.iTime)) * smoothstep(0.1500000059604644775390625, 0.449999988079071044921875, dot(emittedP, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625)))));
    emittedP *= gcu.crt_glass_tint;
    float2 qP = abs(pP) - float2(1.0 - gcu.crt_corner_radius);
    float cdP = (length(fast::max(qP, float2(0.0))) + fast::min(fast::max(qP.x, qP.y), 0.0)) - gcu.crt_corner_radius;
    float cmP = 1.0 - smoothstep(-0.0040000001899898052215576171875, 0.00200000009499490261077880859375, cdP);
    emittedP *= (cmP * (1.0 - (gcu.crt_bezel * smoothstep(0.85000002384185791015625, 1.12000000476837158203125, length(pP)))));
    fragColor = float4(fast::max(emittedP, float3(0.0)), 1.0);
}

fragment ghostcrtty_crt_display_out ghostcrtty_crt_display(constant GhostCrtUniforms& gcu [[buffer(0)]], texture2d<float> previousPassTexture [[texture(2)]], sampler previousPassTextureSmplr [[sampler(2)]], float4 gl_FragCoord [[position]])
{
    ghostcrtty_crt_display_out out = {};
    int g_contentMode = 0;
    float g_seq = 0.0;
    float g_aspect = 1.33000004291534423828125;
    float g_shiftY = 0.0;
    float g_ilOffset = 0.0;
    float2 _crtFragCoord = float2(gl_FragCoord.x, gcu.iResolution.y - gl_FragCoord.y);
    float2 param_1 = _crtFragCoord;
    float4 param;
    mainImage(param, param_1, g_contentMode, g_seq, g_aspect, g_shiftY, g_ilOffset, gcu, previousPassTexture, previousPassTextureSmplr);
    out.FragColor = param;
    float4 _2742 = out.FragColor;
    float3 _2749 = powr(fast::clamp(_2742.xyz, float3(0.0), float3(1.0)), float3(0.4545454680919647216796875));
    out.FragColor.x = _2749.x;
    out.FragColor.y = _2749.y;
    out.FragColor.z = _2749.z;
    out.FragColor.w = 1.0;
    return out;
}

