import { useState, useRef } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Upload, Star, Trash2, X, ChevronLeft, ChevronRight } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";

export interface ImageData {
  id: number;
  filePath: string;
  isMain: number;
  displayOrder: number;
}

interface ImageGalleryModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  images: ImageData[];
  entityId: number;
  entityType: "character" | "place";
  onUpload: (files: FileList) => Promise<void>;
  onSetMain: (imageId: number) => Promise<void>;
  onDelete: (imageId: number) => Promise<void>;
}

export function ImageGalleryModal({
  open,
  onOpenChange,
  images,
  entityId,
  entityType,
  onUpload,
  onSetMain,
  onDelete,
}: ImageGalleryModalProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedImage = images[selectedIndex];
  const mainImage = images.find((img) => img.isMain === 1);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    try {
      await onUpload(files);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } finally {
      setUploading(false);
    }
  };

  const handleSetMain = async () => {
    if (!selectedImage) return;
    await onSetMain(selectedImage.id);
  };

  const handleDelete = async () => {
    if (!selectedImage) return;
    const confirmDelete = window.confirm("Are you sure you want to delete this image?");
    if (!confirmDelete) return;

    await onDelete(selectedImage.id);
    if (selectedIndex >= images.length - 1) {
      setSelectedIndex(Math.max(0, images.length - 2));
    }
  };

  const handlePrevious = () => {
    setSelectedIndex((prev) => (prev > 0 ? prev - 1 : images.length - 1));
  };

  const handleNext = () => {
    setSelectedIndex((prev) => (prev < images.length - 1 ? prev + 1 : 0));
  };

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl h-[80vh] flex flex-col font-mono">
        <DialogHeader>
          <DialogTitle className="text-primary terminal-glow">
            {entityType === "character" ? "Character" : "Place"} Images
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 flex gap-4 min-h-0">
          {/* Main image viewer */}
          <div className="flex-1 flex flex-col gap-2">
            {images.length > 0 ? (
              <>
                <div className="flex-1 relative bg-muted/20 rounded-md overflow-hidden flex items-center justify-center">
                  {selectedImage && (
                    <img
                      src={selectedImage.filePath}
                      alt={`Image ${selectedIndex + 1}`}
                      className="max-w-full max-h-full object-contain"
                    />
                  )}

                  {/* Navigation arrows */}
                  {images.length > 1 && (
                    <>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="absolute left-2 top-1/2 -translate-y-1/2 bg-background/80 hover:bg-background"
                        onClick={handlePrevious}
                      >
                        <ChevronLeft className="h-6 w-6" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="absolute right-2 top-1/2 -translate-y-1/2 bg-background/80 hover:bg-background"
                        onClick={handleNext}
                      >
                        <ChevronRight className="h-6 w-6" />
                      </Button>
                    </>
                  )}
                </div>

                {/* Action buttons */}
                <div className="flex gap-2 justify-between items-center">
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleSetMain}
                      disabled={selectedImage?.isMain === 1}
                      className="font-mono"
                    >
                      <Star className={`h-4 w-4 mr-2 ${selectedImage?.isMain === 1 ? "fill-yellow-500 text-yellow-500" : ""}`} />
                      {selectedImage?.isMain === 1 ? "Main Image" : "Set as Main"}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleDelete}
                      className="font-mono text-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Delete
                    </Button>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {selectedIndex + 1} / {images.length}
                  </span>
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-muted-foreground">
                <div className="text-center">
                  <p className="text-sm mb-2">No images yet</p>
                  <p className="text-xs">Upload images to get started</p>
                </div>
              </div>
            )}
          </div>

          {/* Thumbnail sidebar */}
          <div className="w-48 flex flex-col gap-2">
            <Button
              onClick={handleUploadClick}
              disabled={uploading}
              className="font-mono w-full"
              size="sm"
            >
              <Upload className="h-4 w-4 mr-2" />
              {uploading ? "Uploading..." : "Upload Images"}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/jpg"
              multiple
              onChange={handleFileChange}
              className="hidden"
            />

            <ScrollArea className="flex-1">
              <div className="grid grid-cols-2 gap-2">
                {images.map((image, index) => (
                  <button
                    key={image.id}
                    onClick={() => setSelectedIndex(index)}
                    className={`relative aspect-square rounded-md overflow-hidden border-2 transition-colors ${
                      index === selectedIndex
                        ? "border-primary"
                        : "border-border hover:border-primary/50"
                    }`}
                  >
                    <img
                      src={image.filePath}
                      alt={`Thumbnail ${index + 1}`}
                      className="w-full h-full object-cover"
                    />
                    {image.isMain === 1 && (
                      <div className="absolute top-1 right-1 bg-background/90 rounded-full p-1">
                        <Star className="h-3 w-3 fill-yellow-500 text-yellow-500" />
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </ScrollArea>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
