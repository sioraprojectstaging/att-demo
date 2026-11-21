import cv2
import numpy as np
import threading
import logging
from PIL import Image
from PIL.ExifTags import TAGS
import io

# Configure logger for this module
logger = logging.getLogger(__name__)

# Lazy import to allow migrations to run without insightface installed
FaceAnalysis = None

def _load_insightface():
    global FaceAnalysis
    if FaceAnalysis is None:
        try:
            from insightface.app import FaceAnalysis as FA
            FaceAnalysis = FA
        except ImportError:
            raise ImportError("insightface is not installed. Run: pip install insightface onnxruntime")
    return FaceAnalysis


MODEL_PACK = 'buffalo_l'
# The two buffalo_l files needed for detection + recognition.
MODEL_FILES = ('det_10g.onnx', 'w600k_r50.onnx')


def _ensure_model_files(root, base_url):
    """
    Make sure <root>/models/buffalo_l/ holds the detection and recognition
    models. On Vercel the filesystem is read-only except /tmp, so on a cold
    start the files are streamed from FACE_MODEL_BASE_URL into /tmp.

    If base_url is empty, insightface's own downloader is left to fetch the
    full pack (fine locally; too large for Vercel's /tmp).
    """
    import os
    import requests

    model_dir = os.path.join(os.path.expanduser(root), 'models', MODEL_PACK)
    missing = [f for f in MODEL_FILES if not os.path.exists(os.path.join(model_dir, f))]
    if not missing:
        return
    if not base_url:
        if os.path.isdir(model_dir):
            raise RuntimeError(
                f"Face model files {missing} are missing from {model_dir} and "
                "FACE_MODEL_BASE_URL is not set."
            )
        return

    os.makedirs(model_dir, exist_ok=True)
    for filename in missing:
        target = os.path.join(model_dir, filename)
        partial = target + '.part'
        url = f"{base_url}/{filename}"
        logger.info(f"Downloading face model {url}")
        with requests.get(url, stream=True, timeout=120) as response:
            response.raise_for_status()
            with open(partial, 'wb') as fh:
                for chunk in response.iter_content(chunk_size=4 * 1024 * 1024):
                    fh.write(chunk)
        os.replace(partial, target)


def _apply_exif_orientation(pil_image):
    """
    Apply EXIF orientation to PIL image.
    Mobile phones often store images rotated with EXIF metadata.
    This function rotates the image to the correct orientation.
    """
    try:
        exif = pil_image._getexif()
        if exif is None:
            return pil_image
        
        # Find the orientation tag
        orientation_key = None
        for tag_id, tag_name in TAGS.items():
            if tag_name == 'Orientation':
                orientation_key = tag_id
                break
        
        if orientation_key is None or orientation_key not in exif:
            return pil_image
        
        orientation = exif[orientation_key]
        
        # Apply rotation based on EXIF orientation value
        if orientation == 2:
            pil_image = pil_image.transpose(Image.FLIP_LEFT_RIGHT)
        elif orientation == 3:
            pil_image = pil_image.rotate(180, expand=True)
        elif orientation == 4:
            pil_image = pil_image.transpose(Image.FLIP_TOP_BOTTOM)
        elif orientation == 5:
            pil_image = pil_image.transpose(Image.FLIP_LEFT_RIGHT).rotate(270, expand=True)
        elif orientation == 6:
            pil_image = pil_image.rotate(270, expand=True)
        elif orientation == 7:
            pil_image = pil_image.transpose(Image.FLIP_LEFT_RIGHT).rotate(90, expand=True)
        elif orientation == 8:
            pil_image = pil_image.rotate(90, expand=True)
        
        logger.debug(f"Applied EXIF orientation correction: {orientation}")
        return pil_image
    except Exception as e:
        logger.debug(f"Could not read EXIF orientation: {e}")
        return pil_image


def load_image_correctly(image_file):
    """
    Decodes image, applies EXIF rotation, returns OpenCV BGR image.
    """
    if hasattr(image_file, 'read'):
        image_file.seek(0)
        pil_img = Image.open(image_file)
    else:
        pil_img = Image.open(io.BytesIO(image_file))

    logger.debug(f"Loaded image: mode={pil_img.mode}, size={pil_img.size}")
    
    pil_img = _apply_exif_orientation(pil_img)
    pil_img = pil_img.convert("RGB")

    img = np.array(pil_img)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


class FaceHandler:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        """Thread-safe singleton access"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        logger.info("Initializing InsightFace model (buffalo_l)... this may take a moment.")
        # 'buffalo_l' is a good balance of speed/accuracy.
        # Only detection + recognition are loaded: they are all this module uses
        # (bbox + embedding), and skipping the landmark/gender-age models saves
        # ~150 MB and startup time. Embeddings are identical to the full pack,
        # so faces enrolled before this change still match.
        from django.conf import settings
        root = settings.FACE_MODEL_ROOT
        _ensure_model_files(root, settings.FACE_MODEL_BASE_URL)
        FA = _load_insightface()
        self.app = FA(
            name=MODEL_PACK,
            root=root,
            allowed_modules=['detection', 'recognition'],
            providers=['CPUExecutionProvider'],
        )
        self.app.prepare(ctx_id=0, det_size=(640, 640))
        logger.info("InsightFace model loaded successfully.")

    def process_image(self, image_file):
        """
        Accepts a Django UploadedFile (or bytes), converts to OpenCV format,
        detects faces, and returns the embedding of the largest face.
        
        This method properly handles EXIF orientation from mobile phone cameras.
        Includes robust detection with lower threshold and lighting compensation.
        """
        import time
        start_time = time.time()
        
        # # DEBUG: Uncomment to save images for debugging (DO NOT USE IN PRODUCTION)
        # import os
        # from datetime import datetime
        # debug_dir = "/tmp/face_debug"
        # os.makedirs(debug_dir, exist_ok=True)
        # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # try:
        #     if hasattr(image_file, 'read'):
        #         image_file.seek(0)
        #         raw_bytes = image_file.read()
        #         image_file.seek(0)
        #         raw_path = os.path.join(debug_dir, f"{timestamp}_raw.bin")
        #         with open(raw_path, 'wb') as f:
        #             f.write(raw_bytes)
        #         logger.info(f"DEBUG: Saved raw image to {raw_path} ({len(raw_bytes)} bytes)")
        # except Exception as e:
        #     logger.error(f"DEBUG: Error saving raw image: {e}")
        
        try:
            img = load_image_correctly(image_file)
            load_time = time.time() - start_time
            logger.debug(f"Image load time: {load_time:.3f}s")
            
            if img is None:
                logger.error("load_image_correctly returned None")
                return None

            # Normalize size (InsightFace sweet spot)
            h, w = img.shape[:2]
            logger.debug(f"Image dimensions after load: {w}x{h}, channels: {img.shape[2] if len(img.shape) > 2 else 1}")
            
            # # DEBUG: Uncomment to save loaded image for debugging
            # try:
            #     debug_img_path = os.path.join(debug_dir, f"{timestamp}_loaded.jpg")
            #     cv2.imwrite(debug_img_path, img)
            #     logger.info(f"DEBUG: Saved loaded image to {debug_img_path}")
            # except Exception as e:
            #     logger.error(f"DEBUG: Error saving loaded image: {e}")
            
            if max(h, w) > 1280:
                scale = 1280 / max(h, w)
                img = cv2.resize(img, None, fx=scale, fy=scale)
                logger.info(f"Resized image to: {img.shape[1]}x{img.shape[0]}")

            detect_start = time.time()
            
            # Standard detection (det_thresh removed - not supported in this InsightFace version)
            faces = self.app.get(img)
            detect_time = time.time() - detect_start
            logger.info(f"Face detection: time={detect_time:.3f}s, found={len(faces) if faces else 0}")

            # If no faces found, try with enhanced image (histogram equalization for lighting issues)
            if not faces:
                logger.info("No faces with standard detection, trying with enhanced image...")
                
                # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) for lighting correction
                lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
                l_channel, a_channel, b_channel = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))  # Increased clip limit
                l_channel = clahe.apply(l_channel)
                enhanced_lab = cv2.merge([l_channel, a_channel, b_channel])
                enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
                
                # Retry with enhanced image
                faces = self.app.get(enhanced_img)
                logger.info(f"Enhanced detection found {len(faces) if faces else 0} face(s)")
                
                if faces:
                    img = enhanced_img  # Use enhanced image for embedding extraction
                else:
                    # Last resort: try gamma correction for very dark images
                    logger.info("Trying gamma correction for dark images...")
                    gamma = 1.5
                    inv_gamma = 1.0 / gamma
                    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
                    gamma_img = cv2.LUT(img, table)
                    faces = self.app.get(gamma_img)
                    logger.info(f"Gamma-corrected detection found {len(faces) if faces else 0} face(s)")
                    if faces:
                        img = gamma_img

            if not faces:
                logger.warning("No faces detected after all enhancement attempts.")
                return None

            # Largest face
            largest_face = max(
                faces,
                key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1])
            )
            
            bbox = largest_face.bbox
            det_score = largest_face.det_score if hasattr(largest_face, 'det_score') else 0.0
            total_time = time.time() - start_time
            logger.debug(f"Selected largest face at bbox: [{bbox[0]:.0f}, {bbox[1]:.0f}, {bbox[2]:.0f}, {bbox[3]:.0f}], det_score: {det_score:.3f}")
            logger.info(f"Total face processing time: {total_time:.3f}s")

            return largest_face.embedding.tolist()

        except Exception as e:
            logger.exception(f"Error processing image: {e}")
            return None

    def detect_spoof_single_image(self, image_file):
        """
        Basic anti-spoofing checks on a single image.
        Returns (is_live: bool, confidence: float, reason: str)
        """
        try:
            img = load_image_correctly(image_file)
            if img is None:
                logger.warning("Spoof check: Could not decode image")
                return False, 0.0, "Could not decode image"

            # Check 1: Image quality / blur detection
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            logger.debug(f"Spoof check - Laplacian variance (blur): {laplacian_var:.2f}")
            
            # Very low variance = likely a printed photo or screen
            # Threshold lowered to 12 to accommodate various phone cameras and lighting conditions
            if laplacian_var < 12:
                logger.warning(f"Spoof check failed: Image too flat/blurry (variance={laplacian_var:.2f})")
                return False, 0.3, "Full face not visible, retry"

            # Check 2: Detect screen/moiré patterns (high frequency noise)
            # FFT analysis for detecting screen patterns
            f_transform = np.fft.fft2(gray)
            f_shift = np.fft.fftshift(f_transform)
            magnitude_spectrum = 20 * np.log(np.abs(f_shift) + 1)
            
            # High energy in specific frequencies can indicate screen
            center = np.array(magnitude_spectrum.shape) // 2
            high_freq_region = magnitude_spectrum[
                center[0]-50:center[0]+50, 
                center[1]-50:center[1]+50
            ]
            high_freq_avg = np.mean(high_freq_region) if high_freq_region.size > 0 else 0
            
            # Check 3: Face detection with robust approach for challenging lighting
            faces = self.app.get(img)
            
            # If no faces found, try with enhanced image
            if not faces:
                lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
                l_channel, a_channel, b_channel = cv2.split(lab)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                l_channel = clahe.apply(l_channel)
                enhanced_lab = cv2.merge([l_channel, a_channel, b_channel])
                enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
                faces = self.app.get(enhanced_img)
                logger.debug(f"Spoof check - Enhanced detection found {len(faces) if faces else 0} face(s)")
            
            if not faces:
                logger.warning("Spoof check failed: No face detected")
                return False, 0.0, "Full face not visible, retry"

            largest_face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
            
            # Check face size (too small = possibly from a screen at distance)
            bbox = largest_face.bbox
            face_width = bbox[2] - bbox[0]
            face_height = bbox[3] - bbox[1]
            img_width = img.shape[1]
            
            face_ratio = face_width / img_width
            logger.debug(f"Spoof check - Face ratio: {face_ratio:.3f}, size: {face_width:.0f}x{face_height:.0f}")
            
            if face_ratio < 0.15:
                logger.warning(f"Spoof check failed: Face too small (ratio={face_ratio:.3f})")
                return False, 0.4, "Full face not visible, retry"

            # Check 4: Detection confidence score (lowered from 0.7 to 0.5 for glasses)
            det_score = largest_face.det_score if hasattr(largest_face, 'det_score') else 0.9
            logger.debug(f"Spoof check - Detection score: {det_score:.3f}")
            
            if det_score < 0.5:
                logger.warning(f"Spoof check failed: Low detection confidence ({det_score:.3f})")
                return False, det_score, "Full face not visible, retry"

            # Calculate overall liveness score
            liveness_score = min(1.0, (laplacian_var / 200) * 0.4 + det_score * 0.4 + face_ratio * 0.2)
            logger.debug(f"Spoof check - Liveness score: {liveness_score:.3f}")
            
            # Lowered threshold from 0.45 to 0.35 to reduce false rejections
            # Most real faces score 0.4+ even in poor lighting
            if liveness_score > 0.35:
                logger.info(f"Liveness check passed (score={liveness_score:.3f})")
                return True, liveness_score, "Liveness check passed"
            else:
                logger.warning(f"Spoof check failed: Possible spoof (score={liveness_score:.3f})")
                return False, liveness_score, "Full face not visible, retry"

        except Exception as e:
            logger.exception(f"Anti-spoof error: {e}")
            return False, 0.0, str(e)

    def validate_multi_frame(self, image_files, similarity_threshold=0.85):
        """
        Anti-spoofing using multiple frames.
        Checks that embeddings across frames are consistent but not IDENTICAL
        (real faces have micro-movements; photos are static).
        
        Args:
            image_files: List of 3+ image files
            similarity_threshold: Frames should be similar (same person) but not identical
            
        Returns:
            (is_live: bool, embedding: list, reason: str)
        """
        if len(image_files) < 3:
            return False, None, "Need at least 3 frames for anti-spoof validation"

        embeddings = []
        for img_file in image_files:
            emb = self.process_image(img_file)
            if emb is None:
                return False, None, "Face not detected in one or more frames"
            embeddings.append(np.array(emb))

        # Check similarity between consecutive frames
        similarities = []
        for i in range(len(embeddings) - 1):
            sim = np.dot(embeddings[i], embeddings[i+1]) / (
                np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[i+1])
            )
            similarities.append(sim)

        avg_similarity = np.mean(similarities)
        min_similarity = np.min(similarities)
        max_similarity = np.max(similarities)
        
        # Real faces: high similarity (same person) but with slight variance (movement)
        # Photo attacks: extremely high similarity (no movement) or very low (different angles don't match)
        
        if avg_similarity < similarity_threshold:
            return False, None, f"Frames don't match - possible different people (sim={avg_similarity:.3f})"
        
        # If ALL frames are nearly identical (>0.995), it's likely a static photo
        if min_similarity > 0.995:
            return False, None, "Frames too identical - possible photo attack"
        
        # Pass! Return the average embedding
        avg_embedding = np.mean(embeddings, axis=0)
        return True, avg_embedding.tolist(), f"Multi-frame validation passed (sim={avg_similarity:.3f})"

