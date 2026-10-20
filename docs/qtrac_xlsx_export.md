# Reading a QtracP per-stimulus Excel export

One workbook per recording, written by QtracP from the same `.QZD` file as the
recording's `.MEM`. Where the `.MEM` holds the finished numbers (one T-SICI value
per ISI), the workbook holds every pulse that produced them. The lab keeps them in
`Y:\Merged Data\xlsx Data` (the `CSP\` subfolder holds waveform exports, see below).

`parser/xlsx_parser.py` implements everything on this page; `tests/_xlsx_fixtures.py`
builds a small synthetic workbook in the same layout.

## 1. Matching a workbook to its `.MEM`

Match on the **Qtrac acquisition token** that ends both file stems
(`SNBR-196-TP3C60922B.xlsx` ↔ `SNBR-196-TP3C60922B.MEM`, token `TP3C60922B`).
Never match on the participant number: one pair on the share carries different
numbers in the two names, three workbooks carry none, and one recording was
exported four times under different names. When a token has several exports,
prefer the one with a `T` sheet, then the newest file.

## 2. Sheets

| Sheet | Holds | Unit |
|---|---|---|
| `T` | Test stimulus intensity of each pulse | %MSO, integers |
| `P` | MEP amplitude of each pulse (peak-to-peak in the QTMS protocols) | mV |
| `L` | MEP latency (stimulus to positive peak) | ms |
| `D` | Conditioning-test delay of each pulse, i.e. **the ISI** | ms |
| `QPP` | QtracP's command log | ignore |

Three export variants exist:

- `D`, `P`, `L`, `T`, `QPP`: the full per-stimulus export (54 of 61 files). Thresholds and amplitudes.
- `D`, `P`, `M<chan>-<trace>`, `QPP`: the operator exported one raw waveform instead of `L` and `T` (7 files). Amplitudes only; thresholds cannot be recomputed.
- `Wxxxx`, `Wxxx`, `Wxx`, `Wx`, `W`, `QPP`: a CSP waveform export (the `CSP\` folder). Nothing per stimulus; skip it.

## 3. Layout inside a sheet

Row 1 is a header with `Chan  N` every third column. Each channel owns a pair of
columns: elapsed time in minutes, then the sheet's value. The rows of different
channels are **not aligned** with each other, so read each channel's column pair on
its own and join the four sheets by channel and time. Newer exports also append a
long-format block on the right (`Elapsed Time (min)`, `Channel`, `Values`) that
repeats the same sheet in tidy form.

## 4. What each channel is

The channel numbers come from the QTMSG protocol, not from the measurement.

| Channel | Role |
|---|---|
| 1 | **RMT200 tracking**: test pulse alone, target 0.2 mV. Runs on its own during the RMT determination (4→2→1 %MSO steps), then keeps running every 4th stimulus throughout the T-SICI / T-SICF phase. That later stretch is the reference the `.MEM` divides the T-SICI thresholds by. |
| 5 | **RMT1000 tracking** (target 1 mV): test pulse alone. Also the test-alone pulse delivered every 4th stimulus during the A-SICI / A-SICF phases, which makes it their baseline. |
| 10 | **RMT50 tracking** (target 50 µV), test pulse alone. |
| 4, 6–9, 11–19 | **The paired pulses** (conditioning + test). Which ISI sits on which channel depends on the protocol version and the ISI option chosen, so **always read the ISI from `D`**, never from the channel number. Examples: T-SICI at 1, 1.5, 2, 2.5, 3, 3.5 ms on channels 11–16 (17–19 carry 4, 5, 7 ms when the nine-ISI option is used); A-SICF over 14 ISIs (1.0–4.9 ms) on 4, 6–9, 11–19, or over 9 ISIs on 11–19. |
| 20, 21, 22 | **Rejected traces**, diverted here by Qtrac's trace-skip options: 20 = spontaneous EMG before the stimulus, 21 = a long stimulus artefact, 22 = a missing stimulus. Their counts are the `.MEM`'s `NSkip`, `NArtRej`, `NArtMiss`. Never use them. |

The sign of `D` says which pairing a pulse belongs to: `D > 0` is a SICI pairing
(conditioning pulse first), `D < 0` a SICF pairing, `D = 0` a test pulse alone,
and `D = -300` marks the CSP staircase (channels 12–16 at 80–160 % RMT), which is
out of scope here.

## 5. Telling the phases apart

A conditioned channel is reused across phases, so the same channel and ISI can hold
T-SICI pulses early in the session and A-SICI pulses later. The reliable rule:

- a paired pulse delivered **while channel 5 is running** belongs to an **amplitude** phase (A-SICI when `D > 0`, A-SICF when `D < 0`); its test stimulus is held fixed at the RMT1000 level and the MEP is the reading;
- any other paired pulse belongs to a **threshold-tracking** phase (T-SICI when `D > 0`, T-SICF when `D < 0`); the test stimulus moves from pulse to pulse and *is* the reading.

A typical QTMSG20S session (SNBR-196, 22/09/2026) reads, in elapsed minutes:
RMT200 alone on channel 1 (1–5), T-SICI on channels 11–16 interleaved with channel 1
(6–13), RMT50 on channel 10 (17), RMT1000 on channel 5 (17–18), then A-SICF on
channels 4, 6–9, 11–19 with channel 5 every 4th pulse (34–51).

## 6. Getting the `.MEM` numbers back

| `.MEM` value | Pulses to use | Operation |
|---|---|---|
| `T-SICI(70%)Xms`, `!T-SICIvISI(%RMT)` | The ISI's channel in the tracking phase; channel 1 from the pulse just before that phase to its end | Qtrac's *log regression* on each set: regress `T` on `ln(P)` with weight `1 − |log10(P / 0.2)|` (clipped at 0, and 0 outside 0.01–2 mV), read the stimulus at `P = 0.2 mV`. Value = 100 × threshold(ISI) / threshold(channel 1). The `.MEM` line stores it minus 100. Reproduces the `.MEM` to within 0.5 %RMT on 44 of 51 files, and its `+/-` standard errors. |
| `!T-SICFvISI(%RMT)` | Same, with the `D < 0` tracking pulses | Same operation. 14 of 14 exact on the one file that has it. |
| `!A-SICIvISI(abs)`, `!A-SICFvISI(abs)` | The ISI's channel in the amplitude phase | Geometric mean of `P`. Exact on 225 of 225 values. |
| `!A-SICIvISI(rel)`, `!A-SICFvISI(rel)` | As above, plus channel 5 from the pulse just before the first pair to the last pair | 100 × geometric mean(ISI) / geometric mean(channel 5). Exact on about half the files, within a few percent on the rest; the `.MEM`'s `0.0` row is that baseline. |
| `RMT50`, `RMT200`, `RMT1000` (header) | Channels 10, 1, 5 during their determination stretch | **Not exactly recoverable**: Qtrac starts that regression at a *Restart* marker the export does not carry. Take them from the `.MEM`. |
| `NSkip`, `NArtRej`, `NArtMiss` | Channels 20, 21, 22 inside the phase | Count them. |

Dividing by the header `RMT200` instead of the channel-1 threshold tracked alongside
gives values off by a median of 4 %RMT.

## 7. Known traps

- **Increments instead of stimuli.** Two recordings (`SNBR-180-F1-TH3C60709A`, `SNBR-211-TH3C60813A`) export the paired-channel `T` as the increment above the conditioning pulse, so the pairs sit at 15–35 %MSO under an RMT of 47–62. Add `round(0.7 × latest channel-1 T)` before regressing.
- **Old protocol (QTMSG18S).** `SNBR-073` and `SNBR-158` also ran SICI against conditioning intensity on channels 6–9 at 2.5 ms; those pulses look like T-SICI at 2.5 ms and are not separated by the rule in §5.
- **Duplicates.** `TP3C60608B` exists four times, two of them without a `T` sheet.
- **Names.** `SNBR-213-BSL-*-TP3C60818A/B.xlsx` pair with `SNBR-080-FU-*-TP3C60818A/B.MEM`, whose headers say SNBR-080.

Sources: the `QTRACW & TMS 2017-07-10` and `QTMSG-18 Manual Part 1` PDFs under
`Y:\Merged Data\QtracW Install and Update Files\Qtrac Manuals`, and a comparison of
every matched workbook against its `.MEM` (September 2026).
