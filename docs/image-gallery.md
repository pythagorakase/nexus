# Image Gallery System

## Overview

The image gallery system allows uploading and managing multiple images for characters and places. Each entity can have multiple images, with one designated as the "main" image for thumbnails.

## Architecture

### Database Schema

Images are stored in the `assets` schema, separate from core narrative data:

```sql
-- Character images
assets.character_images (
  id BIGSERIAL PRIMARY KEY,
  character_id BIGINT REFERENCES characters(id) ON DELETE CASCADE,
  file_path TEXT NOT NULL,
  is_main INTEGER DEFAULT 0,  -- 0 = false, 1 = true
  display_order INTEGER DEFAULT 0,
  uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
)

-- Place images (same structure)
assets.place_images (
  id BIGSERIAL PRIMARY KEY,
  place_id BIGINT REFERENCES places(id) ON DELETE CASCADE,
  file_path TEXT NOT NULL,
  is_main INTEGER DEFAULT 0,
  display_order INTEGER DEFAULT 0,
  uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
)
```

### File Storage

- **Location**: Filesystem storage in `.gitignored` directories
- **Paths**:
  - Characters: `/character_portraits/{character_id}/`
  - Places: `/place_images/{place_id}/`
- **Naming**: `{timestamp}_{sanitized_filename}{ext}`
- **Validation**:
  - File types: PNG, JPEG, JPG only
  - Max size: 15MB per file
  - Filename sanitization: alphanumeric, dash, underscore only

### API Endpoints

#### Character Images
- `GET /api/characters/:id/images` - List all images
- `POST /api/characters/:id/images` - Upload images (up to 10)
- `PUT /api/characters/:id/images/:imageId/main` - Set main image
- `DELETE /api/characters/:id/images/:imageId` - Delete image

#### Place Images
- `GET /api/places/:id/images` - List all images
- `POST /api/places/:id/images` - Upload images (up to 10)
- `PUT /api/places/:id/images/:imageId/main` - Set main image
- `DELETE /api/places/:id/images/:imageId` - Delete image

## Frontend Components

### ImageGalleryModal

Shared modal component used by both Characters and Places tabs:

- Full-size image viewer with navigation arrows
- Thumbnail grid sidebar
- Upload, set main, and delete actions
- Keyboard navigation support

### Integration

- **CharactersTab**: Flexible aspect ratio thumbnail (128px × 160px max)
- **MapTab**: Same thumbnail styling in place detail dialogs
- Click thumbnail to open gallery
- Upload button for quick access

## Security & Validation

### Upload Validation
- MIME type checking (image/png, image/jpeg, image/jpg)
- File extension validation (.png, .jpg, .jpeg)
- 15MB file size limit enforced by multer
- Filename sanitization to prevent path traversal

### Error Handling
- 413 status for files exceeding size limit
- 400 status for invalid file types
- Descriptive error messages returned to client

## Workflow

1. **First Upload**: Automatically becomes main image
2. **Additional Uploads**: Added with auto-incrementing display_order
3. **Set Main**: Atomically unsets all other images, sets new main
4. **Delete**: Removes database record and deletes file from filesystem
5. **Delete Main**: No automatic reassignment (user must explicitly set new main)

## Future Enhancements

- Image compression/resizing on upload
- Thumbnail generation for faster gallery loading
- Drag-and-drop reordering
- Image captions/descriptions
- Object storage migration (S3-compatible)
