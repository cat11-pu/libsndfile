#include <sndfile.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "vio_track.h"

/*
** Reads one file fully into memory, opens it through the tracked virtual IO,
** then drains it frame by frame. Emits a single JSON line on stdout:
**
** {"file":..., "status":"ok"|"open_error"|"read_error", "error":...,
**  "frames":N, "max_access":OFF, "size":SZ}
**
** max_access is the highest byte offset (exclusive) the reader touched, which
** localises where parsing/decoding stopped (the failure offset).
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
	{	fprintf (stderr, "cannot open %s\n", argv [1]) ;
		return 2 ;
	}

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
	{
		printf ("{\"file\":\"%s\",\"status\":\"open_error\",\"error\":\"%s\","
				"\"frames\":0,\"max_access\":%lld,\"size\":%ld}\n",
				argv [1], sf_strerror (NULL), (long long) vf.max_access, size) ;
		free (data) ;
		return 0 ;
	}

	int channels = info.channels > 0 ? info.channels : 1 ;
	if (channels > (1 << 20))
		channels = 1 << 20 ;

	float *buf = malloc (sizeof (float) * (size_t) channels) ;
	if (buf == NULL)
	{	sf_close (sf) ;
		free (data) ;
		return 2 ;
	}

	sf_count_t frames = 0 ;
	int read_status = 0 ; /* 0 ok, 1 error mid-stream */
	sf_count_t r ;
	while ((r = sf_readf_float (sf, buf, 1)) > 0)
		frames++ ;

	int err = sf_error (sf) ;
	if (err != SF_ERR_NO_ERROR)
		read_status = 1 ;

	sf_close (sf) ;
	free (buf) ;

	printf ("{\"file\":\"%s\",\"status\":\"%s\",\"error\":\"%s\","
			"\"frames\":%lld,\"max_access\":%lld,\"size\":%ld}\n",
			argv [1], read_status ? "read_error" : "ok",
			read_status ? sf_error_number (err) : "none",
			(long long) frames, (long long) vf.max_access, size) ;

	free (data) ;
	return 0 ;
}
