/*
** Copyright (C) 2026 Erik de Castro Lopo <erikd@mega-nerd.com>
**
** This program is free software; you can redistribute it and/or modify
** it under the terms of the GNU General Public License as published by
** the Free Software Foundation; either version 2 of the License, or
** (at your option) any later version.
**
** This program is distributed in the hope that it will be useful,
** but WITHOUT ANY WARRANTY; without even the implied warranty of
** MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
** GNU General Public License for more details.
**
** You should have received a copy of the GNU General Public License
** along with this program; if not, write to the Free Software
** Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
*/

#include "sfconfig.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if HAVE_UNISTD_H
#include <unistd.h>
#else
#include "sf_unistd.h"
#endif

#include <sndfile.h>

#include "utils.h"

#define CHANNELS	2
#define FRAME_COUNT	4410
#define PARK_POS	123
#define BUF_FRAMES	(FRAME_COUNT + 100)

typedef struct
{	sf_count_t	start ;
	sf_count_t	len ;
	sf_count_t	expect ;
} RangeCase ;

/* Boundary and out-of-range cases. `expect` is the required return value. */
static const RangeCase cases [] =
{	/* Zero length requests. */
	{ 0, 0, 0 },
	{ FRAME_COUNT, 0, 0 },
	/* Minimal in-range requests. */
	{ 0, 1, 1 },
	{ 1, 1, 1 },
	{ FRAME_COUNT - 1, 1, 1 },
	/* Interior and whole file requests. */
	{ FRAME_COUNT / 2, FRAME_COUNT / 2, FRAME_COUNT / 2 },
	{ 0, FRAME_COUNT, FRAME_COUNT },
	/* Requests clamped by end of file. */
	{ FRAME_COUNT - 1, 2, 1 },
	{ FRAME_COUNT - 3, 10, 3 },
	{ 0, FRAME_COUNT + 100, FRAME_COUNT },
	/* Requests starting at or past end of file. */
	{ FRAME_COUNT, 1, 0 },
	{ FRAME_COUNT + 7, 5, 0 },
	/* Invalid requests. */
	{ -1, 4, -1 },
	{ 4, -1, -1 },
	{ -5, -5, -1 }
} ;

static void
create_test_file (const char *filename, int format)
{	SF_INFO info ;
	SNDFILE *file ;
	short *data ;
	sf_count_t k ;
	int i ;

	data = malloc (FRAME_COUNT * CHANNELS * sizeof (short)) ;
	exit_if_true (data == NULL, "\n\n%s : malloc failed.\n", __func__) ;

	for (i = 0 ; i < FRAME_COUNT * CHANNELS ; i++)
		data [i] = (short) ((i * 7 + 13) % 60000 - 30000) ;

	info.samplerate = 44100 ;
	info.channels = CHANNELS ;
	info.format = format ;

	file = sf_open (filename, SFM_WRITE, &info) ;
	exit_if_true (file == NULL, "\n\n%s : sf_open (%s) failed : %s\n", __func__, filename, sf_strerror (NULL)) ;

	k = sf_writef_short (file, data, FRAME_COUNT) ;
	exit_if_true (k != FRAME_COUNT, "\n\n%s : sf_writef_short returned %ld.\n", __func__, (long) k) ;

	sf_close (file) ;
	free (data) ;
} /* create_test_file */

#define DEFINE_RANGE_TEST(TYPE, READF, READF_RANGE) \
static void \
run_cases_##TYPE (SNDFILE *file, const char *filename) \
{	TYPE *ref, *buf, one [CHANNELS] ; \
	sf_count_t pos, ret ; \
	int k ; \
	sf_count_t i ; \
	\
	ref = malloc (FRAME_COUNT * CHANNELS * sizeof (TYPE)) ; \
	buf = malloc (BUF_FRAMES * CHANNELS * sizeof (TYPE)) ; \
	exit_if_true (ref == NULL || buf == NULL, "\n\n%s : malloc failed.\n", __func__) ; \
	\
	/* Reference : read the whole file, slices are taken from this. */ \
	exit_if_true (sf_seek (file, 0, SEEK_SET) != 0, "\n\n%s : rewind failed.\n", __func__) ; \
	ret = READF (file, ref, FRAME_COUNT) ; \
	exit_if_true (ret != FRAME_COUNT, "\n\n%s : whole file read returned %ld.\n", __func__, (long) ret) ; \
	\
	/* Park the read position somewhere non-trivial. Range reads must not move it. */ \
	exit_if_true (sf_seek (file, PARK_POS, SEEK_SET) != PARK_POS, "\n\n%s : seek failed.\n", __func__) ; \
	\
	for (k = 0 ; k < ARRAY_LEN (cases) ; k++) \
	{	memset (buf, 0xA5, BUF_FRAMES * CHANNELS * sizeof (TYPE)) ; \
		\
		ret = READF_RANGE (file, buf, cases [k].start, cases [k].len) ; \
		exit_if_true (ret != cases [k].expect, \
				"\n\n%s (%s) case %d { start %ld, len %ld } : expected %ld, got %ld.\n", \
				__func__, filename, k, (long) cases [k].start, (long) cases [k].len, \
				(long) cases [k].expect, (long) ret) ; \
		\
		if (ret < 0) \
		{	exit_if_true (sf_error (file) == SF_ERR_NO_ERROR, \
					"\n\n%s (%s) case %d : -1 returned but sf_error is clear.\n", __func__, filename, k) ; \
			continue ; \
			} ; \
		\
		/* Compare against the matching slice of the whole file read. */ \
		exit_if_true (ret > 0 && memcmp (buf, ref + cases [k].start * CHANNELS, ret * CHANNELS * sizeof (TYPE)) != 0, \
				"\n\n%s (%s) case %d : data differs from whole-file slice.\n", __func__, filename, k) ; \
		\
		/* The unread tail of the requested range must be zero filled. */ \
		for (i = ret * CHANNELS ; i < cases [k].len * CHANNELS ; i++) \
			exit_if_true (buf [i] != 0, \
					"\n\n%s (%s) case %d : item %ld of requested range not zeroed.\n", \
					__func__, filename, k, (long) i) ; \
		\
		pos = sf_seek (file, 0, SEEK_CUR) ; \
		exit_if_true (pos != PARK_POS, \
				"\n\n%s (%s) case %d : read position moved to %ld.\n", __func__, filename, k, (long) pos) ; \
		} ; \
	\
	/* NULL buffer handling. */ \
	exit_if_true (READF_RANGE (file, NULL, 0, 4) != -1, \
			"\n\n%s (%s) : NULL ptr with len > 0 did not return -1.\n", __func__, filename) ; \
	exit_if_true (READF_RANGE (file, NULL, 0, 0) != 0, \
			"\n\n%s (%s) : NULL ptr with len == 0 did not return 0.\n", __func__, filename) ; \
	\
	/* A sequential read after all the range reads must still line up. */ \
	ret = READF (file, one, 1) ; \
	exit_if_true (ret != 1 || memcmp (one, ref + PARK_POS * CHANNELS, sizeof (one)) != 0, \
			"\n\n%s (%s) : sequential read after range reads is misaligned.\n", __func__, filename) ; \
	\
	free (ref) ; \
	free (buf) ; \
} /* run_cases_##TYPE */

DEFINE_RANGE_TEST (short, sf_readf_short, sf_readf_range_short)
DEFINE_RANGE_TEST (int, sf_readf_int, sf_readf_range_int)
DEFINE_RANGE_TEST (float, sf_readf_float, sf_readf_range_float)
DEFINE_RANGE_TEST (double, sf_readf_double, sf_readf_range_double)

static void
test_format (int format, const char *tag)
{	SF_INFO info ;
	SNDFILE *file ;
	char filename [256] ;

	snprintf (filename, sizeof (filename), "readf_range_%s.wav", tag) ;
	print_test_name ("readf_range_test", filename) ;

	create_test_file (filename, format) ;

	file = sf_open (filename, SFM_READ, &info) ;
	exit_if_true (file == NULL, "\n\n%s : sf_open (%s) failed.\n", __func__, filename) ;
	exit_if_true (info.frames != FRAME_COUNT || info.channels != CHANNELS,
			"\n\n%s : bad SF_INFO (frames %ld, channels %d).\n",
			__func__, (long) info.frames, info.channels) ;

	run_cases_short (file, filename) ;
	run_cases_int (file, filename) ;
	run_cases_float (file, filename) ;
	run_cases_double (file, filename) ;

	sf_close (file) ;
	remove (filename) ;
} /* test_format */

static void
write_mode_test (void)
{	SF_INFO info ;
	SNDFILE *file ;
	short buf [8] ;
	const char *filename = "readf_range_write_mode.wav" ;

	print_test_name ("readf_range_test (write mode)", filename) ;

	info.samplerate = 44100 ;
	info.channels = CHANNELS ;
	info.format = SF_FORMAT_WAV | SF_FORMAT_PCM_16 ;

	file = sf_open (filename, SFM_WRITE, &info) ;
	exit_if_true (file == NULL, "\n\n%s : sf_open (%s) failed.\n", __func__, filename) ;

	exit_if_true (sf_readf_range_short (file, buf, 0, 1) != -1,
			"\n\n%s : range read on SFM_WRITE file did not return -1.\n", __func__) ;
	exit_if_true (sf_error (file) == SF_ERR_NO_ERROR,
			"\n\n%s : -1 returned but sf_error is clear.\n", __func__) ;

	sf_close (file) ;
	remove (filename) ;
} /* write_mode_test */

int
main (void)
{
	test_format (SF_FORMAT_WAV | SF_FORMAT_PCM_16, "pcm16") ;
	test_format (SF_FORMAT_WAV | SF_FORMAT_PCM_24, "pcm24") ;
	test_format (SF_FORMAT_WAV | SF_FORMAT_PCM_32, "pcm32") ;
	test_format (SF_FORMAT_WAV | SF_FORMAT_FLOAT, "float") ;

	write_mode_test () ;

	return 0 ;
} /* main */
