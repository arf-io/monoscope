#pragma clang diagnostic ignored "-Wmissing-prototypes"

#include <metal_stdlib>
#include <simd/simd.h>

using namespace metal;

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
        float tHeater = (8.0 * gcu.crt_warmup_time_scale) * jitter;
        float tDot = tHeater + (0.449999988079071044921875 * jitter);
        float tLine = tDot + (0.699999988079071044921875 * jitter);
        float tUnfold = tLine + (2.599999904632568359375 * jitter);
        if (seq < tHeater)
        {
            e.black = 1.0;
        }
        else
        {
            if (seq < tDot)
            {
                float k = (seq - tHeater) / (tDot - tHeater);
                e.hSpan = 0.01200000010430812835693359375;
                e.vSpan = 0.01200000010430812835693359375;
                e.bright = 6.0 * k;
                e.focusMul = 2.5;
            }
            else
            {
                if (seq < tLine)
                {
                    float k_1 = (seq - tDot) / (tLine - tDot);
                    k_1 = 1.0 - ((1.0 - k_1) * (1.0 - k_1));
                    e.hSpan = mix(0.01200000010430812835693359375, 1.0, k_1);
                    e.vSpan = 0.01200000010430812835693359375;
                    e.bright = mix(6.0, 3.5, k_1);
                    e.focusMul = mix(1.39999997615814208984375, 1.14999997615814208984375, k_1);
                }
                else
                {
                    if (seq < tUnfold)
                    {
                        float k_2 = (seq - tLine) / (tUnfold - tLine);
                        k_2 = 1.0 - powr(1.0 - k_2, 2.2000000476837158203125);
                        e.vSpan = mix(0.01200000010430812835693359375, 1.0, k_2);
                        e.bright = mix(3.5, 1.0, k_2);
                        e.focusMul = mix(1.7999999523162841796875, 1.14999997615814208984375, k_2);
                        float lockK = 1.0 - k_2;
                        e.roll = (lockK * lockK) * fract(seq * mix(4.0, 0.20000000298023223876953125, k_2));
                        e.skew = 0.0599999986588954925537109375 * lockK;
                    }
                    else
                    {
                        e.focusMul = mix(1.14999997615814208984375, 1.0, fast::min((seq - tUnfold) / ((25.0 * gcu.crt_warmup_time_scale) * 6.6700000762939453125), 1.0));
                    }
                }
            }
        }
        e.bright *= mix(0.0, thermal, smoothstep(tHeater, tDot, seq));
    }
    else
    {
        float tLine_1 = 0.20000000298023223876953125 * jitter;
        float tDot_1 = 0.550000011920928955078125 * jitter;
        float tGone = 5.0 * jitter;
        if (seq < tLine_1)
        {
            float k_3 = seq / tLine_1;
            k_3 *= k_3;
            e.vSpan = mix(1.0, 0.00999999977648258209228515625, k_3);
            e.bright = fast::min(1.0 / fast::max(e.vSpan, 0.0199999995529651641845703125), 9.0) * 0.550000011920928955078125;
            e.focusMul = 1.2999999523162841796875;
        }
        else
        {
            if (seq < tDot_1)
            {
                float k_4 = (seq - tLine_1) / (tDot_1 - tLine_1);
                k_4 *= k_4;
                e.vSpan = 0.00999999977648258209228515625;
                e.hSpan = mix(1.0, 0.01200000010430812835693359375, k_4);
                e.bright = fast::min(9.0, mix(9.0, 14.0, k_4)) * 0.550000011920928955078125;
                e.focusMul = 1.60000002384185791015625;
            }
            else
            {
                if (seq < tGone)
                {
                    float k_5 = (seq - tDot_1) / (tGone - tDot_1);
                    e.vSpan = 0.00999999977648258209228515625;
                    e.hSpan = 0.01200000010430812835693359375;
                    e.bright = 7.69999980926513671875 * exp((-k_5) * 5.5);
                    e.focusMul = 1.89999997615814208984375;
                    e.roll = 0.0040000001899898052215576171875 * k_5;
                }
                else
                {
                    e.black = 1.0;
                }
            }
        }
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
        float4 _1458 = stateAt(param, gcu, previousPassTexture, previousPassTextureSmplr);
        acc += _1458.xyz;
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
            float4 _1496 = stateAt(param, gcu, previousPassTexture, previousPassTextureSmplr);
            acc += _1496.xyz;
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
float2 warpToContent(thread float2& p, thread const PowerEnv& env, thread const float& apl, thread const float& dgWobble, constant GhostCrtUniforms& gcu)
{
    float rc = cos(gcu.crt_rotation);
    float rs = sin(gcu.crt_rotation);
    p = float2x2(float2(rc, -rs), float2(rs, rc)) * p;
    p.x += ((gcu.crt_parallelogram + env.skew) * p.y);
    p.x *= (1.0 + (gcu.crt_trapezoid * p.y));
    float w = 1.0 / fast::max(gcu.crt_curve_radius, 1.0);
    float wx = 0.180000007152557373046875 * w;
    float wy = 0.23999999463558197021484375 * w;
    p *= float2(1.0 + ((wx * p.y) * p.y), 1.0 + ((wy * p.x) * p.x));
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
float burnEfficiency(thread const float2& cuv, thread const float& dose, constant GhostCrtUniforms& gcu)
{
    float wear = smoothstep(0.0, 1.0, dose);
    if (true)
    {
        float rows = 24.0;
        float rowPh = fract(cuv.y * rows);
        float rowGhost = smoothstep(0.1500000059604644775390625, 0.5, rowPh) * smoothstep(0.85000002384185791015625, 0.5, rowPh);
        float rowWeight = (0.3499999940395355224609375 + (0.64999997615814208984375 * step(cuv.y, 1.0 / rows))) + (0.449999988079071044921875 * step(1.0 - (1.0 / rows), cuv.y));
        float margin = smoothstep(0.100000001490116119384765625, 0.0199999995529651641845703125, cuv.x) * 0.5;
        float2 c = cuv - float2(0.5);
        float panel = exp((-dot(c * float2(1.0, 1.39999997615814208984375), c * float2(1.0, 1.39999997615814208984375))) * 2.2000000476837158203125) * 0.4000000059604644775390625;
        float vintage = fast::clamp((((rowGhost * rowWeight) * 0.550000011920928955078125) + margin) + panel, 0.0, 1.0);
        wear = fast::max(wear, (vintage * 0.180000007152557373046875) * 0.800000011920928955078125);
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
        float3 emittedC = (float3(0.874000012874603271484375, 0.913999974727630615234375, 1.0) * lightC.x) + ((float3(dot(lightC, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625))) * smoothstep(2.0, 8.0, dot(lightC, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625)))) * 0.300000011920928955078125);
        emittedC *= gcu.crt_glass_tint;
        float2 qC = abs(pC) - float2(1.0 - gcu.crt_corner_radius);
        float cdC = (length(fast::max(qC, float2(0.0))) + fast::min(fast::max(qC.x, qC.y), 0.0)) - gcu.crt_corner_radius;
        float cmC = 1.0 - smoothstep(-0.0040000001899898052215576171875, 0.00200000009499490261077880859375, cdC);
        emittedC *= cmC;
        emittedC += float3((0.0035000001080334186553955078125 * (1.0 - gcu.crt_glass_tint)) * cmC);
        fragColor = float4(fast::max(emittedC, float3(0.0)), 1.0);
        return;
    }
    float2 pV = ((fragCoord / res) * 2.0) - float2(1.0);
    float2 param_8 = pV;
    PowerEnv param_9 = env;
    float param_10 = apl;
    float param_11 = dgWobble;
    float2 _2035 = warpToContent(param_8, param_9, param_10, param_11, gcu);
    float2 cuvV = _2035;
    if (gcu.crt_emi_wobble > 0.0)
    {
        cuvV.x += (((gcu.crt_emi_wobble * 0.00120000005699694156646728515625) * sin((cuvV.y * 19.0) + (gcu.iTime * 61.700000762939453125))) * (0.60000002384185791015625 + (0.4000000059604644775390625 * sin(gcu.iTime * 0.730000019073486328125))));
    }
    bool _2071 = cuvV.x < 0.0;
    bool _2078;
    if (!_2071)
    {
        _2078 = cuvV.x > 1.0;
    }
    else
    {
        _2078 = _2071;
    }
    bool _2085;
    if (!_2078)
    {
        _2085 = cuvV.y < 0.0;
    }
    else
    {
        _2085 = _2078;
    }
    bool _2092;
    if (!_2085)
    {
        _2092 = cuvV.y > 1.0;
    }
    else
    {
        _2092 = _2085;
    }
    if (_2092)
    {
        fragColor = float4(float3(0.0035000001080334186553955078125 * (1.0 - gcu.crt_glass_tint)), 1.0);
        return;
    }
    cuvV.y = fast::max(cuvV.y, 2.5 / res.y);
    float rEdgeV = length(pV);
    float cornerSoftV = 1.0 + (0.5 * smoothstep(0.550000011920928955078125, 1.25, rEdgeV));
    float focusMulV = gcu.crt_focus * env.focusMul;
    float2 pxV = float2(1.0) / res;
    float coreSig = fast::max((gcu.crt_vector_beam_core * focusMulV) * cornerSoftV, 0.449999988079071044921875);
    float3 core = float3(0.0);
    float coreG = 0.0;
    float wc = 0.0;
    for (int y = -2; y <= 2; y++)
    {
        for (int x = -2; x <= 2; x++)
        {
            float2 d = float2(float(x), float(y));
            float w = exp(((-0.5) * dot(d, d)) / (coreSig * coreSig));
            float2 param_12 = cuvV + (d * pxV);
            float4 _2182 = stateAt(param_12, gcu, previousPassTexture, previousPassTextureSmplr);
            float4 s = _2182;
            core += (s.xyz * w);
            coreG += (s.y * w);
            wc += w;
        }
    }
    core /= float3(fast::max(wc, 9.9999997473787516355514526367188e-05));
    coreG /= fast::max(wc, 9.9999997473787516355514526367188e-05);
    float2 param_13 = cuvV;
    float4 _2214 = stateAt(param_13, gcu, previousPassTexture, previousPassTextureSmplr);
    float doseV = _2214.w;
    float3 halo = float3(0.0);
    float haloW = 0.0;
    float2 param_14 = fragCoord + float2(fract(gcu.iTime * 13.0) * 289.0, fract(gcu.iTime * 7.0) * 331.0);
    float hseed = hash12(param_14);
    for (int r = 0; r < 3; r++)
    {
        for (int s_1 = 0; s_1 < 12; s_1++)
        {
            float j1 = fract((hseed + (float(r) * 0.61803400516510009765625)) + (float(s_1) * 0.38196599483489990234375));
            float j2 = fract(((hseed * 1.61802995204925537109375) + (float(s_1) * 0.754877984523773193359375)) + (float(r) * 0.24697999656200408935546875));
            float rr = (float(r) + j2) / 3.0;
            float rad = (rr * 0.02999999932944774627685546875) * res.y;
            float a = (float(s_1) + j1) * 0.52359879016876220703125;
            float wgt = exp(((-2.0) * rr) * rr);
            float2 d_1 = (float2(cos(a), sin(a)) * rad) / res;
            float2 param_15 = cuvV + d_1;
            float4 _2318 = stateAt(param_15, gcu, previousPassTexture, previousPassTextureSmplr);
            halo += (_2318.xyz * wgt);
            haloW += wgt;
        }
    }
    halo /= float3(fast::max(haloW, 9.9999997473787516355514526367188e-05));
    float eV = core.x + (halo.x * gcu.crt_vector_beam_halo);
    float3 emittedV = float3(0.874000012874603271484375, 0.913999974727630615234375, 1.0) * eV;
    emittedV = mix(emittedV, float3(eV), float3(smoothstep(0.89999997615814208984375, 1.60000002384185791015625, core.x) * 0.60000002384185791015625));
    float dwellDot = coreG * gcu.crt_vector_dot_gain;
    emittedV += (float3(0.936999976634979248046875, 0.9570000171661376953125, 1.0) * dwellDot);
    emittedV *= (1.0 + ((gcu.crt_vector_flicker * (0.4000000059604644775390625 + (1.60000002384185791015625 * apl))) * sin(60.946895599365234375 * gcu.iTime)));
    if (gcu.crt_noise > 0.0)
    {
        float2 param_16 = fragCoord + float2(fract(gcu.iTime * 7.0) * 331.0);
        float n = hash12(param_16);
        emittedV *= (1.0 + ((gcu.crt_noise * 2.0) * (n - 0.5)));
    }
    emittedV *= env.bright;
    float2 param_17 = cuvV;
    float param_18 = doseV;
    emittedV *= burnEfficiency(param_17, param_18, gcu);
    emittedV *= gcu.crt_glass_tint;
    emittedV *= (1.0 - (gcu.crt_bezel * smoothstep(0.819999992847442626953125, 1.12000000476837158203125, rEdgeV)));
    float2 qV = abs(pV) - float2(1.0 - gcu.crt_corner_radius);
    float cdV = (length(fast::max(qV, float2(0.0))) + fast::min(fast::max(qV.x, qV.y), 0.0)) - gcu.crt_corner_radius;
    float cmV = 1.0 - smoothstep(-0.0040000001899898052215576171875, 0.00200000009499490261077880859375, cdV);
    emittedV *= cmV;
    emittedV += float3((0.0035000001080334186553955078125 * (1.0 - gcu.crt_glass_tint)) * cmV);
    fragColor = float4(fast::max(emittedV, float3(0.0)), 1.0);
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
    float4 _2906 = out.FragColor;
    float3 _2913 = powr(fast::clamp(_2906.xyz, float3(0.0), float3(1.0)), float3(0.4545454680919647216796875));
    out.FragColor.x = _2913.x;
    out.FragColor.y = _2913.y;
    out.FragColor.z = _2913.z;
    out.FragColor.w = 1.0;
    return out;
}

