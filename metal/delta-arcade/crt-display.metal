#pragma clang diagnostic ignored "-Wmissing-prototypes"

#include <metal_stdlib>
#include <simd/simd.h>

using namespace metal;

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
        float4 _1465 = stateAt(param, gcu, previousPassTexture, previousPassTextureSmplr);
        acc += _1465.xyz;
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
            float4 _1503 = stateAt(param, gcu, previousPassTexture, previousPassTextureSmplr);
            acc += _1503.xyz;
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
    float3 _1954;
    if (t >= 0.0)
    {
        _1954 = mix(float3(1.0), float3(0.882000029087066650390625, 0.954999983310699462890625, 1.17999994754791259765625), float3(t));
    }
    else
    {
        _1954 = mix(float3(1.0), float3(1.1150000095367431640625, 1.0099999904632568359375, 0.8450000286102294921875), float3(-t));
    }
    float3 gains = _1954;
    return c * gains;
}

static inline __attribute__((always_inline))
float3 maskWeight(thread const float2& fragCoord, constant GhostCrtUniforms& gcu)
{
    float triadPx = gcu.iResolution.x / float(int(gcu.crt_mask_triads));
    float dark = 1.0 - gcu.crt_mask_strength;
    float rowH = triadPx * 0.865999996662139892578125;
    float row = floor(fragCoord.y / rowH);
    float xoff = mod(row, 2.0) * 0.5;
    float2 cell = float2((fragCoord.x / triadPx) + xoff, fragCoord.y / rowH);
    float2 f = fract(cell);
    float ph = f.x * 3.0;
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
    float dotShape = smoothstep(0.5, 0.319999992847442626953125, abs(f.y - 0.5));
    m = mix(float3(dark * 0.85000002384185791015625), m, float3(dotShape));
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
float vHoldRoll(thread float& y, thread const float& extraRoll, constant GhostCrtUniforms& gcu)
{
    float beat = gcu.crt_v_hold;
    float phase = extraRoll;
    float u = beat / 0.1500000059604644775390625;
    if (abs(u) <= 1.0)
    {
        phase += (0.5 * u);
    }
    else
    {
        float slip = 0.1500000059604644775390625 * sqrt((u * u) - 1.0);
        float t = gcu.iTime * slip;
        float crawl = t + (0.2199999988079071044921875 * sin((t * 2.0) * 3.1415927410125732421875));
        phase += (sign(u) * (0.5 + fract(crawl)));
    }
    if (phase == 0.0)
    {
        return 1.0;
    }
    y = fract(y - phase);
    float d = fast::min(abs(y - 1.0), y);
    float bar = smoothstep(0.0, 0.07500000298023223876953125, d);
    return mix(0.0500000007450580596923828125, 1.0, bar);
}

static inline __attribute__((always_inline))
float hHoldTear(thread float& x, thread const float& y, constant GhostCrtUniforms& gcu)
{
    float df = gcu.crt_h_hold;
    if (df == 0.0)
    {
        return 1.0;
    }
    float u = df / 45.0;
    float shift;
    float shear;
    if (abs(u) <= 1.0)
    {
        shift = 0.5 * u;
        shear = 0.0;
    }
    else
    {
        float slip = 45.0 * sqrt((u * u) - 1.0);
        shear = slip / 15734.0;
        shift = (sign(u) * 0.5) + fract((gcu.iTime * slip) * 0.0199999995529651641845703125);
    }
    shift = fract(shift + ((y * float(int(gcu.crt_scan_lines))) * shear));
    x = fract(x - shift);
    float d = fast::min(abs(x - 1.0), x);
    float bar = smoothstep(0.0, (0.17000000178813934326171875 * fast::min(abs(df) / 60.0, 1.0)) + 0.001000000047497451305389404296875, d);
    return mix(0.0599999986588954925537109375, 1.0, bar);
}

static inline __attribute__((always_inline))
float3 contentAt(thread const float2& uv, thread float& g_shiftY, constant GhostCrtUniforms& gcu, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float2 param = float2(uv.x, uv.y - g_shiftY);
    float4 _846 = stateAt(param, gcu, previousPassTexture, previousPassTextureSmplr);
    return _846.xyz;
}

static inline __attribute__((always_inline))
float3 scanSample(thread const float2& cuv, thread const float& focusMul, thread const float& cornerSoft, thread float& g_shiftY, thread float& g_ilOffset, constant GhostCrtUniforms& gcu, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float2 res = gcu.iResolution.xy;
    float lines = float(int(gcu.crt_scan_lines));
    float srcY = (cuv.y * lines) - 0.5;
    srcY += g_ilOffset;
    float y0 = floor(srcY);
    float fy = srcY - y0;
    float aspect = res.x / res.y;
    float sigmaX = (res.x / (gcu.crt_h_bandwidth * aspect)) * 0.449999988079071044921875;
    sigmaX = fast::max((sigmaX * focusMul) * cornerSoft, 0.2800000011920928955078125);
    float pxU = 1.0 / res.x;
    float convPx = gcu.crt_misconvergence * cornerSoft;
    float dR = (-convPx) * pxU;
    float dB = convPx * pxU;
    float3 acc = float3(0.0);
    float wsum = 0.0;
    for (int line = 0; line < 2; line++)
    {
        float ly = y0 + float(line);
        float lineV = (ly + 0.5) / lines;
        float edgeFade = smoothstep(-0.039999999105930328369140625, 0.039999999105930328369140625, lineV) * smoothstep(1.03999996185302734375, 0.959999978542327880859375, lineV);
        if (edgeFade < 0.001000000047497451305389404296875)
        {
            continue;
        }
        float dy = srcY - ly;
        float2 param = float2(cuv.x, lineV);
        float3 peek = contentAt(param, g_shiftY, gcu, previousPassTexture, previousPassTextureSmplr);
        float lum = fast::clamp(dot(peek, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625)), 0.0, 1.5);
        float sigma = ((gcu.crt_scan_min_width * (1.0 + ((gcu.crt_scan_bloom * 1.39999997615814208984375) * powr(lum, 0.62000000476837158203125)))) * focusMul) * cornerSoft;
        float wLine = exp(((-0.5) * (dy / sigma)) * (dy / sigma)) / (sigma * 2.5066282749176025390625);
        float3 lineAcc = float3(0.0);
        float3 lineW = float3(9.9999997473787516355514526367188e-05);
        for (int i = -2; i <= 2; i++)
        {
            float dx = float(i);
            float wx = exp(((-0.5) * (dx / sigmaX)) * (dx / sigmaX));
            float2 tuv = float2(cuv.x + (dx * pxU), lineV);
            float2 param_1 = tuv;
            float3 s = contentAt(param_1, g_shiftY, gcu, previousPassTexture, previousPassTextureSmplr);
            float wxR = exp(((-0.5) * ((dx + convPx) / sigmaX)) * ((dx + convPx) / sigmaX));
            float wxB = exp(((-0.5) * ((dx - convPx) / sigmaX)) * ((dx - convPx) / sigmaX));
            lineAcc += float3(s.x * wxR, s.y * wx, s.z * wxB);
            lineW += float3(wxR, wx, wxB);
        }
        acc += ((lineAcc / lineW) * (edgeFade * wLine));
        wsum += (edgeFade * wLine);
    }
    return acc / float3(fast::max(wsum, 9.9999997473787516355514526367188e-05));
}

static inline __attribute__((always_inline))
float3 vectorSample(thread const float2& cuv, thread const float& focusMul, thread const float& cornerSoft, thread float& g_shiftY, constant GhostCrtUniforms& gcu, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float2 res = gcu.iResolution.xy;
    float2 px = float2(1.0) / res;
    float sigmaPx = fast::max(((gcu.crt_scan_min_width * 1.7999999523162841796875) * focusMul) * cornerSoft, 0.550000011920928955078125);
    float3 acc = float3(0.0);
    float wsum = 0.0;
    for (int y = -2; y <= 2; y++)
    {
        for (int x = -2; x <= 2; x++)
        {
            float2 d = float2(float(x), float(y));
            float w = exp(((-0.5) * dot(d, d)) / (sigmaPx * sigmaPx));
            float2 param = cuv + (d * px);
            acc += (contentAt(param, g_shiftY, gcu, previousPassTexture, previousPassTextureSmplr) * w);
            wsum += w;
        }
    }
    return acc / float3(fast::max(wsum, 9.9999997473787516355514526367188e-05));
}

static inline __attribute__((always_inline))
float linePulse(thread const float& d, thread const float& width)
{
    return exp(((-0.5) * (d / width)) * (d / width));
}

static inline __attribute__((always_inline))
float angleDelta(thread const float& a, thread const float& b)
{
    return abs(precise::atan2(sin(a - b), cos(a - b)));
}

static inline __attribute__((always_inline))
float3 radarInstrumentLight(thread const float2& cuv, thread const float2& pFace, constant GhostCrtUniforms& gcu)
{
    bool _1221 = gcu.crt_radar_overlay <= 0.0;
    bool _1228;
    if (_1221)
    {
        _1228 = gcu.crt_radar_sweep <= 0.0;
    }
    else
    {
        _1228 = _1221;
    }
    if (_1228)
    {
        return float3(0.0);
    }
    float aspect = gcu.iResolution.x / gcu.iResolution.y;
    float2 p = float2(pFace.x * aspect, pFace.y);
    float r = length(p);
    float a = precise::atan2(p.y, p.x);
    float edge = 1.0 - smoothstep(0.959999978542327880859375, 1.019999980926513671875, r);
    float ring = 0.0;
    for (int i = 1; i <= 4; i++)
    {
        float param = abs(r - (float(i) * 0.20000000298023223876953125));
        float param_1 = 0.002799999900162220001220703125;
        ring = fast::max(ring, linePulse(param, param_1));
    }
    float param_2 = abs(p.x);
    float param_3 = 0.002199999988079071044921875;
    float param_4 = abs(p.y);
    float param_5 = 0.002199999988079071044921875;
    float _cross = fast::max(linePulse(param_2, param_3), linePulse(param_4, param_5)) * smoothstep(0.980000019073486328125, 0.86000001430511474609375, r);
    float tick = 0.0;
    for (int i_1 = 0; i_1 < 12; i_1++)
    {
        float ta = (-3.1415927410125732421875) + ((float(i_1) * 3.1415927410125732421875) / 6.0);
        float param_6 = a;
        float param_7 = ta;
        float ad = angleDelta(param_6, param_7);
        float radial = smoothstep(0.980000019073486328125, 0.920000016689300537109375, r) * smoothstep(0.7799999713897705078125, 0.87999999523162841796875, r);
        float param_8 = ad * fast::max(r, 0.100000001490116119384765625);
        float param_9 = 0.0035000001080334186553955078125;
        tick = fast::max(tick, linePulse(param_8, param_9) * radial);
    }
    float param_10 = r;
    float param_11 = 0.017999999225139617919921875;
    float center = linePulse(param_10, param_11);
    float grid = (fast::clamp((((ring * 0.550000011920928955078125) + (_cross * 0.3499999940395355224609375)) + (tick * 0.800000011920928955078125)) + (center * 0.3499999940395355224609375), 0.0, 1.0) * gcu.crt_radar_overlay) * edge;
    float rpm = fast::max(gcu.crt_radar_sweep_rate, 0.100000001490116119384765625);
    float sweepA = (-1.57079637050628662109375) + ((gcu.iTime * rpm) * 0.10471975803375244140625);
    float param_12 = a;
    float param_13 = sweepA;
    float da = angleDelta(param_12, param_13);
    float param_14 = da * fast::max(r, 0.0500000007450580596923828125);
    float param_15 = 0.00999999977648258209228515625;
    float sweepLine = (linePulse(param_14, param_15) * smoothstep(0.02999999932944774627685546875, 0.100000001490116119384765625, r)) * smoothstep(1.019999980926513671875, 0.920000016689300537109375, r);
    float sweepBloom = ((exp((-da) * 14.0) * smoothstep(0.02999999932944774627685546875, 0.119999997317790985107421875, r)) * smoothstep(1.0, 0.7799999713897705078125, r)) * 0.2199999988079071044921875;
    float sweep = ((sweepLine + sweepBloom) * gcu.crt_radar_sweep) * edge;
    return float3(grid + sweep, (grid * 0.75) + (sweep * 0.4000000059604644775390625), grid * 0.25);
}

static inline __attribute__((always_inline))
float3 glassGlow(thread const float2& cuv, thread float& g_shiftY, constant GhostCrtUniforms& gcu, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    bool _1649 = gcu.crt_halation <= 0.0;
    bool _1656;
    if (_1649)
    {
        _1656 = gcu.crt_diffusion <= 0.0;
    }
    else
    {
        _1656 = _1649;
    }
    if (_1656)
    {
        return float3(0.0);
    }
    float2 res = gcu.iResolution.xy;
    float3 tight = float3(0.0);
    float3 wide = float3(0.0);
    float2 param = (cuv * res) + float2(fract(gcu.iTime * 13.0) * 289.0, fract(gcu.iTime * 7.0) * 331.0);
    float rot = hash12(param) * 6.283185482025146484375;
    for (int i = 0; i < 12; i++)
    {
        float a = (float(i) * 2.399960041046142578125) + rot;
        float r = sqrt((float(i) + 0.5) / 12.0);
        float2 d = float2(cos(a), sin(a)) * r;
        float2 param_1 = cuv + ((d * (0.01200000010430812835693359375 * res.y)) / res);
        float3 sT = contentAt(param_1, g_shiftY, gcu, previousPassTexture, previousPassTextureSmplr);
        float2 param_2 = cuv + ((d * (0.054999999701976776123046875 * res.y)) / res);
        float3 sW = contentAt(param_2, g_shiftY, gcu, previousPassTexture, previousPassTextureSmplr);
        tight += sT;
        wide += sW;
    }
    tight /= float3(12.0);
    wide /= float3(12.0);
    float wLum = dot(wide, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625));
    float3 halo = mix(wide, float3(wLum), float3(0.60000002384185791015625));
    return (tight * gcu.crt_diffusion) + (halo * gcu.crt_halation);
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
float damperWires(thread const float& v)
{
    return 1.0;
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
    float2 p = ((fragCoord / res) * 2.0) - float2(1.0);
    float2 pFace = p;
    float2 param_10 = p;
    PowerEnv param_11 = env;
    float param_12 = apl;
    float param_13 = dgWobble;
    float2 _2156 = warpToContent(param_10, param_11, param_12, param_13, gcu);
    float2 cuv = _2156;
    if (gcu.crt_emi_wobble > 0.0)
    {
        cuv.x += (((gcu.crt_emi_wobble * 0.00120000005699694156646728515625) * sin((cuv.y * 19.0) + (gcu.iTime * 61.700000762939453125))) * (0.60000002384185791015625 + (0.4000000059604644775390625 * sin(gcu.iTime * 0.730000019073486328125))));
    }
    float param_14 = cuv.y;
    float param_15 = env.roll;
    float _2197 = vHoldRoll(param_14, param_15, gcu);
    cuv.y = param_14;
    float vbiShade = _2197;
    float param_16 = cuv.x;
    float param_17 = cuv.y;
    float _2208 = hHoldTear(param_16, param_17, gcu);
    cuv.x = param_16;
    float syncShade = vbiShade * _2208;
    bool _2214 = cuv.x < 0.0;
    bool _2221;
    if (!_2214)
    {
        _2221 = cuv.x > 1.0;
    }
    else
    {
        _2221 = _2214;
    }
    bool _2228;
    if (!_2221)
    {
        _2228 = cuv.y < 0.0;
    }
    else
    {
        _2228 = _2221;
    }
    bool _2235;
    if (!_2228)
    {
        _2235 = cuv.y > 1.0;
    }
    else
    {
        _2235 = _2228;
    }
    if (_2235)
    {
        fragColor = float4(float3(0.0035000001080334186553955078125 * (1.0 - gcu.crt_glass_tint)), 1.0);
        return;
    }
    float rEdge = length(pFace);
    float cornerSoft = 1.0 + (0.5 * smoothstep(0.550000011920928955078125, 1.25, rEdge));
    float focusMul = gcu.crt_focus * env.focusMul;
    g_aspect = res.x / res.y;
    float2 param_18 = cuv;
    float param_19 = focusMul;
    float param_20 = cornerSoft;
    float3 light = scanSample(param_18, param_19, param_20, g_shiftY, g_ilOffset, gcu, previousPassTexture, previousPassTextureSmplr);
    if (gcu.crt_vector_trace > 0.0)
    {
        float2 param_21 = cuv;
        float param_22 = focusMul;
        float param_23 = cornerSoft;
        light = mix(light, vectorSample(param_21, param_22, param_23, g_shiftY, gcu, previousPassTexture, previousPassTextureSmplr), float3(fast::clamp(gcu.crt_vector_trace, 0.0, 1.0)));
    }
    float2 param_24 = cuv;
    float2 param_25 = pFace;
    light += (radarInstrumentLight(param_24, param_25, gcu) * env.bright);
    if (dgWobble > 0.0030000000260770320892333984375)
    {
        float2 sw = float2((dgWobble * 0.0040000001899898052215576171875) * sin((gcu.iTime * 53.0) + (cuv.y * 9.0)), 0.0);
        float2 param_26 = cuv + sw;
        float4 _2330 = stateAt(param_26, gcu, previousPassTexture, previousPassTextureSmplr);
        light.x = mix(light.x, _2330.x, 0.60000002384185791015625);
        float2 param_27 = cuv - sw;
        float4 _2340 = stateAt(param_27, gcu, previousPassTexture, previousPassTextureSmplr);
        light.z = mix(light.z, _2340.z, 0.60000002384185791015625);
    }
    float2 param_28 = cuv;
    light += glassGlow(param_28, g_shiftY, gcu, previousPassTexture, previousPassTextureSmplr);
    float g2Lift = fast::max(gcu.crt_g2_screen - 0.550000011920928955078125, 0.0) * 2.2000000476837158203125;
    float retraceAmt = fast::max(g2Lift * 0.100000001490116119384765625, gcu.crt_retrace_lines * 0.14000000059604644775390625);
    if ((g2Lift > 0.0) || (retraceAmt > 0.0))
    {
        float lift = (g2Lift * 0.0500000007450580596923828125) * env.bright;
        float ph = fract((cuv.y * 13.0) + (cuv.x * 1.60000002384185791015625));
        float lines = (smoothstep(0.9700000286102294921875, 1.0, ph) * retraceAmt) * env.bright;
        light += float3(lift + lines);
    }
    light *= (env.bright * syncShade);
    if (gcu.crt_hum_amp > 0.0)
    {
        float bandY = fract(gcu.iTime / gcu.crt_hum_period);
        float d = abs(fract((cuv.y - bandY) + 0.5) - 0.5);
        float band = exp(((-d) * d) / 0.004999999888241291046142578125);
        light *= (1.0 - (gcu.crt_hum_amp * band));
    }
    light *= (1.0 + (gcu.crt_flicker * sin(60.946895599365234375 * gcu.iTime)));
    if (gcu.crt_noise > 0.0)
    {
        float2 param_29 = fragCoord + float2(fract(gcu.iTime * 7.0) * 331.0);
        float n = hash12(param_29);
        light *= (1.0 + ((gcu.crt_noise * 2.0) * (n - 0.5)));
    }
    float2 param_30 = float2(cuv.x, cuv.y - g_shiftY);
    float4 _2493 = stateAt(param_30, gcu, previousPassTexture, previousPassTextureSmplr);
    float dose = _2493.w;
    float2 param_31 = cuv;
    float param_32 = dose;
    light *= burnEfficiency(param_31, param_32, gcu);
    float3 param_33 = light;
    float3 emitted = whitePoint(param_33, gcu);
    float2 param_34 = fragCoord;
    float3 mw = maskWeight(param_34, gcu);
    float lum = fast::clamp(dot(emitted, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625)), 0.0, 1.0);
    mw = mix(mw, float3(1.0), float3(gcu.crt_mask_fade * lum));
    float avgT = mix(1.0, 0.3333333432674407958984375 + (0.666666686534881591796875 * (1.0 - gcu.crt_mask_strength)), 1.0);
    emitted *= (mw * mix(1.0, 1.0 / fast::max(avgT, 0.3400000035762786865234375), gcu.crt_mask_strength * 0.85000002384185791015625));
    float param_35 = fragCoord.y / res.y;
    emitted *= damperWires(param_35);
    emitted *= gcu.crt_glass_tint;
    float bezelShade = 1.0 - (gcu.crt_bezel * smoothstep(0.819999992847442626953125, 1.12000000476837158203125, rEdge));
    emitted *= bezelShade;
    float2 q = abs(pFace) - float2(1.0 - gcu.crt_corner_radius);
    float cornerDist = (length(fast::max(q, float2(0.0))) + fast::min(fast::max(q.x, q.y), 0.0)) - gcu.crt_corner_radius;
    float cornerMask = 1.0 - smoothstep(-0.0040000001899898052215576171875, 0.00200000009499490261077880859375, cornerDist);
    emitted *= cornerMask;
    emitted += float3((0.0035000001080334186553955078125 * (1.0 - gcu.crt_glass_tint)) * cornerMask);
    fragColor = float4(fast::max(emitted, float3(0.0)), 1.0);
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
    float4 _2634 = out.FragColor;
    float3 _2641 = powr(fast::clamp(_2634.xyz, float3(0.0), float3(1.0)), float3(0.4545454680919647216796875));
    out.FragColor.x = _2641.x;
    out.FragColor.y = _2641.y;
    out.FragColor.z = _2641.z;
    out.FragColor.w = 1.0;
    return out;
}

