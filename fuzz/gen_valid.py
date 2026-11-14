#!/usr/bin/env python3
"""Generate a diverse corpus of *valid* audio files via libsndfile (ctypes).

The files are written by the reference (system) libsndfile and span several
containers and sub-formats, channel counts, sample rates and frame counts.
They are later decoded by BOTH local builds and compared sample-by-sample.
"""
import ctypes
import math
import os
import sys

SF = ctypes.CDLL("libsndfile.so.1")

SF_FORMAT_WAV = 0x010000
SF_FORMAT_AIFF = 0x020000
SF_FORMAT_AU = 0x030000
SF_FORMAT_RAW = 0x040000
SF_FORMAT_PAF = 0x050000
SF_FORMAT_SVX = 0x060000
SF_FORMAT_NIST = 0x070000
SF_FORMAT_VOC = 0x080000
SF_FORMAT_IRCAM = 0x0A0000
SF_FORMAT_W64 = 0x0B0000
SF_FORMAT_MAT4 = 0x0C0000
SF_FORMAT_MAT5 = 0x0D0000
SF_FORMAT_PVF = 0x0E0000
SF_FORMAT_XI = 0x0F0000
SF_FORMAT_HTK = 0x100000
SF_FORMAT_SDS = 0x110000
SF_FORMAT_AVR = 0x120000
SF_FORMAT_WAVEX = 0x130000
SF_FORMAT_SD2 = 0x160000
SF_FORMAT_FLAC = 0x170000
SF_FORMAT_CAF = 0x180000
SF_FORMAT_WVE = 0x210000
SF_FORMAT_OGG = 0x200000

SF_FORMAT_PCM_S8 = 0x0001
SF_FORMAT_PCM_16 = 0x0002
SF_FORMAT_PCM_24 = 0x0003
SF_FORMAT_PCM_32 = 0x0004
SF_FORMAT_PCM_U8 = 0x0005
SF_FORMAT_FLOAT = 0x0006
SF_FORMAT_DOUBLE = 0x0007
SF_FORMAT_ULAW = 0x0010
SF_FORMAT_ALAW = 0x0011
SF_FORMAT_IMA_ADPCM = 0x0012
SF_FORMAT_MS_ADPCM = 0x0013
SF_FORMAT_GSM610 = 0x0020
SF_FORMAT_VOX_ADPCM = 0x0021
SF_FORMAT_G721_32 = 0x0030
SF_FORMAT_DWVW_12 = 0x0041
SF_FORMAT_DWVW_16 = 0x0042
SF_FORMAT_DWVW_24 = 0x0043


class SF_INFO(ctypes.Structure):
    _fields_ = [
        ("frames", ctypes.c_longlong),
        ("samplerate", ctypes.c_int),
        ("channels", ctypes.c_int),
        ("format", ctypes.c_int),
        ("sections", ctypes.c_int),
        ("seekable", ctypes.c_int),
    ]


SFM_WRITE = 0x20

# (label, container, subtype, channel constraint)
FORMATS = [
    ("wav_pcm16", SF_FORMAT_WAV, SF_FORMAT_PCM_16, None),
    ("wav_pcm24", SF_FORMAT_WAV, SF_FORMAT_PCM_24, None),
    ("wav_pcm32", SF_FORMAT_WAV, SF_FORMAT_PCM_32, None),
    ("wav_u8", SF_FORMAT_WAV, SF_FORMAT_PCM_U8, None),
    ("wav_s8", SF_FORMAT_WAV, SF_FORMAT_PCM_S8, None),
    ("wav_float", SF_FORMAT_WAV, SF_FORMAT_FLOAT, None),
    ("wav_double", SF_FORMAT_WAV, SF_FORMAT_DOUBLE, None),
    ("wav_ima", SF_FORMAT_WAV, SF_FORMAT_IMA_ADPCM, None),
    ("wav_msadpcm", SF_FORMAT_WAV, SF_FORMAT_MS_ADPCM, None),
    ("wav_ulaw", SF_FORMAT_WAV, SF_FORMAT_ULAW, None),
    ("wav_alaw", SF_FORMAT_WAV, SF_FORMAT_ALAW, None),
    ("wavex_pcm16", SF_FORMAT_WAVEX, SF_FORMAT_PCM_16, None),
    ("wavex_float", SF_FORMAT_WAVEX, SF_FORMAT_FLOAT, None),
    ("aiff_pcm16", SF_FORMAT_AIFF, SF_FORMAT_PCM_16, None),
    ("aiff_pcm24", SF_FORMAT_AIFF, SF_FORMAT_PCM_24, None),
    ("aiff_pcm32", SF_FORMAT_AIFF, SF_FORMAT_PCM_32, None),
    ("aiff_float", SF_FORMAT_AIFF, SF_FORMAT_FLOAT, None),
    ("aiff_ima", SF_FORMAT_AIFF, SF_FORMAT_IMA_ADPCM, None),
    ("au_pcm16", SF_FORMAT_AU, SF_FORMAT_PCM_16, None),
    ("au_pcm24", SF_FORMAT_AU, SF_FORMAT_PCM_24, None),
    ("au_pcm32", SF_FORMAT_AU, SF_FORMAT_PCM_32, None),
    ("au_ulaw", SF_FORMAT_AU, SF_FORMAT_ULAW, None),
    ("au_alaw", SF_FORMAT_AU, SF_FORMAT_ALAW, None),
    ("au_float", SF_FORMAT_AU, SF_FORMAT_FLOAT, None),
    ("w64_pcm16", SF_FORMAT_W64, SF_FORMAT_PCM_16, None),
    ("w64_pcm24", SF_FORMAT_W64, SF_FORMAT_PCM_24, None),
    ("w64_float", SF_FORMAT_W64, SF_FORMAT_FLOAT, None),
    ("w64_ima", SF_FORMAT_W64, SF_FORMAT_IMA_ADPCM, None),
    ("w64_msadpcm", SF_FORMAT_W64, SF_FORMAT_MS_ADPCM, None),
    ("caf_pcm16", SF_FORMAT_CAF, SF_FORMAT_PCM_16, None),
    ("caf_pcm24", SF_FORMAT_CAF, SF_FORMAT_PCM_24, None),
    ("caf_pcm32", SF_FORMAT_CAF, SF_FORMAT_PCM_32, None),
    ("caf_float", SF_FORMAT_CAF, SF_FORMAT_FLOAT, None),
    ("caf_double", SF_FORMAT_CAF, SF_FORMAT_DOUBLE, None),
    ("caf_ulaw", SF_FORMAT_CAF, SF_FORMAT_ULAW, None),
    ("caf_alaw", SF_FORMAT_CAF, SF_FORMAT_ALAW, None),
    ("caf_ima", SF_FORMAT_CAF, SF_FORMAT_IMA_ADPCM, None),
    ("flac_pcm16", SF_FORMAT_FLAC, SF_FORMAT_PCM_16, None),
    ("flac_pcm24", SF_FORMAT_FLAC, SF_FORMAT_PCM_24, None),
    ("flac_pcm32", SF_FORMAT_FLAC, SF_FORMAT_PCM_32, None),
    ("ogg_pcm", SF_FORMAT_OGG, 0x0060, None),   # SF_FORMAT_VORBIS
    ("voc_pcm16", SF_FORMAT_VOC, SF_FORMAT_PCM_16, None),
    ("voc_u8", SF_FORMAT_VOC, SF_FORMAT_PCM_U8, None),
    ("ircam_pcm16", SF_FORMAT_IRCAM, SF_FORMAT_PCM_16, None),
    ("ircam_ulaw", SF_FORMAT_IRCAM, SF_FORMAT_ULAW, None),
    ("nist_pcm16", SF_FORMAT_NIST, SF_FORMAT_PCM_16, None),
    ("nist_ulaw", SF_FORMAT_NIST, SF_FORMAT_ULAW, None),
    ("svx_pcm16", SF_FORMAT_SVX, SF_FORMAT_PCM_16, 1),
    ("pvf_pcm16", SF_FORMAT_PVF, SF_FORMAT_PCM_16, None),
    ("xi_pcm16", SF_FORMAT_XI, SF_FORMAT_PCM_16, None),
    ("htk_pcm16", SF_FORMAT_HTK, SF_FORMAT_PCM_16, 1),
    ("sds_pcm16", SF_FORMAT_SDS, SF_FORMAT_PCM_16, None),
    ("avr_pcm16", SF_FORMAT_AVR, SF_FORMAT_PCM_16, None),
    ("wve_alaw", SF_FORMAT_WVE, SF_FORMAT_ALAW, 1),
    ("raw_pcm16", SF_FORMAT_RAW, SF_FORMAT_PCM_16, None),
    ("raw_float", SF_FORMAT_RAW, SF_FORMAT_FLOAT, None),
    ("raw_ulaw", SF_FORMAT_RAW, SF_FORMAT_ULAW, None),
]


def make_samples(frames, channels, sr, seed):
    out = (ctypes.c_float * (frames * channels))()
    for n in range(frames):
        for c in range(channels):
            freq = 220.0 + 60.0 * c + 7.0 * (seed % 13)
            amp = 0.35 + 0.25 * ((seed % 5) / 4.0)
            v = amp * math.sin(2.0 * math.pi * freq * n / sr)
            v += 0.08 * math.sin(2.0 * math.pi * (freq * 2.01) * n / sr)
            out[n * channels + c] = v
    return out


def main():
    outdir = sys.argv[1]
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    os.makedirs(outdir, exist_ok=True)

    SF.sf_open.argtypes = [ctypes.c_char_p, ctypes.c_int,
                           ctypes.POINTER(SF_INFO)]
    SF.sf_open.restype = ctypes.c_void_p
    SF.sf_writef_float.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_longlong]
    SF.sf_writef_float.restype = ctypes.c_longlong
    SF.sf_close.argtypes = [ctypes.c_void_p]
    SF.sf_close.restype = ctypes.c_int
    SF.sf_strerror.argtypes = [ctypes.c_void_p]
    SF.sf_strerror.restype = ctypes.c_char_p

    written = 0
    idx = 0
    channels_choices = [1, 2, 3, 4, 6]
    sr_choices = [8000, 11025, 22050, 44100, 48000, 96000]

    while written < target:
        label, container, subtype, ch_limit = FORMATS[idx % len(FORMATS)]
        idx += 1
        channels = channels_choices[written % len(channels_choices)]
        if ch_limit is not None:
            channels = ch_limit
        sr = sr_choices[written % len(sr_choices)]
        frames = 8 + (written * 37 % 4000)
        seed = written + 1

        info = SF_INFO()
        info.frames = frames
        info.samplerate = sr
        info.channels = channels
        info.format = container | subtype
        info.sections = 0
        info.seekable = 0

        path = os.path.join(outdir, f"v_{written:04d}_{label}.bin")
        handle = SF.sf_open(path.encode(), SFM_WRITE, ctypes.byref(info))
        if not handle:
            # Skip combinations this lib build rejects; try next format.
            if os.path.exists(path):
                os.remove(path)
            continue

        buf = make_samples(frames, channels, sr, seed)
        n = SF.sf_writef_float(handle, buf, frames)
        SF.sf_close(handle)
        if n != frames:
            if os.path.exists(path):
                os.remove(path)
            continue
        written += 1

    print(f"wrote {written} valid files to {outdir}")


if __name__ == "__main__":
    main()
