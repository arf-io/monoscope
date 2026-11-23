# Tektronix DVST Writing Dynamics — Research Dossier

Research for the ghostcrtty `CRT_DVST` storage-tube shader path. Focus: **how fast does
the writing beam scan across the memory tube**, and how the stored image is laid down
progressively rather than flashed in all at once.

**Legend:** `[DOC]` = documented number from a primary/secondary source (quoted, cited
inline). `[EST]` = my estimate/derivation, flagged as such. `[CALC]` = arithmetic on
documented inputs.

---

## TL;DR — the numbers the shader needs

| Quantity | Value | Confidence | Source |
|---|---|---|---|
| **Stored writing speed** (bistable DVST) | **1500–4000 vector-inches/second** | `[DOC]` | Wikipedia/HandWiki 4010 |
| Same in metric | **≈ 3,800–10,160 cm/s ≈ 3.8–10 cm per *millisecond*** | `[CALC]` | — |
| Same in cm/µs | **≈ 0.004–0.010 cm/µs** (i.e. hundredths of a cm per µs) | `[CALC]` | — |
| Single full-diagonal vector (11.2″) | **2.8 ms (fast) – 7.5 ms (slow)** | `[CALC]` | — |
| Dense full screen, beam-limited | **≈ 1.8–5 s** | `[EST]` | derived |
| Full screen, comm-limited @ 9600 baud | **≈ 3 s**; @ 2400 baud **≈ 12 s** | `[EST]` | derived |
| Screen-clear / erase cycle (lockout) | **"on the order of a second"** (~0.5 s erase pulse + settle) | `[DOC]` | Wikipedia 4010; radiomuseum |
| Storage-screen phosphor | **green, P1-class willemite** Zn₂SiO₄:Mn (~525 nm) | `[DOC]` | TekWiki Phosphor |
| 4054 Option 31 refresh color | **orange** (special multi-layer phosphor), stored stays green | `[DOC]` | TekWiki 4054 / VCFed |

**Headline correction for the user's question:** the bistable DVST writing beam is **slow** —
it moves a few **centimetres per *millisecond***, not per microsecond. The dramatic
"cm/µs" numbers (100–1000 cm/µs) you see for Tektronix belong to *variable-persistence /
transfer-storage **oscilloscope*** tubes (7623, 7633), a **different, faster, non-bistable**
technology. The graphics terminals (4010/4014/4051–4054) are the slow bistable kind — which
is exactly *why* you can watch the picture draw itself on screen over seconds.

---

## 1. Stored writing speed — the key figure

Tektronix rated their bistable storage displays by **"stored writing speed"**: the fastest
the writing beam can be steered while still depositing enough charge to *store* a visible
trace. Move faster than this and the trace won't latch (it becomes a transient
"write-through" flash instead).

> "Tektronix referred to this as the *stored writing speed*, and measured it in terms of
> **vector-inches-per-second, with ratings between 1500 and 4000** being typical for their
> displays." `[DOC]`
> — Wikipedia, *Tektronix 4010*, https://en.wikipedia.org/wiki/Tektronix_4010 ; mirrored at
> HandWiki, https://handwiki.org/wiki/Engineering:Tektronix_4010

Unit conversions `[CALC]` (1 inch = 2.54 cm):

- 1500 in/s = 3,810 cm/s = **3.81 cm/ms = 0.00381 cm/µs**
- 4000 in/s = 10,160 cm/s = **10.16 cm/ms = 0.01016 cm/µs**

So the beam covers **a few centimetres per millisecond**. A single stroke crossing the whole
tube is milliseconds long — visible to the eye as it's laid down.

### Why "cm/µs" figures are misleading here `[DOC]`
Tektronix *oscilloscope* storage tubes quote far higher writing speeds because they use
**variable-persistence** and **transfer-storage** mechanisms, not simple bistable storage:

- 7623 Option 12: **200 cm/µs**; 7633: **1000 cm/µs**
  — Radiomuseum, *Tektronix: Three Kinds of Storage*,
  https://www.radiomuseum.org/forum/tektronix_three_kinds_of_storage.html and
  https://www.radiomuseum.org/forum/tektronix_7633_oscilloscope_a_1000_cms_storage_oscilloscope.html

These are ~10,000–100,000× faster than the bistable graphics terminals and are a **separate
technology**. For the DVST graphics-terminal simulation, the correct regime is the slow
**1500–4000 in/s** bistable one.

---

## 2. How the beam draws — random-access vector, point-to-point

DVST graphics terminals are **random-access (calligraphic / vector) displays**. The writing
gun is steered directly to XY coordinates and draws vectors and characters stroke-by-stroke —
there is **no fixed raster scan**.

> "The first four [bytes] following the GS position the graphic cursor, every point after
> that **draws a vector** on the display." … drawing proceeds by "moving **point to point**
> while in graphics mode." `[DOC]`
> — HandWiki / Wikipedia, *Tektronix 4010*

Consequences for the shader model:

- **Total draw time ≈ (total vector length ÷ writing speed) + per-vector overhead.**
  More content on screen ⇒ longer to draw. This is the behaviour the shader must reproduce:
  a sparse screen finishes quickly, a dense screen takes noticeably longer.
- Addressable grid: **1024 × 780** visible points, 10-bit (4010). `[DOC]`
  — TekWiki, https://w140.com/tekwiki/wiki/4010 ; Wikipedia (states 1024×768 "in graphics mode").
- Physical viewing area (4010): **6.7 × 9 inches (170 × 230 mm)**, 11″ tube. `[DOC]`
  — Wikipedia, *Tektronix 4010*. (4014 = 19″ tube, 4096×3120 with Enhanced Graphics Module —
  TekWiki https://w140.com/tekwiki/wiki/4014.)
- Screen **diagonal ≈ √(6.7² + 9²) = 11.2 inches** `[CALC]`.

### Beam-limited draw times `[CALC]`/`[EST]`

- One full-diagonal vector: 11.2″ ÷ 1500 in/s = **7.5 ms**; ÷ 4000 in/s = **2.8 ms**.
- Fill the screen with ~780 horizontal strokes of 9″ each = 7,020 vector-inches:
  ÷ 1500 = **4.7 s**; ÷ 4000 = **1.75 s**. `[EST]`
- General rule of thumb from the DVST literature: *"The erasing and redrawing process can
  take **several seconds for complex pictures**."* `[DOC]`
  — Wikipedia, *Direct-view bistable storage tube*,
  https://en.wikipedia.org/wiki/Direct-view_bistable_storage_tube

### Comm-limited draw times (often the real bottleneck) `[EST]`

In practice the host link was frequently slower than the beam, so you literally watched the
plot crawl across the tube as bytes arrived. Supported rates: **110, 300, 600, 1200, 2400,
4800, 9600 bit/s** `[DOC]` (Wikipedia). Each vector endpoint is ~2–5 transmitted bytes.

- ~1000 vectors × ~3 bytes ≈ 3,000 bytes. At 9600 baud (≈960 char/s): **≈ 3 s**; at 2400
  baud: **≈ 12 s**. `[EST]`
- Text housekeeping was fast by comparison: *"the carriage return took about 100 to 200 μs,
  and a screen clear operation … on the order of a second."* `[DOC]` (Wikipedia).

**Modelling takeaway:** total draw time should scale with **content amount** (coverage), in
the **seconds** regime for a full screen, sub-second for sparse content — either the
beam-limited or comm-limited derivation lands in the same order of magnitude.

---

## 3. The storage-screen phosphor — it is GREEN (P1-class), not P7

The DVST **storage screen is green.** Tektronix bistable storage targets used a **P1-family
willemite** phosphor as the viewable storage dielectric:

> P1 phosphor is **Zn₂SiO₄:Mn (willemite)**, yellowish-green, primary wavelength **~525 nm**,
> persistence ~20 ms; used as the **viewable bistable storage target** dielectric in storage
> CRTs. `[DOC]`
> — TekWiki, *Phosphor*, https://w140.com/tekwiki/wiki/Phosphor ; corroborated by CRT
> phosphor references (bunkerofdoom CRT phosphor research PDF).

The 4010 display was *"always monochrome, in three different brightnesses of 'CRT green'."*
`[DOC]` (Wikipedia). The nickname **"the mean green flashin' machine"** comes from the bright
**green** full-screen erase flash `[DOC]` (Wikipedia DVST article).

**Honest reconciliation with the sim and the user's phrasing:**
- The sim currently maps the stored glow to **P1 willemite green** — this is **correct** for
  a Tektronix bistable storage screen. Keep it.
- The user's *"P7 (or colored/orange)"* is **not** the DVST storage phosphor. **P7** is the
  blue-flash / long-yellow-persistence *radar/medical* phosphor — a different chemistry used
  on refresh (radar/scope) screens, **not** on Tek bistable storage targets. The stored DVST
  glow is green, full stop.
- The **only** authentic orange in this family is the **4054 Option 31** (see §3a) — a
  special *refresh* overlay, not the stored image.

### 3a. The orange — 4054 Option 30/31 refresh graphics `[DOC]`
Option 30 added a Signetics 8X300-based **dynamic (refresh) graphics coprocessor**; Option 31
paired it with a **special multi-layer CRT phosphor** so that **refreshed (non-stored)
graphics appear orange** while **stored graphics remain green**, on the same tube,
simultaneously.
— TekWiki, https://w140.com/tekwiki/wiki/4054 ; VCFed thread *Amazing Tektronix 4054 with
Option 30 and 31 Dynamic Graphics*,
https://forum.vcfed.org/index.php?threads/amazing-tektronix-4054-with-option-30-and-31-dynamic-graphics.1239131/
; demo video https://www.youtube.com/watch?v=M98VOoGFLL8 . Introduced in the 1982 Tek catalog.

So the sim's **orange = Opt 31 refresh / write-through**, **green = stored**, mapping is
chemically and historically correct.

---

## 4. Erase + view + write cycle timing

The tube is a reusable "blackboard": write → view (indefinitely) → erase → write again.

**Erase mechanism & timing** `[DOC]`:
> The target is erased by "writing the whole screen bright with a positive pulse, then dark
> with a negative pulse." *"After about **one-half second**, the positive erase pulse is
> removed and the storage target mesh drops back to a quiescent level near zero volts."* The
> front-panel **PERSISTENCE** control "changes the width of the erase pulses and, hence, the
> time that a stored image can be viewed."
> — Radiomuseum, *Tektronix: The Storage Story* / *Three Kinds of Storage*
> (https://www.radiomuseum.org/forum/tektronix_the_storage_story.html); Wikipedia 4010
> ("screen clear … on the order of a second").

So the **erase cycle** is: a **bright green full-screen flash** (positive pulse ~0.5 s) →
dark negative pulse → settle to quiescent, **total ≈ 1 second of lockout** during which you
cannot write. The 611 storage display manual (bitsavers 070-0752-02) documents the same
positive/negative erase-pulse scheme and a settling/settle-time spec (≈ 3.5 µs/cm + 5 µs for
positioning) — https://w140.com/tekwiki/wiki/611 .

**View / fade-positive behaviour** `[DOC]`: a stored image persists essentially
indefinitely, but over minutes the *"stored charges on the phosphors slowly migrated and
diffused away,"* so the image gets **more diffuse/blurry** and the background gradually
brightens ("fade-positive") until an erase is needed. Idle **hold mode** dims the flood to
save the target after long idle. (Wikipedia 4010.)

**Reconciliation with the sim's current model:**
- Sim: **~12 ms flash + ~0.75 s lockout.** `[EST vs DOC]`
  - The **0.75 s lockout** is well within the documented "~0.5 s erase pulse + settle ≈ 1 s"
    range — **keep**.
  - The **12 ms flash** is *shorter* than the real bright-green flash, which lasts a good
    fraction of a second (~0.5 s positive pulse). This is a deliberate legibility choice; it
    is **faster than reality**. Flag it in the honesty ledger. Optionally lengthen toward
    ~150–500 ms for authenticity, or leave as an intentional stylisation.

---

## 5. Direct implications for the progressive-write shader model

1. **Regime:** slow bistable. Beam covers the tube in **milliseconds per stroke**, a full
   screen in **~2–5 s** (beam-limited) or **~3–12 s** (comm-limited). Default the shader's
   write duration to the **low-single-digit-seconds** range for a full screen, scaled down
   for sparse content. This is authentic, not a stylisation.
2. **Scan/draw order:** true hardware order is *host-transmission order* (arbitrary vector
   list). The shader can't recover that, so a **defensible proxy** is reading/writing order
   (top-to-bottom, left-to-right) — honest approximation, flag it.
3. **Content scaling:** total draw time must **grow with coverage** (vector-length ∝ content
   amount). Sparse = fast, dense = slow — matches both the beam-limited and comm-limited
   physics.
4. **Writing spot:** authentic to show a **brighter moving write-through flash** at the beam
   position (write-through is genuinely brighter/whiter than the settled stored trace), which
   then settles to the crisp green stored glow behind it.
5. **Latch:** once written, the trace is the **crisp bistable green** (P1) persistent glow —
   don't regress crispness. Orange only under Opt 31.
6. **Erase:** keep the flash + ~0.75 s lockout; after erase, the next draw writes
   progressively again from zero.
7. **Rate knob:** expose a `dvst_write_rate` (like warmup) where **1.0 ≈ real-ish**
   (full screen in a couple of seconds); higher = faster. The physical anchor is
   **1500–4000 vector-inches/s**.

---

## Sources

- Wikipedia, *Tektronix 4010* — https://en.wikipedia.org/wiki/Tektronix_4010
  (stored writing speed 1500–4000 vector-in/s; screen 6.7×9″; baud rates; CR 100–200 µs;
  screen clear ~1 s; green; charge diffusion)
- HandWiki, *Engineering:Tektronix 4010* — https://handwiki.org/wiki/Engineering:Tektronix_4010
  (mirror; same stored-writing-speed quote, point-to-point vector drawing)
- Wikipedia, *Direct-view bistable storage tube* —
  https://en.wikipedia.org/wiki/Direct-view_bistable_storage_tube
  ("several seconds for complex pictures"; "mean green flashin' machine")
- TekWiki, *4010* — https://w140.com/tekwiki/wiki/4010 (11″ DVST, 1024×780, 10-bit)
- TekWiki, *4014* — https://w140.com/tekwiki/wiki/4014 (19″, 1024×768 / 4096×3120 EGM)
- TekWiki, *4054* — https://w140.com/tekwiki/wiki/4054 (Opt 30/31 dynamic/refresh graphics)
- VCFed forum, 4054 Option 30/31 —
  https://forum.vcfed.org/index.php?threads/amazing-tektronix-4054-with-option-30-and-31-dynamic-graphics.1239131/
  (Opt 31 special multi-layer phosphor: refresh = orange, stored = green)
- TekWiki, *Phosphor* — https://w140.com/tekwiki/wiki/Phosphor (P1 = Zn₂SiO₄:Mn willemite,
  ~525 nm, storage target)
- Radiomuseum, *Tektronix: Three Kinds of Storage* —
  https://www.radiomuseum.org/forum/tektronix_three_kinds_of_storage.html
  (bistable vs variable-persistence vs transfer; 200 & 1000 cm/µs scope tubes)
- Radiomuseum, *Tektronix: The Storage Story* —
  https://www.radiomuseum.org/forum/tektronix_the_storage_story.html
  (erase pulse ~0.5 s, PERSISTENCE control varies pulse width)
- Tektronix Type 611 Storage Display Unit Instruction Manual (bitsavers 070-0752-02 Rev G,
  Jun 1977) — https://w140.com/tekwiki/wiki/611 and
  https://archive.org/details/bitsavers_tektronixc611StorageDisplayUnitInstructionManualJu_76984044
  (positive/negative erase-pulse scheme; settling ≈ 3.5 µs/cm + 5 µs)
- Columbia University computing history, *The Tektronix 4010 Graphics Terminal* —
  https://www.columbia.edu/cu/computinghistory/tektronix.html

*Not directly reachable during this pass:* the archive.org **full djvu text** of the 611
manual (BookReader 404'd on the plain-text stream) and the Tektronix book *"Storage
Cathode-Ray Tubes and Circuits"* — both would firm up the exact 611 stored-writing-speed
number and erase-pulse width if a later pass can open the PDFs on bitsavers directly.
