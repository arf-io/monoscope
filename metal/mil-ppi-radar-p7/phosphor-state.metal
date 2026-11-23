#pragma clang diagnostic ignored "-Wmissing-prototypes"

#include <metal_stdlib>
#include <simd/simd.h>

using namespace metal;

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

struct ghostcrtty_phosphor_state_out
{
    float4 FragColor [[color(0)]];
};

static inline __attribute__((always_inline))
float4 _CRT_SAMPLE(texture2d<float> t, sampler tSmplr, thread const float2& uv)
{
    return t.sample(tSmplr, float2(uv.x, 1.0 - uv.y));
}

static inline __attribute__((always_inline))
float3 fetchContent(thread const float2& uv, texture2d<float> contentTexture, sampler contentTextureSmplr)
{
    float2 param = uv;
    float4 t = _CRT_SAMPLE(contentTexture, contentTextureSmplr, param);
    return t.xyz / float3(fast::max(t.w, 0.001000000047497451305389404296875));
}

static inline __attribute__((always_inline))
float measureAPL(texture2d<float> contentTexture, sampler contentTextureSmplr)
{
    float apl = 0.0;
    for (int y = 0; y < 4; y++)
    {
        for (int x = 0; x < 4; x++)
        {
            float2 uv = (float2(float(x), float(y)) + float2(0.5)) / float2(4.0);
            float2 param = uv;
            apl += dot(fetchContent(param, contentTexture, contentTextureSmplr), float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625));
        }
    }
    return apl / 16.0;
}

static inline __attribute__((always_inline))
float3 adjustChroma(thread const float3& c)
{
    return c;
}

static inline __attribute__((always_inline))
float3 signalToDrive(thread const float3& linearContent, constant GhostCrtUniforms& gcu)
{
    float3 signal = powr(fast::max(linearContent, float3(0.0)), float3(0.4545454680919647216796875));
    signal = (signal * gcu.crt_contrast) + float3(gcu.crt_brightness);
    signal = fast::clamp(signal, float3(0.0), float3(1.39999997615814208984375));
    return powr(signal, float3(gcu.crt_tube_gamma));
}

static inline __attribute__((always_inline))
float decayPiecewise(thread const float& s, thread const float& dt, thread float& tauHi, thread const float& knee, thread float& tauLo, constant GhostCrtUniforms& gcu)
{
    if (s <= 0.0)
    {
        return 0.0;
    }
    float persist = gcu.crt_persistence;
    if (persist <= 0.0)
    {
        return 0.0;
    }
    tauHi *= persist;
    tauLo *= persist;
    if (s > knee)
    {
        float tKnee = tauHi * log(s / knee);
        if (dt <= tKnee)
        {
            return s * exp((-dt) / tauHi);
        }
        return knee * exp((-(dt - tKnee)) / tauLo);
    }
    return s * exp((-dt) / tauLo);
}

static inline __attribute__((always_inline))
float3 decayPiecewise3(thread const float3& s, thread const float& dt, constant GhostCrtUniforms& gcu)
{
    float param = s.x;
    float param_1 = dt;
    float param_2 = 0.00025000001187436282634735107421875;
    float param_3 = 0.100000001490116119384765625;
    float param_4 = 0.008000000379979610443115234375;
    float _182 = decayPiecewise(param, param_1, param_2, param_3, param_4, gcu);
    float param_5 = s.y;
    float param_6 = dt;
    float param_7 = 0.0;
    float param_8 = 0.0;
    float param_9 = 8.0;
    float _192 = decayPiecewise(param_5, param_6, param_7, param_8, param_9, gcu);
    float param_10 = s.z;
    float param_11 = dt;
    float param_12 = 0.0;
    float param_13 = 0.0;
    float param_14 = 0.0;
    float _201 = decayPiecewise(param_10, param_11, param_12, param_13, param_14, gcu);
    return float3(_182, _192, _201);
}

static inline __attribute__((always_inline))
float hash12(thread const float2& p)
{
    float3 p3 = fract(p.xyx * 0.103100001811981201171875);
    p3 += float3(dot(p3, p3.yzx + float3(33.3300018310546875)));
    return fract((p3.x + p3.y) * p3.z);
}

static inline __attribute__((always_inline))
void mainImage(thread float4& fragColor, thread const float2& fragCoord, constant GhostCrtUniforms& gcu, texture2d<float> contentTexture, sampler contentTextureSmplr, texture2d<float> historyTexture, sampler historyTextureSmplr)
{
    float2 res = gcu.iResolution.xy;
    float2 uv = fragCoord / res;
    float dt = fast::clamp(gcu.iTimeDelta, 0.0, 0.100000001490116119384765625);
    float2 param = float2(0.5) / res;
    float4 histP0 = _CRT_SAMPLE(historyTexture, historyTextureSmplr, param);
    float2 param_1 = float2(1.5, 0.5) / res;
    float4 histP1 = _CRT_SAMPLE(historyTexture, historyTextureSmplr, param_1);
    bool initialized = histP1.w > 0.5;
    float seqClock = histP0.x + dt;
    float storedPowerNonce = histP0.y;
    float storedDegaussNonce = histP0.z;
    float powerState = histP0.w;
    float warmClock = histP1.x;
    float aplIIR = histP1.y;
    float degaussClock = histP1.z + dt;
    bool powerOn = int(gcu.crt_power_on) != 0;
    if (!initialized)
    {
        seqClock = 0.0;
        warmClock = 0.0;
        degaussClock = 1000.0;
        storedPowerNonce = float(int(gcu.crt_power_nonce));
        storedDegaussNonce = float(int(gcu.crt_degauss_nonce));
        powerState = float(powerOn);
    }
    else
    {
        if (storedPowerNonce != float(int(gcu.crt_power_nonce)))
        {
            seqClock = 0.0;
            storedPowerNonce = float(int(gcu.crt_power_nonce));
            powerState = float(powerOn);
        }
        if (storedDegaussNonce != float(int(gcu.crt_degauss_nonce)))
        {
            degaussClock = 0.0;
            storedDegaussNonce = float(int(gcu.crt_degauss_nonce));
        }
    }
    float _415;
    if (powerOn)
    {
        _415 = fast::min(warmClock + dt, 3600.0);
    }
    else
    {
        _415 = fast::max(warmClock - (3.0 * dt), 0.0);
    }
    warmClock = _415;
    float aplNow = measureAPL(contentTexture, contentTextureSmplr);
    float _434;
    if (initialized)
    {
        _434 = mix(aplNow, aplIIR, exp((-dt) / 0.119999997317790985107421875));
    }
    else
    {
        _434 = aplNow;
    }
    aplIIR = _434;
    float rollPhase = 0.0;
    float rollPrev = 0.0;
    float estHz = 60.0;
    float fieldParity = 0.0;
    if (fragCoord.y < 1.0)
    {
        float x = floor(fragCoord.x);
        if (x < 1.0)
        {
            fragColor = float4(seqClock, storedPowerNonce, storedDegaussNonce, powerState);
        }
        else
        {
            if (x < 2.0)
            {
                fragColor = float4(warmClock, aplIIR, degaussClock, 1.0);
            }
            else
            {
                if ((x < 3.0) && (x >= 2.0))
                {
                    fragColor = float4(float(int(gcu.crt_erase_nonce)), 0.0, 0.0, 0.0);
                }
                else
                {
                    fragColor = float4(0.0);
                }
            }
        }
        return;
    }
    float2 param_2 = uv;
    float3 content = fetchContent(param_2, contentTexture, contentTextureSmplr);
    float3 param_3 = content;
    content = adjustChroma(param_3);
    float3 param_4 = content;
    float3 drive = signalToDrive(param_4, gcu);
    float ablComp = 1.0 / (1.0 + ((gcu.crt_abl * fast::max(aplIIR - 0.3499999940395355224609375, 0.0)) * 2.2000000476837158203125));
    drive *= ablComp;
    float beamOn = float(powerOn);
    drive *= beamOn;
    float mdrive = dot(drive, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625));
    drive = float3(mdrive, 0.0, 0.0);
    if ((gcu.crt_cursor_overdrive > 0.0) && false)
    {
        float age = gcu.iTime - gcu.iTime;
        if ((age >= 0.0) && (age < 0.25))
        {
            float2 cpos = float2(-1000000.0);
            float2 csz = float2(0.0);
            bool _568 = fragCoord.x >= cpos.x;
            bool _579;
            if (_568)
            {
                _579 = fragCoord.x <= (cpos.x + csz.x);
            }
            else
            {
                _579 = _568;
            }
            bool inX = _579;
            bool _585 = fragCoord.y <= cpos.y;
            bool _596;
            if (_585)
            {
                _596 = fragCoord.y >= (cpos.y - csz.y);
            }
            else
            {
                _596 = _585;
            }
            bool inY = _596;
            if (inX && inY)
            {
                drive *= (1.0 + (gcu.crt_cursor_overdrive * exp((-age) / 0.039999999105930328369140625)));
            }
        }
    }
    float2 param_5 = uv;
    float4 hist = _CRT_SAMPLE(historyTexture, historyTextureSmplr, param_5);
    float3 param_6 = hist.xyz;
    float param_7 = dt;
    float3 excited = decayPiecewise3(param_6, param_7, gcu);
    float2 param_8 = float2(2.5, 0.5) / res;
    float4 histP2n = _CRT_SAMPLE(historyTexture, historyTextureSmplr, param_8);
    bool _641;
    if (initialized)
    {
        _641 = histP2n.x != float(int(gcu.crt_erase_nonce));
    }
    else
    {
        _641 = initialized;
    }
    if (_641)
    {
        excited = float3(0.0);
    }
    float blue = fast::max(drive.x, excited.x);
    float yPrev = hist.y * exp((-dt) / (8.0 * fast::max(gcu.crt_persistence, 0.001000000047497451305389404296875)));
    float yTarget = blue * 0.85000002384185791015625;
    float yellow = mix(yPrev, fast::max(yTarget, yPrev), 1.0 - exp((-dt) / 0.119999997317790985107421875));
    float3 newState = float3(blue, yellow, 0.0);
    float dose = hist.w;
    float emitLum = newState.x;
    float inc = ((emitLum * dt) * 9.6999996458180248737335205078125e-05) * gcu.crt_burnin_rate;
    if (inc > 0.0)
    {
        float p = inc / 0.0005000000237487256526947021484375;
        float2 param_9 = fragCoord + float2(fract(gcu.iTime) * 917.0, 0.0);
        float r = hash12(param_9);
        dose += (0.0005000000237487256526947021484375 * step(r, p));
        dose = fast::min(dose, 1.0);
    }
    fragColor = float4(newState, dose);
}

fragment ghostcrtty_phosphor_state_out ghostcrtty_phosphor_state(constant GhostCrtUniforms& gcu [[buffer(0)]], texture2d<float> contentTexture [[texture(0)]], texture2d<float> historyTexture [[texture(1)]], sampler contentTextureSmplr [[sampler(0)]], sampler historyTextureSmplr [[sampler(1)]], float4 gl_FragCoord [[position]])
{
    ghostcrtty_phosphor_state_out out = {};
    float2 _crtFragCoord = float2(gl_FragCoord.x, gcu.iResolution.y - gl_FragCoord.y);
    float2 param_1 = _crtFragCoord;
    float4 param;
    mainImage(param, param_1, gcu, contentTexture, contentTextureSmplr, historyTexture, historyTextureSmplr);
    out.FragColor = param;
    return out;
}

