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
PowerEnv powerEnvelope(thread const float& seq, thread const float& warm, thread const float& powerState, constant GhostCrtUniforms& u_1)
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
    float tSettle = fast::max(warm / fast::max((45.0 * u_1.crt_warmup_time_scale) * 6.6700000762939453125, 1.0), 0.0);
    float thermal = 1.0 - (0.25 * exp((-tSettle) * 3.0));
    if (powerState > 0.5)
    {
        float tLight = 6.0 * u_1.crt_warmup_time_scale;
        float tFade = tLight + ((3.5 * u_1.crt_warmup_time_scale) * 6.6700000762939453125);
        if (seq < tLight)
        {
            e.black = 1.0;
        }
        else
        {
            float k = smoothstep(tLight, tFade, seq);
            e.bright = k * thermal;
            e.focusMul = mix(1.60000002384185791015625, 1.0, k);
            e.sizeMul = mix(1.01800000667572021484375, 1.0, smoothstep(tLight, tFade + ((8.0 * u_1.crt_warmup_time_scale) * 6.6700000762939453125), seq));
        }
    }
    else
    {
        float tLine = 0.20000000298023223876953125;
        float tDot = 0.550000011920928955078125;
        float tGone = 5.0;
        if (seq < tLine)
        {
            float k_1 = seq / tLine;
            k_1 *= k_1;
            e.vSpan = mix(1.0, 0.00999999977648258209228515625, k_1);
            e.bright = fast::min(1.0 / fast::max(e.vSpan, 0.0199999995529651641845703125), 9.0) * 0.550000011920928955078125;
            e.focusMul = 1.2999999523162841796875;
        }
        else
        {
            if (seq < tDot)
            {
                float k_2 = (seq - tLine) / (tDot - tLine);
                k_2 *= k_2;
                e.vSpan = 0.00999999977648258209228515625;
                e.hSpan = mix(1.0, 0.01200000010430812835693359375, k_2);
                e.bright = fast::min(9.0, mix(9.0, 14.0, k_2)) * 0.550000011920928955078125;
                e.focusMul = 1.60000002384185791015625;
            }
            else
            {
                if (seq < tGone)
                {
                    float k_3 = (seq - tDot) / (tGone - tDot);
                    e.vSpan = 0.00999999977648258209228515625;
                    e.hSpan = 0.01200000010430812835693359375;
                    e.bright = 7.69999980926513671875 * exp((-k_3) * 5.5);
                    e.focusMul = 1.89999997615814208984375;
                    e.roll = 0.0040000001899898052215576171875 * k_3;
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
float4 stateAt(thread float2& uv, constant GhostCrtUniforms& u_1, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float2 res = u_1.iResolution.xy;
    uv.y = fast::max(uv.y, 2.5 / res.y);
    float2 param = uv;
    return _CRT_SAMPLE(previousPassTexture, previousPassTextureSmplr, param);
}

static inline __attribute__((always_inline))
float3 collapseLine(thread const float& u, constant GhostCrtUniforms& u_1, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float3 acc = float3(0.0);
    for (int i = 0; i < 12; i++)
    {
        float2 param = float2(u, (float(i) + 0.5) / 12.0);
        float4 _1283 = stateAt(param, u_1, previousPassTexture, previousPassTextureSmplr);
        acc += _1283.xyz;
    }
    return acc / float3(12.0);
}

static inline __attribute__((always_inline))
float3 collapseAll(constant GhostCrtUniforms& u_1, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float3 acc = float3(0.0);
    for (int y = 0; y < 4; y++)
    {
        for (int x = 0; x < 4; x++)
        {
            float2 param = (float2(float(x), float(y)) + float2(0.5)) / float2(4.0);
            float4 _1322 = stateAt(param, u_1, previousPassTexture, previousPassTextureSmplr);
            acc += _1322.xyz;
        }
    }
    return acc / float3(16.0);
}

static inline __attribute__((always_inline))
float3 collapseLight(thread const float2& pFace, thread const PowerEnv& env, constant GhostCrtUniforms& u_1, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float aspect = u_1.iResolution.x / u_1.iResolution.y;
    float spotV = fast::max(env.vSpan, 0.006000000052154064178466796875) * (1.0 + (0.60000002384185791015625 * (env.focusMul - 1.0)));
    float spotH = fast::max(env.hSpan, 0.006000000052154064178466796875 / aspect);
    float gy = exp(((-0.5) * (pFace.y / spotV)) * (pFace.y / spotV));
    float3 content;
    if (env.hSpan > 0.5)
    {
        float u = fast::clamp((pFace.x * 0.5) + 0.5, 0.0, 1.0);
        float param = u;
        content = collapseLine(param, u_1, previousPassTexture, previousPassTextureSmplr);
    }
    else
    {
        float gx = exp(((-0.5) * (pFace.x / spotH)) * (pFace.x / spotH));
        content = collapseAll(u_1, previousPassTexture, previousPassTextureSmplr);
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
float3 whitePoint(thread const float3& c, constant GhostCrtUniforms& u_1)
{
    float t = fast::clamp((u_1.crt_color_temp - 6500.0) / 2800.0, -1.0, 1.0);
    float3 _1798;
    if (t >= 0.0)
    {
        _1798 = mix(float3(1.0), float3(0.882000029087066650390625, 0.954999983310699462890625, 1.17999994754791259765625), float3(t));
    }
    else
    {
        _1798 = mix(float3(1.0), float3(1.1150000095367431640625, 1.0099999904632568359375, 0.8450000286102294921875), float3(-t));
    }
    float3 gains = _1798;
    return c * gains;
}

static inline __attribute__((always_inline))
float3 maskWeight(thread const float2& fragCoord, constant GhostCrtUniforms& u_1)
{
    float triadPx = u_1.iResolution.x / float(int(u_1.crt_mask_triads));
    float dark = 1.0 - u_1.crt_mask_strength;
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
float2 warpToContent(thread float2& p, thread const PowerEnv& env, thread const float& apl, thread const float& dgWobble, constant GhostCrtUniforms& u_1)
{
    float rc = cos(u_1.crt_rotation);
    float rs = sin(u_1.crt_rotation);
    p = float2x2(float2(rc, -rs), float2(rs, rc)) * p;
    p.x += ((u_1.crt_parallelogram + env.skew) * p.y);
    p.x *= (1.0 + (u_1.crt_trapezoid * p.y));
    float w = 1.0 / fast::max(u_1.crt_curve_radius, 1.0);
    float wx = 0.180000007152557373046875 * w;
    float wy = 0.23999999463558197021484375 * w;
    p.x *= (1.0 + ((wx * p.y) * p.y));
    p.x *= (1.0 + ((u_1.crt_pincushion * ((p.y * p.y) - 0.5)) * 2.0));
    float breathe = 1.0 + ((u_1.crt_hv_breathing * 0.0599999986588954925537109375) * apl);
    p.x += ((dgWobble * 0.006000000052154064178466796875) * sin(u_1.iTime * 61.0));
    p.y += ((dgWobble * 0.0040000001899898052215576171875) * sin((u_1.iTime * 47.0) + 1.7000000476837158203125));
    float2 span = float2(u_1.crt_h_size * env.hSpan, u_1.crt_v_size * env.vSpan);
    span *= ((breathe * env.sizeMul) * (1.0 + u_1.crt_overscan));
    p /= fast::max(span, float2(9.9999997473787516355514526367188e-05));
    p -= (float2(u_1.crt_h_pos, u_1.crt_v_pos) * 2.0);
    return (p * 0.5) + float2(0.5);
}

static inline __attribute__((always_inline))
float vHoldRoll(thread float& y, thread const float& extraRoll, constant GhostCrtUniforms& u_1)
{
    float beat = u_1.crt_v_hold;
    float phase = extraRoll;
    if (abs(beat) >= 0.1500000059604644775390625)
    {
        float t = u_1.iTime * abs(beat);
        float crawl = t + (0.2199999988079071044921875 * sin((t * 2.0) * 3.1415927410125732421875));
        phase += (fract(crawl) * sign(beat));
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
float hHoldTear(thread float& x, thread const float& y, constant GhostCrtUniforms& u_1)
{
    float df = u_1.crt_h_hold;
    if (abs(df) < 1.0)
    {
        return 1.0;
    }
    float perLine = df / 15734.0;
    float shift = fract(((y * float(int(u_1.crt_scan_lines))) * perLine) + ((u_1.iTime * df) * 0.0199999995529651641845703125));
    x = fract(x - shift);
    float d = fast::min(abs(x - 1.0), x);
    float bar = smoothstep(0.0, (0.17000000178813934326171875 * fast::min(abs(df) / 60.0, 1.0)) + 0.001000000047497451305389404296875, d);
    return mix(0.0599999986588954925537109375, 1.0, bar);
}

static inline __attribute__((always_inline))
float3 contentAt(thread const float2& uv, thread float& g_shiftY, constant GhostCrtUniforms& u_1, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float2 param = float2(uv.x, uv.y - g_shiftY);
    float4 _675 = stateAt(param, u_1, previousPassTexture, previousPassTextureSmplr);
    return _675.xyz;
}

static inline __attribute__((always_inline))
float3 scanSample(thread const float2& cuv, thread const float& focusMul, thread const float& cornerSoft, thread float& g_shiftY, thread float& g_ilOffset, constant GhostCrtUniforms& u_1, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float2 res = u_1.iResolution.xy;
    float lines = float(int(u_1.crt_scan_lines));
    float srcY = (cuv.y * lines) - 0.5;
    srcY += g_ilOffset;
    float y0 = floor(srcY);
    float fy = srcY - y0;
    float aspect = res.x / res.y;
    float sigmaX = (res.x / (u_1.crt_h_bandwidth * aspect)) * 0.449999988079071044921875;
    sigmaX = fast::max((sigmaX * focusMul) * cornerSoft, 0.2800000011920928955078125);
    float pxU = 1.0 / res.x;
    float convPx = u_1.crt_misconvergence * cornerSoft;
    float dR = (-convPx) * pxU;
    float dB = convPx * pxU;
    float3 acc = float3(0.0);
    float wsum = 0.0;
    for (int line = 0; line < 2; line++)
    {
        float ly = y0 + float(line);
        float lineV = (ly + 0.5) / lines;
        if ((lineV < 0.0) || (lineV > 1.0))
        {
            continue;
        }
        float dy = srcY - ly;
        float2 param = float2(cuv.x, lineV);
        float3 peek = contentAt(param, g_shiftY, u_1, previousPassTexture, previousPassTextureSmplr);
        float lum = fast::clamp(dot(peek, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625)), 0.0, 1.5);
        float sigma = ((u_1.crt_scan_min_width * (1.0 + ((u_1.crt_scan_bloom * 1.39999997615814208984375) * powr(lum, 0.62000000476837158203125)))) * focusMul) * cornerSoft;
        float wLine = exp(((-0.5) * (dy / sigma)) * (dy / sigma)) / (sigma * 2.5066282749176025390625);
        float3 lineAcc = float3(0.0);
        float3 lineW = float3(9.9999997473787516355514526367188e-05);
        for (int i = -2; i <= 2; i++)
        {
            float dx = float(i);
            float wx = exp(((-0.5) * (dx / sigmaX)) * (dx / sigmaX));
            float2 tuv = float2(cuv.x + (dx * pxU), lineV);
            float2 param_1 = tuv;
            float3 s = contentAt(param_1, g_shiftY, u_1, previousPassTexture, previousPassTextureSmplr);
            float wxR = exp(((-0.5) * ((dx + convPx) / sigmaX)) * ((dx + convPx) / sigmaX));
            float wxB = exp(((-0.5) * ((dx - convPx) / sigmaX)) * ((dx - convPx) / sigmaX));
            lineAcc += float3(s.x * wxR, s.y * wx, s.z * wxB);
            lineW += float3(wxR, wx, wxB);
        }
        acc += ((lineAcc / lineW) * wLine);
        wsum += wLine;
    }
    return acc;
}

static inline __attribute__((always_inline))
float3 vectorSample(thread const float2& cuv, thread const float& focusMul, thread const float& cornerSoft, thread float& g_shiftY, constant GhostCrtUniforms& u_1, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float2 res = u_1.iResolution.xy;
    float2 px = float2(1.0) / res;
    float sigmaPx = fast::max(((u_1.crt_scan_min_width * 1.7999999523162841796875) * focusMul) * cornerSoft, 0.550000011920928955078125);
    float3 acc = float3(0.0);
    float wsum = 0.0;
    for (int y = -2; y <= 2; y++)
    {
        for (int x = -2; x <= 2; x++)
        {
            float2 d = float2(float(x), float(y));
            float w = exp(((-0.5) * dot(d, d)) / (sigmaPx * sigmaPx));
            float2 param = cuv + (d * px);
            acc += (contentAt(param, g_shiftY, u_1, previousPassTexture, previousPassTextureSmplr) * w);
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
float3 radarInstrumentLight(thread const float2& cuv, thread const float2& pFace, constant GhostCrtUniforms& u_1)
{
    bool _1038 = u_1.crt_radar_overlay <= 0.0;
    bool _1045;
    if (_1038)
    {
        _1045 = u_1.crt_radar_sweep <= 0.0;
    }
    else
    {
        _1045 = _1038;
    }
    if (_1045)
    {
        return float3(0.0);
    }
    float aspect = u_1.iResolution.x / u_1.iResolution.y;
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
    float grid = (fast::clamp((((ring * 0.550000011920928955078125) + (_cross * 0.3499999940395355224609375)) + (tick * 0.800000011920928955078125)) + (center * 0.3499999940395355224609375), 0.0, 1.0) * u_1.crt_radar_overlay) * edge;
    float rpm = fast::max(u_1.crt_radar_sweep_rate, 0.100000001490116119384765625);
    float sweepA = (-1.57079637050628662109375) + ((u_1.iTime * rpm) * 0.10471975803375244140625);
    float param_12 = a;
    float param_13 = sweepA;
    float da = angleDelta(param_12, param_13);
    float param_14 = da * fast::max(r, 0.0500000007450580596923828125);
    float param_15 = 0.00999999977648258209228515625;
    float sweepLine = (linePulse(param_14, param_15) * smoothstep(0.02999999932944774627685546875, 0.100000001490116119384765625, r)) * smoothstep(1.019999980926513671875, 0.920000016689300537109375, r);
    float sweepBloom = ((exp((-da) * 14.0) * smoothstep(0.02999999932944774627685546875, 0.119999997317790985107421875, r)) * smoothstep(1.0, 0.7799999713897705078125, r)) * 0.2199999988079071044921875;
    float sweep = ((sweepLine + sweepBloom) * u_1.crt_radar_sweep) * edge;
    return float3(grid + sweep, (grid * 0.75) + (sweep * 0.4000000059604644775390625), grid * 0.25);
}

static inline __attribute__((always_inline))
float hash12(thread const float2& p)
{
    float3 p3 = fract(p.xyx * 0.103100001811981201171875);
    p3 += float3(dot(p3, p3.yzx + float3(33.3300018310546875)));
    return fract((p3.x + p3.y) * p3.z);
}

static inline __attribute__((always_inline))
float3 glassGlow(thread const float2& cuv, thread float& g_shiftY, constant GhostCrtUniforms& u_1, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    bool _1468 = u_1.crt_halation <= 0.0;
    bool _1475;
    if (_1468)
    {
        _1475 = u_1.crt_diffusion <= 0.0;
    }
    else
    {
        _1475 = _1468;
    }
    if (_1475)
    {
        return float3(0.0);
    }
    float2 res = u_1.iResolution.xy;
    float3 tight = float3(0.0);
    float3 wide = float3(0.0);
    float2 param = (cuv * res) + float2(fract(u_1.iTime * 13.0) * 289.0, fract(u_1.iTime * 7.0) * 331.0);
    float rot = hash12(param) * 6.283185482025146484375;
    for (int i = 0; i < 12; i++)
    {
        float a = (float(i) * 2.399960041046142578125) + rot;
        float r = sqrt((float(i) + 0.5) / 12.0);
        float2 d = float2(cos(a), sin(a)) * r;
        float2 param_1 = cuv + ((d * (0.01200000010430812835693359375 * res.y)) / res);
        float3 sT = contentAt(param_1, g_shiftY, u_1, previousPassTexture, previousPassTextureSmplr);
        float2 param_2 = cuv + ((d * (0.054999999701976776123046875 * res.y)) / res);
        float3 sW = contentAt(param_2, g_shiftY, u_1, previousPassTexture, previousPassTextureSmplr);
        tight += sT;
        wide += sW;
    }
    tight /= float3(12.0);
    wide /= float3(12.0);
    float wLum = dot(wide, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625));
    float3 halo = mix(wide, float3(wLum), float3(0.60000002384185791015625));
    return (tight * u_1.crt_diffusion) + (halo * u_1.crt_halation);
}

static inline __attribute__((always_inline))
float burnEfficiency(thread const float2& cuv, thread const float& dose, constant GhostCrtUniforms& u_1)
{
    float wear = smoothstep(0.0, 1.0, dose);
    if (u_1.crt_burnin_vintage > 0.0)
    {
        float rows = 24.0;
        float rowPh = fract(cuv.y * rows);
        float rowGhost = smoothstep(0.1500000059604644775390625, 0.5, rowPh) * smoothstep(0.85000002384185791015625, 0.5, rowPh);
        float rowWeight = (0.3499999940395355224609375 + (0.64999997615814208984375 * step(cuv.y, 1.0 / rows))) + (0.449999988079071044921875 * step(1.0 - (1.0 / rows), cuv.y));
        float margin = smoothstep(0.100000001490116119384765625, 0.0199999995529651641845703125, cuv.x) * 0.5;
        float2 c = cuv - float2(0.5);
        float panel = exp((-dot(c * float2(1.0, 1.39999997615814208984375), c * float2(1.0, 1.39999997615814208984375))) * 2.2000000476837158203125) * 0.4000000059604644775390625;
        float vintage = fast::clamp((((rowGhost * rowWeight) * 0.550000011920928955078125) + margin) + panel, 0.0, 1.0);
        wear = fast::max(wear, (vintage * u_1.crt_burnin_vintage) * 0.800000011920928955078125);
    }
    return 1.0 - ((0.3499999940395355224609375 * u_1.crt_burnin_visibility) * wear);
}

static inline __attribute__((always_inline))
float damperWires(thread const float& v, constant GhostCrtUniforms& u_1)
{
    float n = (float(int(u_1.crt_mask_triads)) > 520.0) ? 2.0 : 1.0;
    float wirePx = fast::max(u_1.iResolution.y * 0.000899999984540045261383056640625, 1.0);
    float w = wirePx / u_1.iResolution.y;
    float shade = 1.0;
    if (n < 1.5)
    {
        shade *= (1.0 - (0.3499999940395355224609375 * (1.0 - smoothstep(0.0, w, abs(v - 0.666999995708465576171875)))));
    }
    else
    {
        shade *= (1.0 - (0.3499999940395355224609375 * (1.0 - smoothstep(0.0, w, abs(v - 0.333000004291534423828125)))));
        shade *= (1.0 - (0.3499999940395355224609375 * (1.0 - smoothstep(0.0, w, abs(v - 0.666999995708465576171875)))));
    }
    return shade;
}

static inline __attribute__((always_inline))
void mainImage(thread float4& fragColor, thread const float2& fragCoord, thread int& g_contentMode, thread float& g_seq, thread float& g_aspect, thread float& g_shiftY, thread float& g_ilOffset, constant GhostCrtUniforms& u_1, texture2d<float> previousPassTexture, sampler previousPassTextureSmplr)
{
    float2 res = u_1.iResolution.xy;
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
    PowerEnv env = powerEnvelope(param_2, param_3, param_4, u_1);
    if (env.black > 0.5)
    {
        fragColor = float4(float3(0.0035000001080334186553955078125 * (1.0 - u_1.crt_glass_tint)), 1.0);
        return;
    }
    if (env.vSpan < 0.180000007152557373046875)
    {
        float2 pC = ((fragCoord / res) * 2.0) - float2(1.0);
        float2 param_5 = pC;
        PowerEnv param_6 = env;
        float3 lightC = collapseLight(param_5, param_6, u_1, previousPassTexture, previousPassTextureSmplr);
        float3 param_7 = lightC;
        float3 emittedC = whitePoint(param_7, u_1);
        float2 param_8 = fragCoord;
        emittedC *= maskWeight(param_8, u_1);
        emittedC *= u_1.crt_glass_tint;
        float2 qC = abs(pC) - float2(1.0 - u_1.crt_corner_radius);
        float cdC = length(fast::max(qC, float2(0.0))) - u_1.crt_corner_radius;
        float cmC = 1.0 - smoothstep(-0.0040000001899898052215576171875, 0.00200000009499490261077880859375, cdC);
        emittedC *= cmC;
        emittedC += float3((0.0035000001080334186553955078125 * (1.0 - u_1.crt_glass_tint)) * cmC);
        fragColor = float4(fast::max(emittedC, float3(0.0)), 1.0);
        return;
    }
    float2 p = ((fragCoord / res) * 2.0) - float2(1.0);
    float2 pFace = p;
    float2 param_9 = p;
    PowerEnv param_10 = env;
    float param_11 = apl;
    float param_12 = dgWobble;
    float2 _1996 = warpToContent(param_9, param_10, param_11, param_12, u_1);
    float2 cuv = _1996;
    if (u_1.crt_emi_wobble > 0.0)
    {
        cuv.x += (((u_1.crt_emi_wobble * 0.00120000005699694156646728515625) * sin((cuv.y * 19.0) + (u_1.iTime * 61.700000762939453125))) * (0.60000002384185791015625 + (0.4000000059604644775390625 * sin(u_1.iTime * 0.730000019073486328125))));
    }
    float param_13 = cuv.y;
    float param_14 = env.roll;
    float _2037 = vHoldRoll(param_13, param_14, u_1);
    cuv.y = param_13;
    float vbiShade = _2037;
    float param_15 = cuv.x;
    float param_16 = cuv.y;
    float _2048 = hHoldTear(param_15, param_16, u_1);
    cuv.x = param_15;
    float syncShade = vbiShade * _2048;
    bool _2054 = cuv.x < 0.0;
    bool _2061;
    if (!_2054)
    {
        _2061 = cuv.x > 1.0;
    }
    else
    {
        _2061 = _2054;
    }
    bool _2068;
    if (!_2061)
    {
        _2068 = cuv.y < 0.0;
    }
    else
    {
        _2068 = _2061;
    }
    bool _2075;
    if (!_2068)
    {
        _2075 = cuv.y > 1.0;
    }
    else
    {
        _2075 = _2068;
    }
    if (_2075)
    {
        fragColor = float4(float3(0.0035000001080334186553955078125 * (1.0 - u_1.crt_glass_tint)), 1.0);
        return;
    }
    float rEdge = length(pFace);
    float cornerSoft = 1.0 + (0.5 * smoothstep(0.550000011920928955078125, 1.25, rEdge));
    float focusMul = u_1.crt_focus * env.focusMul;
    g_aspect = res.x / res.y;
    float2 param_17 = cuv;
    float param_18 = focusMul;
    float param_19 = cornerSoft;
    float3 light = scanSample(param_17, param_18, param_19, g_shiftY, g_ilOffset, u_1, previousPassTexture, previousPassTextureSmplr);
    if (u_1.crt_vector_trace > 0.0)
    {
        float2 param_20 = cuv;
        float param_21 = focusMul;
        float param_22 = cornerSoft;
        light = mix(light, vectorSample(param_20, param_21, param_22, g_shiftY, u_1, previousPassTexture, previousPassTextureSmplr), float3(fast::clamp(u_1.crt_vector_trace, 0.0, 1.0)));
    }
    float2 param_23 = cuv;
    float2 param_24 = pFace;
    light += (radarInstrumentLight(param_23, param_24, u_1) * env.bright);
    if (dgWobble > 0.0030000000260770320892333984375)
    {
        float2 sw = float2((dgWobble * 0.0040000001899898052215576171875) * sin((u_1.iTime * 53.0) + (cuv.y * 9.0)), 0.0);
        float2 param_25 = cuv + sw;
        float4 _2170 = stateAt(param_25, u_1, previousPassTexture, previousPassTextureSmplr);
        light.x = mix(light.x, _2170.x, 0.60000002384185791015625);
        float2 param_26 = cuv - sw;
        float4 _2180 = stateAt(param_26, u_1, previousPassTexture, previousPassTextureSmplr);
        light.z = mix(light.z, _2180.z, 0.60000002384185791015625);
    }
    float2 param_27 = cuv;
    light += glassGlow(param_27, g_shiftY, u_1, previousPassTexture, previousPassTextureSmplr);
    float g2Lift = fast::max(u_1.crt_g2_screen - 0.550000011920928955078125, 0.0) * 2.2000000476837158203125;
    float retraceAmt = fast::max(g2Lift * 0.100000001490116119384765625, u_1.crt_retrace_lines * 0.14000000059604644775390625);
    if ((g2Lift > 0.0) || (retraceAmt > 0.0))
    {
        float lift = (g2Lift * 0.0500000007450580596923828125) * env.bright;
        float ph = fract((cuv.y * 13.0) + (cuv.x * 1.60000002384185791015625));
        float lines = (smoothstep(0.9700000286102294921875, 1.0, ph) * retraceAmt) * env.bright;
        light += float3(lift + lines);
    }
    light *= (env.bright * syncShade);
    if (u_1.crt_hum_amp > 0.0)
    {
        float bandY = fract(u_1.iTime / u_1.crt_hum_period);
        float d = abs(fract((cuv.y - bandY) + 0.5) - 0.5);
        float band = exp(((-d) * d) / 0.004999999888241291046142578125);
        light *= (1.0 - (u_1.crt_hum_amp * band));
    }
    light *= (1.0 + (u_1.crt_flicker * sin(60.946895599365234375 * u_1.iTime)));
    if (u_1.crt_noise > 0.0)
    {
        float2 param_28 = fragCoord + float2(fract(u_1.iTime * 7.0) * 331.0);
        float n = hash12(param_28);
        light *= (1.0 + ((u_1.crt_noise * 2.0) * (n - 0.5)));
    }
    float2 param_29 = float2(cuv.x, cuv.y - g_shiftY);
    float4 _2333 = stateAt(param_29, u_1, previousPassTexture, previousPassTextureSmplr);
    float dose = _2333.w;
    float2 param_30 = cuv;
    float param_31 = dose;
    light *= burnEfficiency(param_30, param_31, u_1);
    float3 param_32 = light;
    float3 emitted = whitePoint(param_32, u_1);
    float2 param_33 = fragCoord;
    float3 mw = maskWeight(param_33, u_1);
    float lum = fast::clamp(dot(emitted, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625)), 0.0, 1.0);
    mw = mix(mw, float3(1.0), float3(u_1.crt_mask_fade * lum));
    float avgT = mix(1.0, 0.3333333432674407958984375 + (0.666666686534881591796875 * (1.0 - u_1.crt_mask_strength)), 1.0);
    emitted *= (mw * mix(1.0, 1.0 / fast::max(avgT, 0.3400000035762786865234375), u_1.crt_mask_strength * 0.85000002384185791015625));
    float param_34 = fragCoord.y / res.y;
    emitted *= damperWires(param_34, u_1);
    emitted *= u_1.crt_glass_tint;
    float bezelShade = 1.0 - (u_1.crt_bezel * smoothstep(0.819999992847442626953125, 1.12000000476837158203125, rEdge));
    emitted *= bezelShade;
    float2 q = abs(pFace) - float2(1.0 - u_1.crt_corner_radius);
    float cornerDist = length(fast::max(q, float2(0.0))) - u_1.crt_corner_radius;
    float cornerMask = 1.0 - smoothstep(-0.0040000001899898052215576171875, 0.00200000009499490261077880859375, cornerDist);
    emitted *= cornerMask;
    emitted += float3((0.0035000001080334186553955078125 * (1.0 - u_1.crt_glass_tint)) * cornerMask);
    fragColor = float4(fast::max(emitted, float3(0.0)), 1.0);
}

fragment ghostcrtty_crt_display_out ghostcrtty_crt_display(constant GhostCrtUniforms& u_1 [[buffer(0)]], texture2d<float> previousPassTexture [[texture(2)]], sampler previousPassTextureSmplr [[sampler(2)]], float4 gl_FragCoord [[position]])
{
    ghostcrtty_crt_display_out out = {};
    int g_contentMode = 0;
    float g_seq = 0.0;
    float g_aspect = 1.33000004291534423828125;
    float g_shiftY = 0.0;
    float g_ilOffset = 0.0;
    float2 _crtFragCoord = float2(gl_FragCoord.x, u_1.iResolution.y - gl_FragCoord.y);
    float2 param_1 = _crtFragCoord;
    float4 param;
    mainImage(param, param_1, g_contentMode, g_seq, g_aspect, g_shiftY, g_ilOffset, u_1, previousPassTexture, previousPassTextureSmplr);
    out.FragColor = param;
    float4 _2467 = out.FragColor;
    float3 _2474 = powr(fast::clamp(_2467.xyz, float3(0.0), float3(1.0)), float3(0.4545454680919647216796875));
    out.FragColor.x = _2474.x;
    out.FragColor.y = _2474.y;
    out.FragColor.z = _2474.z;
    out.FragColor.w = 1.0;
    return out;
}

