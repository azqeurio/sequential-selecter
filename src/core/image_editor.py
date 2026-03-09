import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

class PhotoEditor:
    @staticmethod
    def apply_edits(image: Image.Image, params: dict, lut_filter=None) -> Image.Image:
        """
        Apply adjustments using advanced NumPy Color Science (Lightroom-style math).
        Allows values from -100 to 100 with smooth, photographic roll-offs.
        """
        if image.mode != "RGB":
            image = image.convert("RGB")
            
        # --- 0. Geometry Transforms (Flip, Rotate, Crop) ---
        img = image.copy()
        if params.get('flip_h', False):
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        if params.get('flip_v', False):
            img = img.transpose(Image.FLIP_TOP_BOTTOM)

        rotate_val = params.get('rotate', 0)
        if rotate_val != 0:
            img = img.rotate(-rotate_val, resample=Image.BICUBIC, expand=True)

        lens_dist = params.get('lens_distortion', 0) / 100.0
        pers_h = params.get('pers_h', 0) / 100.0
        pers_v = params.get('pers_v', 0) / 100.0
        
        if lens_dist != 0 or pers_h != 0 or pers_v != 0:
            try:
                import cv2
                cv_img = np.array(img)
                h, w = cv_img.shape[:2]
                
                if lens_dist != 0:
                    f = max(w, h)
                    cx, cy = w / 2.0, h / 2.0
                    camera_matrix = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1]], dtype=np.float32)
                    
                    k1 = lens_dist * 0.2
                    dist_coeffs = np.array([k1, 0, 0, 0, 0], dtype=np.float32)
                    new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(camera_matrix, dist_coeffs, (w,h), 1, (w,h))
                    cv_img = cv2.undistort(cv_img, camera_matrix, dist_coeffs, None, new_camera_matrix)
                    
                    x, y, w_roi, h_roi = roi
                    if w_roi > 0 and h_roi > 0:
                        cv_img = cv_img[y:y+h_roi, x:x+w_roi]
                        h, w = cv_img.shape[:2]
                
                if pers_h != 0 or pers_v != 0:
                    pts1 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
                    
                    offset_x = (w * 0.4) * abs(pers_v)
                    offset_y = (h * 0.4) * abs(pers_h)
                    
                    if pers_v > 0:
                        pts2 = np.float32([[offset_x, 0], [w - offset_x, 0], [0, h], [w, h]])
                    elif pers_v < 0:
                        pts2 = np.float32([[0, 0], [w, 0], [offset_x, h], [w - offset_x, h]])
                    else:
                        pts2 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
                        
                    if pers_h > 0:
                        pts2[0][1] += offset_y
                        pts2[2][1] -= offset_y
                    elif pers_h < 0:
                        pts2[1][1] += offset_y
                        pts2[3][1] -= offset_y
                        
                    matrix = cv2.getPerspectiveTransform(pts1, pts2)
                    cv_img = cv2.warpPerspective(cv_img, matrix, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0))
                
                if cv_img.shape[0] > 0 and cv_img.shape[1] > 0:
                    img = Image.fromarray(cv_img)
                    
            except Exception as e:
                import traceback
                print(f"Geometry error: {e}\\n{traceback.format_exc()}")

        c_top = params.get('crop_top', 0) / 100.0
        c_bot = params.get('crop_bottom', 0) / 100.0
        c_left = params.get('crop_left', 0) / 100.0
        c_right = params.get('crop_right', 0) / 100.0
        
        if any(v > 0 for v in [c_top, c_bot, c_left, c_right]):
            w, h = img.size
            left = int(w * c_left)
            top = int(h * c_top)
            right = int(w * (1.0 - c_right))
            bottom = int(h * (1.0 - c_bot))
            if right > left and bottom > top:
                img = img.crop((left, top, right, bottom))

        # --- Base PIL Pre-Processing (Temp / Tint matrix is very fast in PIL) ---
        temp_val = params.get('temperature', 0) # -100 to 100
        tint_val = params.get('tint', 0)
        
        if temp_val != 0 or tint_val != 0:
            # Map -100..100 to subtle shifts
            r_scale = 1.0 + (temp_val * 0.003) + (tint_val * 0.001)
            g_scale = 1.0 - (tint_val * 0.002)
            b_scale = 1.0 - (temp_val * 0.003) + (tint_val * 0.001)
            # Normalize to preserve overall brightness
            m_sum = r_scale + g_scale + b_scale
            if m_sum > 0:
                mult = 3.0 / m_sum
                r_scale *= mult; g_scale *= mult; b_scale *= mult
            matrix = (r_scale, 0, 0, 0,  0, g_scale, 0, 0,  0, 0, b_scale, 0)
            img = img.convert("RGB", matrix)

        # ---------------------------------------------------------------------
        # ADVANCED NUMPY TONE MAPPING ENGINE
        # ---------------------------------------------------------------------
        arr = np.array(img, dtype=np.float32) / 255.0
        
        # 1. Exposure (EV Shift)
        # Lightroom maps +100 to about +3.0 EV, -100 to -3.0 EV
        exp_val = params.get('exposure', 0) / 100.0
        if exp_val != 0:
            ev_shift = exp_val * 3.0
            # Instead of naive multiplication, we use a curve that rolls off highlights
            # Base exposure shift
            arr = arr * (2.0 ** ev_shift)
            # Soft highlight roll-off (to prevent hard clipping)
            arr = 1.0 - np.exp(-arr) if ev_shift > 0 else arr

        # Calculate luminance for masks
        luminance = 0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]
        
        # 2. Highlights & Shadows (Luma-targeted)
        h_val = params.get('highlights', 0) / 100.0
        s_val = params.get('shadows', 0) / 100.0
        w_val = params.get('whites', 0) / 100.0
        b_val = params.get('blacks', 0) / 100.0
        
        if any(v != 0 for v in [h_val, s_val, w_val, b_val]):
            # Smooth weighting masks
            shadow_mask = np.clip(1.0 - (luminance * 2.0), 0, 1)  # peaks at 0, drops to 0 at 0.5
            highlight_mask = np.clip((luminance - 0.5) * 2.0, 0, 1) # peaks at 1, drops to 0 at 0.5
            
            # Apply targeted gamma/linear adjustments
            if s_val != 0:
                # Gamma shift for shadows
                gamma = 1.0 - (s_val * 0.5) # -100 -> 1.5 (darker), +100 -> 0.5 (brighter)
                gamma = max(0.1, gamma)
                arr_s = np.power(np.clip(arr, 1e-5, 1.0), gamma)
                mask = np.expand_dims(shadow_mask, -1)
                arr = arr * (1 - mask) + arr_s * mask
                
            if h_val != 0:
                # Gamma shift for highlights
                gamma = 1.0 + (h_val * 0.5) # -100 -> 0.5 (darker), +100 -> 1.5 (brighter reversed)
                gamma = max(0.1, gamma)
                # For highlights, we invert the image, apply gamma, and invert back
                inv_arr = 1.0 - arr
                arr_h = 1.0 - np.power(np.clip(inv_arr, 1e-5, 1.0), gamma)
                mask = np.expand_dims(highlight_mask, -1)
                arr = arr * (1 - mask) + arr_h * mask
                
            # Whites and Blacks (linear stretch from pivot points)
            if w_val != 0:
                arr = arr + (arr * w_val * 0.5 * np.expand_dims(highlight_mask, -1))
            if b_val != 0:
                arr = arr - ((1.0 - arr) * b_val * 0.5 * np.expand_dims(shadow_mask, -1))

        # 3. Contrast (S-Curve)
        cont_val = params.get('contrast', 0) / 100.0
        if cont_val != 0:
            # -1.0 to 1.0 range
            # We construct a smooth s-curve around mid-gray (0.5)
            # f(x, c) = (x - 0.5) * (1 + c) + 0.5 roughly
            # To prevent clipping, we use a rational function or trigonometric
            pivot = 0.5
            if cont_val > 0:
                # Increasing contrast
                arr = (arr - pivot) * (1.0 + cont_val * 1.5) + pivot
                arr = 0.5 * (np.sin(np.pi * (np.clip(arr, 0, 1) - 0.5)) + 1.0)
            else:
                # Decreasing contrast (flattening towards pivot)
                arr = (arr - pivot) * (1.0 + cont_val) + pivot

        # 4. Saturation (Vibrance-aware)
        sat_val = params.get('saturation', 0) / 100.0
        if sat_val != 0:
            # Recalculate luminance
            lum = 0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]
            lum_expanded = np.expand_dims(lum, -1)
            
            # Simple saturation: mix between luminance grayscale and color
            factor = 1.0 + sat_val * 1.5
            arr = lum_expanded + (arr - lum_expanded) * factor

        # 5. Clarity (Local Contrast via Unsharp Mask on Luminance)
        clarity_val = params.get('clarity', 0) / 100.0
        if clarity_val != 0:
            from PIL import ImageFilter as IF
            lum = 0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]
            # Create blurred luminance for local contrast
            lum_pil = Image.fromarray(np.clip(lum * 255, 0, 255).astype(np.uint8))
            blurred = np.array(lum_pil.filter(IF.GaussianBlur(radius=15)), dtype=np.float32) / 255.0
            # High-pass = original - blurred
            high_pass = lum - blurred
            # Apply clarity as local contrast boost
            detail = np.expand_dims(high_pass, -1) * clarity_val * 1.5
            arr = arr + detail

        # 6. Dehaze (Dark Channel Prior)
        dehaze_val = params.get('dehaze', 0) / 100.0
        if dehaze_val != 0:
            # Estimate atmospheric light from dark channel
            dark_ch = np.min(arr, axis=2)
            # Estimate airlight as the brightest pixel in the dark channel
            airlight = np.percentile(dark_ch, 99.9)
            airlight = max(airlight, 0.1)
            # Transmission map
            t = 1.0 - dehaze_val * 0.8 * (dark_ch / airlight)
            t = np.clip(t, 0.1, 1.0)
            t_expanded = np.expand_dims(t, -1)
            # Recover scene radiance
            arr = (arr - airlight) / t_expanded + airlight
            
        # 7. Sharpness (High-Pass Sharpening)
        sharp_val = params.get('sharpness', 0) / 100.0
        if sharp_val != 0:
            from PIL import ImageFilter as IF
            # Convert to PIL for gaussian blur
            temp_img = Image.fromarray(np.clip(arr * 255, 0, 255).astype(np.uint8))
            blurred = np.array(temp_img.filter(IF.GaussianBlur(radius=2)), dtype=np.float32) / 255.0
            # High-pass detail
            detail = arr - blurred
            arr = arr + detail * sharp_val * 2.0

        # 8. Noise Reduction (Non-Local Means)
        nr_val = params.get('noise_reduction', 0)
        if nr_val > 0:
            try:
                import cv2
                # Map 0-100 to h=3-15 for NLMeans
                h_strength = 3 + (nr_val / 100.0) * 12
                # Convert to uint8 for NLMeans
                arr_u8 = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
                denoised = cv2.fastNlMeansDenoisingColored(
                    arr_u8,
                    None,
                    h_strength,
                    h_strength,
                    7,
                    21,
                )
                arr = denoised.astype(np.float32) / 255.0
            except Exception:
                # OpenCV unavailable or build/signature mismatch: skip NR.
                pass

        # Base clamp before moving back to PIL
        arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)

        # 5. Effects (Vignette) & LUT
        vig_val = params.get('vignette', 0)
        if vig_val != 0:
            # Generating vignette mask in PIL is sometimes faster for high res
            # Or we can do it in numpy. We'll do a simple numpy radial gradient
            w, h = img.size
            X, Y = np.meshgrid(np.linspace(-1, 1, w), np.linspace(-1, 1, h))
            radius = np.sqrt(X**2 + Y**2)
            # Smoothstep
            radius = np.clip(radius, 0, 1.5)
            
            # vig_val < 0 = dark corners, vig_val > 0 = white corners
            amt = vig_val / 100.0
            
            # Make the mask
            mask = 1.0 - (radius * 0.7)**2 # Central brightness
            mask = np.clip(mask, 0, 1)
            
            arr = np.array(img, dtype=np.float32)
            if amt < 0:
                # Darken (-amt is positive)
                darkness = 1.0 + amt * (1.0 - mask)
                arr = arr * np.expand_dims(darkness, -1)
            else:
                # Lighten
                lightness = amt * (1.0 - mask) * 255.0
                arr = arr + np.expand_dims(lightness, -1)
                
            arr = np.clip(arr, 0, 255).astype(np.uint8)
            img = Image.fromarray(arr)

        if lut_filter:
            img = img.filter(lut_filter)

        return img

    @staticmethod
    def load_cube_lut(path):
        """Standard method to load a 3D .cube LUT file via PIL."""
        from PIL import ImageFilter
        try:
            with open(path, 'r') as f:
                lines = f.readlines()
            
            size = 0
            table = []
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('LUT_3D_SIZE'):
                    size = int(line.split()[1])
                elif line.startswith('TITLE') or line.startswith('DOMAIN'):
                    continue
                else:
                    parts = line.split()
                    if len(parts) == 3:
                        table.append(float(parts[0]))
                        table.append(float(parts[1]))
                        table.append(float(parts[2]))
                        
            if size > 0 and len(table) == size * size * size * 3:
                return ImageFilter.Color3DLUT(size, table)
        except Exception as e:
            print(f"Failed to load LUT: {e}")
        return None
