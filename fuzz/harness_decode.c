#include <sndfile.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "vio_track.h"

/*
** Decodes a file through the tracked virtual IO and writes, to stdout:
**   - a text header (ended by a newline) describing SF_INFO,
**   - then the raw little-endian float32 samples (frames*channels),
**   - then the final max_access offset as a trailer line.
** Two builds of this harness must produce byte-identical output for a
** well-formed input; that is the cross-implementation equivalence check.
*/
int
main (int argc, char **argv)
{
	if (argc != 2)
	{	fprintf (stderr, "usage: %s FILE\n", argv [0]) ;
		return 2 ;
	}

	FILE *fp = fopen (argv [1], "rb") ;
	if (fp == NULL)
		return 2 ;
	fseek (fp, 0, SEEK_END) ;
	long size = ftell (fp) ;
	fseek (fp, 0, SEEK_SET) ;
	if (size < 0)
	{	fclose (fp) ;
		return 2 ;
	}

	uint8_t *data = malloc ((size_t) size + 1) ;
	if (data == NULL)
	{	fclose (fp) ;
		return 2 ;
	}
	size_t got = fread (data, 1, (size_t) size, fp) ;
	fclose (fp) ;
	if ((long) got != size)
	{	free (data) ;
		return 2 ;
	}

	VIO_DATA vf ;
	SF_VIRTUAL_IO vio ;
	track_init (&vf, &vio, data, (size_t) size) ;

	SF_INFO info ;
	memset (&info, 0, sizeof (info)) ;
	SNDFILE *sf = sf_open_virtual (&vio, SFM_READ, &info, &vf) ;
	if (sf == NULL)
	{	printf ("OPEN_ERROR\t%s\t%lld\n", sf_strerror (NULL),
				(long long) vf.max_access) ;
		free (data) ;
	return 0 ;
	}

	int channels = info.channels > 0 ? info.channels : 1 ;
	if (channels > (1 << 20))
		channels = 1 << 20 ;

	printf ("OK\tfmt=%d\t subtype=%d\t frames=%lld\t sr=%d\t ch=%d\t "
			"sections=%d\t seekable=%d\n",
			info.format & SF_FORMAT_TYPEMASK,
			info.format & SF_FORMAT_SUBMASK,
			(long long) info.frames, info.samplerate, info.channels,
			info.sections, info.seekable) ;

	float *buf = malloc (sizeof (float) * (size_t) channels) ;
	if (buf == NULL)
	{	sf_close (sf) ;
		free (data) ;
		return 2 ;
	}

	sf_count_t total = 0 ;
	sf_count_t r ;
	while ((r = sf_readf_float (sf, buf, 1)) > 0)
	{
		fwrite (buf, sizeof (float), (size_t) (r * channels), stdout) ;
		total += r ;
	}

	int err = sf_error (sf) ;
	sf_close (sf) ;
	free (buf) ;
	free (data) ;

	printf ("TRAILER\tframes_read=%lld\tsf_error=%d\tmax_access=%lld\n",
			(long long) total, err, (long long) vf.max_access) ;
	return 0 ;
}
