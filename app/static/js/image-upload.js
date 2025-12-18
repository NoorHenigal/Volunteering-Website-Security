/**
 * Image Upload Component
 * Provides image cropping, zooming, and upload functionality for
 * profile pictures, organization logos, and banner images.
 */

document.addEventListener('alpine:init', () => {
    Alpine.data('imageUploader', () => ({
        // Lazy initialization - only set when needed
        endpointUrl: null,
        uploadName: 'file',
        aspectRatio: 1,
        objectUrl: null, // Store object URL for cleanup

        // Reactive properties
        uploading: false,
        file: null,
        dragOver: false,
        error: null,
        cropperOpen: false,
        cropImage: null,
        scale: 1,
        minScale: 0.1,
        coverScale: 1,
        maxScale: 3,
        imageX: 0,
        imageY: 0,
        isDragging: false,
        startX: 0,
        startY: 0,
        initialImageX: 0,
        initialImageY: 0,

        init(endpointUrl, aspectRatio) {
            this.endpointUrl = endpointUrl;
            this.aspectRatio = aspectRatio;
        },

        triggerSelect() {
            this.$refs.fileInput.click();
        },

        onZoomChange(event) {
            const value = parseFloat(event.target.value);
            if (!Number.isFinite(value)) return;
            // Clamp zoom into configured range so slider and image stay in sync
            this.scale = Math.min(this.maxScale, Math.max(this.minScale, value));
        },

        // Calculate the minimum scale needed for the image to fully cover the crop area
        calculateCoverScale(imgWidth, imgHeight) {
            // Viewport dimensions (the visible crop area in the UI)
            const viewportWidth = this.aspectRatio === 1 ? 250 : 320;
            const viewportHeight = this.aspectRatio === 1 ? 250 : 180;

            // Scale needed to cover in each dimension
            const scaleX = viewportWidth / imgWidth;
            const scaleY = viewportHeight / imgHeight;

            // Use the larger scale to ensure full coverage
            return Math.max(scaleX, scaleY);
        },

        handleFile(event) {
            const file = event.target.files?.[0] || event.dataTransfer?.files?.[0];
            if (!file) return;

            if (!file.type.startsWith('image/')) {
                this.error = 'Please upload an image file';
                return;
            }

            if (file.size > 5 * 1024 * 1024) {
                this.error = 'Image must be smaller than 5MB';
                return;
            }

            this.error = null;
            this.file = file;

            // Use createObjectURL for instant file reference
            const objectUrl = URL.createObjectURL(file);
            const img = new Image();
            img.onload = () => {
                this.cropImage = img;
                this.objectUrl = objectUrl; // Store for cleanup

                this.coverScale = this.calculateCoverScale(img.width, img.height);
                this.minScale = this.coverScale * 0.5;
                this.maxScale = Math.max(3, this.coverScale * 3);
                this.scale = this.coverScale;

                this.cropperOpen = true;
                this.resetCrop();
            };
            img.onerror = () => {
                URL.revokeObjectURL(objectUrl);
                this.error = 'Failed to load image';
            };
            img.src = objectUrl;
        },

        resetCrop() {
            this.scale = this.coverScale;
            this.imageX = 0;
            this.imageY = 0;
        },

        closeCropper() {
            this.cropperOpen = false;
            if (this.objectUrl) {
                URL.revokeObjectURL(this.objectUrl);
                this.objectUrl = null;
            }
            this.cropImage = null;
            this.file = null;
        },

        startDrag(e) {
            this.isDragging = true;
            this.startX = e.type.includes('mouse') ? e.clientX : e.touches[0].clientX;
            this.startY = e.type.includes('mouse') ? e.clientY : e.touches[0].clientY;
            this.initialImageX = this.imageX;
            this.initialImageY = this.imageY;
        },

        onDrag(e) {
            if (!this.isDragging) return;
            e.preventDefault();
            const clientX = e.type.includes('mouse') ? e.clientX : e.touches[0].clientX;
            const clientY = e.type.includes('mouse') ? e.clientY : e.touches[0].clientY;

            this.imageX = this.initialImageX + (clientX - this.startX);
            this.imageY = this.initialImageY + (clientY - this.startY);
        },

        stopDrag() {
            this.isDragging = false;
        },

        async upload() {
            if (!this.cropImage) return;

            this.uploading = true;

            try {
                const blob = await this.getCroppedBlob();
                const formData = new FormData();
                formData.append(this.uploadName, blob, 'upload.webp');

                // Get CSRF token from cookie for header-based validation
                // This prevents the middleware from consuming the request body
                const csrfToken = document.cookie
                    .split('; ')
                    .find(row => row.startsWith('csrf_token='))
                    ?.split('=')[1];

                const response = await fetch(this.endpointUrl, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRF-Token': csrfToken || ''
                    }
                });

                if (response.ok) {
                    window.location.reload();
                } else {
                    const data = await response.json().catch(() => ({}));
                    this.error = data.detail || 'Upload failed';
                }
            } catch (err) {
                console.error(err);
                this.error = 'Something went wrong';
            } finally {
                this.uploading = false;
                this.closeCropper();
            }
        },

        getCroppedBlob() {
            return new Promise((resolve) => {
                const canvas = document.createElement('canvas');
                const targetWidth = this.aspectRatio === 1 ? 512 : 1280;
                const targetHeight = targetWidth / this.aspectRatio;

                canvas.width = targetWidth;
                canvas.height = targetHeight;

                const ctx = canvas.getContext('2d');
                ctx.clearRect(0, 0, canvas.width, canvas.height);

                // For circular crops (aspect_ratio === 1)
                if (this.aspectRatio === 1) {
                    // The visible crop area in the viewport is 250x250px circle
                    // We need to map this to the canvas (512x512)
                    const viewportCropSize = 250;
                    const canvasCropSize = 512;
                    const scale = canvasCropSize / viewportCropSize;

                    // Calculate where to draw the image on the canvas
                    // The image is centered and scaled
                    const centerX = canvas.width / 2;
                    const centerY = canvas.height / 2;

                    const drawnW = this.cropImage.width * this.scale * scale;
                    const drawnH = this.cropImage.height * this.scale * scale;

                    const destX = centerX + (this.imageX * scale) - (drawnW / 2);
                    const destY = centerY + (this.imageY * scale) - (drawnH / 2);

                    // Draw the image
                    ctx.drawImage(this.cropImage, 0, 0, this.cropImage.width, this.cropImage.height, destX, destY, drawnW, drawnH);

                    // Create circular mask
                    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                    const data = imageData.data;
                    const radius = canvas.width / 2;
                    const centerCanvasX = canvas.width / 2;
                    const centerCanvasY = canvas.height / 2;

                    for (let i = 0; i < data.length; i += 4) {
                        const pixelIndex = i / 4;
                        const x = pixelIndex % canvas.width;
                        const y = Math.floor(pixelIndex / canvas.width);

                        const dx = x - centerCanvasX;
                        const dy = y - centerCanvasY;
                        const distance = Math.sqrt(dx * dx + dy * dy);

                        if (distance > radius) {
                            data[i + 3] = 0; // Set alpha to 0 (transparent)
                        }
                    }

                    ctx.putImageData(imageData, 0, 0);
                } else {
                    // For non-circular crops (banners, etc.)
                    const viewportCropSize = 320;
                    const canvasCropSize = 1280;
                    const scale = canvasCropSize / viewportCropSize;

                    const centerX = canvas.width / 2;
                    const centerY = canvas.height / 2;

                    const drawnW = this.cropImage.width * this.scale * scale;
                    const drawnH = this.cropImage.height * this.scale * scale;

                    const destX = centerX + (this.imageX * scale) - (drawnW / 2);
                    const destY = centerY + (this.imageY * scale) - (drawnH / 2);

                    ctx.drawImage(this.cropImage, 0, 0, this.cropImage.width, this.cropImage.height, destX, destY, drawnW, drawnH);
                }

                canvas.toBlob(resolve, 'image/webp', 0.9);
            });
        }
    }));
});
