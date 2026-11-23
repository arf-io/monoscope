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
    float _414;
    if (powerOn)
    {
        _414 = fast::min(warmClock + dt, 3600.0);
    }
    else
    {
        _414 = fast::max(warmClock - (3.0 * dt), 0.0);
    }
    warmClock = _414;
    float aplNow = measureAPL(contentTexture, contentTextureSmplr);
    float _433;
    if (initialized)
    {
        _433 = mix(aplNow, aplIIR, exp((-dt) / 0.119999997317790985107421875));
    }
    else
    {
        _433 = aplNow;
    }
    aplIIR = _433;
    float2 param_2 = float2(2.5, 0.5) / res;
    float4 histP2 = _CRT_SAMPLE(historyTexture, historyTextureSmplr, param_2);
    float eraseClock = histP2.x + dt;
    float storedEraseNonce = histP2.y;
    float mismatchIIR = histP2.z;
    if (!initialized)
    {
        eraseClock = 1000.0;
        storedEraseNonce = float(int(gcu.crt_erase_nonce));
        mismatchIIR = 0.0;
    }
    else
    {
        if (storedEraseNonce != float(int(gcu.crt_erase_nonce)))
        {
            eraseClock = 0.0;
            storedEraseNonce = float(int(gcu.crt_erase_nonce));
        }
    }
    if ((eraseClock > 1.2000000476837158203125) && (mismatchIIR > 0.3499999940395355224609375))
    {
        eraseClock = 0.0;
    }
    float2 param_3 = float2(5.5, 0.5) / res;
    float4 histP5 = _CRT_SAMPLE(historyTexture, historyTextureSmplr, param_3);
    float writeClock = histP5.x;
    float inkCoverage = histP2.w;
    bool _520;
    if (initialized)
    {
        _520 = histP0.y != float(int(gcu.crt_power_nonce));
    }
    else
    {
        _520 = initialized;
    }
    bool dvstPowerEvent = _520;
    if ((!initialized) || dvstPowerEvent)
    {
        writeClock = 0.0;
    }
    else
    {
        if (eraseClock < 0.75)
        {
            writeClock = 0.0;
        }
        else
        {
            writeClock += dt;
        }
    }
    float dvstFullness = fast::clamp(inkCoverage / 0.0900000035762786865234375, 0.0, 1.0);
    float dvstDrawT = (0.180000007152557373046875 + (2.2999999523162841796875 * dvstFullness)) / fast::max(gcu.crt_dvst_write_rate, 0.00999999977648258209228515625);
    float dvstOrdMax = 1.059999942779541015625;
    float dvstFront = (writeClock / fast::max(dvstDrawT, 0.001000000047497451305389404296875)) * dvstOrdMax;
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
                if (x < 3.0)
                {
                    float storedCnt = 0.0;
                    float deadCnt = 0.0;
                    float inkCnt = 0.0;
                    for (int i = 0; i < 256; i++)
                    {
                        float2 guv = fract((float2(0.75487768650054931640625, 0.56984031200408935546875) * float(i)) + float2(0.5));
                        guv.y = fast::max(guv.y, 2.5 / res.y);
                        float2 param_4 = guv;
                        float raw = dot(fetchContent(param_4, contentTexture, contentTextureSmplr), float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625));
                        if (raw >= 0.07999999821186065673828125)
                        {
                            inkCnt += 1.0;
                        }
                        float2 param_5 = guv;
                        float st = _CRT_SAMPLE(historyTexture, historyTextureSmplr, param_5).x;
                        if (st > 0.5)
                        {
                            storedCnt += 1.0;
                            if (raw < 0.07999999821186065673828125)
                            {
                                deadCnt += 1.0;
                            }
                        }
                    }
                    float _665;
                    if (storedCnt > 3.5)
                    {
                        _665 = deadCnt / storedCnt;
                    }
                    else
                    {
                        _665 = 0.0;
                    }
                    float mismatch = _665;
                    float _675;
                    if (initialized)
                    {
                        _675 = mix(mismatch, mismatchIIR, exp((-dt) / 0.07999999821186065673828125));
                    }
                    else
                    {
                        _675 = 0.0;
                    }
                    float mm = _675;
                    float inkCov = inkCnt / 256.0;
                    fragColor = float4(eraseClock, storedEraseNonce, mm, inkCov);
                }
                else
                {
                    if (x < 6.0)
                    {
                        fragColor = float4(writeClock, 0.0, 0.0, 0.0);
                    }
                    else
                    {
                        fragColor = float4(0.0);
                    }
                }
            }
        }
        return;
    }
    float2 param_6 = uv;
    float3 content = fetchContent(param_6, contentTexture, contentTextureSmplr);
    float3 param_7 = content;
    content = adjustChroma(param_7);
    float3 param_8 = content;
    float3 drive = signalToDrive(param_8, gcu);
    float ablComp = 1.0 / (1.0 + ((gcu.crt_abl * fast::max(aplIIR - 0.3499999940395355224609375, 0.0)) * 2.2000000476837158203125));
    drive *= ablComp;
    float beamOn = float(powerOn);
    drive *= beamOn;
    float mdrive = dot(drive, float3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625));
    drive = float3(mdrive, 0.0, 0.0);
    float2 param_9 = uv;
    float4 histD = _CRT_SAMPLE(historyTexture, historyTextureSmplr, param_9);
    float stored = histD.x;
    float flash = histD.y * exp((-dt) / 0.180000007152557373046875);
    float wthru = 0.0;
    float drvL = drive.x;
    bool inCursor = false;
    if (false)
    {
        float2 cpos = float2(-1000000.0);
        float2 csz = float2(0.0);
        bool _777 = fragCoord.x >= (cpos.x - 1.0);
        bool _789;
        if (_777)
        {
            _789 = fragCoord.x <= ((cpos.x + csz.x) + 1.0);
        }
        else
        {
            _789 = _777;
        }
        bool _798;
        if (_789)
        {
            _798 = fragCoord.y <= (cpos.y + 1.0);
        }
        else
        {
            _798 = _789;
        }
        bool _810;
        if (_798)
        {
            _810 = fragCoord.y >= ((cpos.y - csz.y) - 1.0);
        }
        else
        {
            _810 = _798;
        }
        inCursor = _810;
    }
    if (eraseClock < 0.01200000010430812835693359375)
    {
        stored = 1.10000002384185791015625;
        flash = 0.0;
    }
    else
    {
        if (eraseClock < 0.20000000298023223876953125)
        {
            stored *= exp((-dt) / 0.04500000178813934326171875);
            flash = 0.0;
        }
        else
        {
            if (eraseClock < 0.75)
            {
                stored = 0.0;
                flash = 0.0;
            }
            else
            {
                float dvstOrd = (1.0 - uv.y) + (uv.x * 0.0599999986588954925537109375);
                bool reached = dvstFront >= dvstOrd;
                if ((((!inCursor) && (drvL >= 0.3499999940395355224609375)) && (stored < 0.5)) && reached)
                {
                    stored = 1.0;
                    flash = 1.0;
                }
            }
        }
    }
    if (inCursor && (drvL > 0.1500000059604644775390625))
    {
        wthru = 0.64999997615814208984375;
    }
    float doseD = histD.w;
    float incD = ((((stored * 0.5) + (flash * 0.5)) * dt) * 9.6999996458180248737335205078125e-05) * gcu.crt_burnin_rate;
    if (incD > 0.0)
    {
        float2 param_10 = fragCoord + float2(fract(gcu.iTime) * 917.0, 0.0);
        float rD = hash12(param_10);
        doseD += (0.0005000000237487256526947021484375 * step(rD, incD / 0.0005000000237487256526947021484375));
        doseD = fast::min(doseD, 1.0);
    }
    fragColor = float4(stored, flash, wthru, doseD);
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

