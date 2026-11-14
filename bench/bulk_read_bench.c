/*
** Bulk block-read + format-conversion benchmark and bit-exact checker for the
** PCM import path (sf_readf_int / sf_readf_float).
**
** Usage:
**   bulk_read_bench bench  <file.wav> <reps> <chunk_frames>
**       Report median / p10 wall time for repeated full-file decode.
**   bulk_read_bench hash   <file.wav>...
**       Emit order-sensitive FNV-1a hashes of the fully decoded int and float
**       buffers plus frame counts, for byte-for-byte comparison across builds.
*/
#include <sndfile.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static double
now_sec (void)
{	struct timespec ts ;
	clock_gettime (CLOCK_MONOTONIC, &ts) ;
	return ts.tv_sec + ts.tv_nsec * 1e-9 ;
}

static int
cmp_double (const void *a, const void *b)
{	double x = * (const double *) a, y = * (const double *) b ;
	return (x > y) - (x < y) ;
}

static volatile long sink ;

static int
run_bench (const char *path, long reps, sf_count_t chunk)
{	SF_INFO info = {0} ;
	SNDFILE *f = sf_open (path, SFM_READ, &info) ;
	if (f == NULL)
	{	fprintf (stderr, "open failed %s: %s\n", path, sf_strerror (NULL)) ;
		return 1 ;
		} ;

	sf_count_t ch = info.channels ;
	int *buf = malloc ((size_t) chunk * ch * sizeof (int)) ;
	double *ts = malloc (reps * sizeof (double)) ;
	long acc = 0 ;

	for (long r = 0 ; r < reps ; r++)
	{	sf_seek (f, 0, SF_SEEK_SET) ;
		double t0 = now_sec () ;
		for (;;)
		{	sf_count_t got = sf_readf_int (f, buf, chunk) ;
			if (got <= 0)
				break ;
			acc += buf [got * ch - 1] ;
			} ;
		ts [r] = now_sec () - t0 ;
		} ;

	qsort (ts, reps, sizeof (double), cmp_double) ;
	printf ("%s frames=%lld ch=%d chunk=%lld median=%.6fs p10=%.6fs\n",
		path, (long long) info.frames, (int) ch, (long long) chunk,
		ts [reps / 2], ts [reps / 10]) ;

	sink = acc ;
	free (ts) ;
	free (buf) ;
	sf_close (f) ;
	return 0 ;
}

static unsigned long long
fnv (const unsigned char *p, size_t n)
{	unsigned long long h = 1469598103934665603ULL ;
	for (size_t i = 0 ; i < n ; i++)
	{	h ^= p [i] ;
		h *= 1099511628211ULL ;
		} ;
	return h ;
}

static int
run_hash (const char *path)
{	SF_INFO info = {0} ;
	SNDFILE *f = sf_open (path, SFM_READ, &info) ;
	if (f == NULL)
	{	fprintf (stderr, "open failed %s: %s\n", path, sf_strerror (NULL)) ;
		return 1 ;
		} ;

	sf_count_t total = info.frames * info.channels ;
	int *ib = malloc ((size_t) total * sizeof (int)) ;
	float *fb = malloc ((size_t) total * sizeof (float)) ;

	sf_count_t ri = sf_readf_int (f, ib, info.frames) ;
	sf_seek (f, 0, SF_SEEK_SET) ;
	sf_count_t rf = sf_readf_float (f, fb, info.frames) ;

	printf ("FILE %s ch=%d frames=%lld ri=%lld rf=%lld\n",
		path, info.channels, (long long) info.frames, (long long) ri, (long long) rf) ;
	printf ("  INT_HASH %llu\n  FLOAT_HASH %llu\n",
		fnv ((unsigned char *) ib, (size_t) ri * info.channels * sizeof (int)),
		fnv ((unsigned char *) fb, (size_t) rf * info.channels * sizeof (float))) ;

	free (ib) ;
	free (fb) ;
	sf_close (f) ;
	return 0 ;
}

int
main (int argc, char **argv)
{
	if (argc < 3)
	{	fprintf (stderr, "usage: %s bench <file> <reps> <chunk> | %s hash <files...>\n",
			argv [0], argv [0]) ;
		return 2 ;
		} ;

	if (strcmp (argv [1], "bench") == 0)
		return run_bench (argv [2], strtol (argv [3], NULL, 10), strtoll (argv [4], NULL, 10)) ;

	if (strcmp (argv [1], "hash") == 0)
	{	int rc = 0 ;
		for (int k = 2 ; k < argc ; k++)
			rc |= run_hash (argv [k]) ;
		return rc ;
		} ;

	fprintf (stderr, "unknown mode %s\n", argv [1]) ;
	return 2 ;
}
