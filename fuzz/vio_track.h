#ifndef VIO_TRACK_H
#define VIO_TRACK_H

#include <sndfile.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct
{
	sf_count_t offset ;
	sf_count_t length ;
	const unsigned char *data ;
	/* Highest byte offset the reader ever touched (read end, exclusive). */
	sf_count_t max_access ;
} VIO_DATA ;

static sf_count_t
track_get_filelen (void *user_data)
{
	VIO_DATA *vf = (VIO_DATA *) user_data ;
	return vf->length ;
}

static sf_count_t
track_seek (sf_count_t offset, int whence, void *user_data)
{
	VIO_DATA *vf = (VIO_DATA *) user_data ;
	sf_count_t new_offset ;

	switch (whence)
	{	case SEEK_SET :
			new_offset = offset ;
			break ;
		case SEEK_CUR :
			new_offset = vf->offset + offset ;
			break ;
		case SEEK_END :
			new_offset = vf->length + offset ;
			break ;
		default :
			return -1 ;
	}

	if (new_offset > vf->length)
		new_offset = vf->length ;
	if (new_offset < 0)
		new_offset = 0 ;

	vf->offset = new_offset ;
	if (new_offset > vf->max_access)
		vf->max_access = new_offset ;
	return vf->offset ;
}

static sf_count_t
track_read (void *ptr, sf_count_t count, void *user_data)
{
	VIO_DATA *vf = (VIO_DATA *) user_data ;

	if (vf->offset >= vf->length)
		return 0 ;
	if (vf->offset + count > vf->length)
		count = vf->length - vf->offset ;

	memcpy (ptr, vf->data + vf->offset, (size_t) count) ;
	vf->offset += count ;
	if (vf->offset > vf->max_access)
		vf->max_access = vf->offset ;
	return count ;
}

static sf_count_t
track_write (const void *ptr, sf_count_t count, void *user_data)
{
	(void) ptr ; (void) count ; (void) user_data ;
	return 0 ;
}

static sf_count_t
track_tell (void *user_data)
{
	VIO_DATA *vf = (VIO_DATA *) user_data ;
	return vf->offset ;
}

static void
track_init (VIO_DATA *vf, SF_VIRTUAL_IO *vio, const uint8_t *data, size_t size)
{
	vio->get_filelen = track_get_filelen ;
	vio->seek = track_seek ;
	vio->read = track_read ;
	vio->write = track_write ;
	vio->tell = track_tell ;

	vf->data = data ;
	vf->length = (sf_count_t) size ;
	vf->offset = 0 ;
	vf->max_access = 0 ;
}

#endif
