"""Live, fixed-region eye previews for the fullscreen calibration canvas.

Uses the same already-mirrored frame and per-eye coordinates as tracking.
No image is recorded, and the preview never changes calibration samples.
"""
import math

import cv2
import numpy as np
from PIL import Image, ImageTk


def preview_bounds(width, height, target=None):
    """Keep a centered panel opposite the calibration target's vertical half."""
    panel_w = min(720, max(160, width-40))
    panel_h = min(240, max(132, int(height*.23)))
    x = (width-panel_w)/2
    y = height-64-panel_h if target is not None and target[1] < .5 else 54
    return x, y, panel_w, panel_h


def draw_calibration_preview(app, now, target=None):
    """Draw both real eye crops and return the panel bounds, or None."""
    app.calibration_preview_photos = []
    if not app.is_binocular() or app.is_linked():
        return None
    canvas = app.full_canvas
    width, height = canvas.winfo_width(), canvas.winfo_height()
    x, y, panel_w, panel_h = preview_bounds(width, height, target)
    canvas.create_rectangle(x, y, x+panel_w, y+panel_h, fill="#192326", outline="#36504e", width=1)
    title = "SYNTHETIC EYE ALIGNMENT" if app.synthetic else "LIVE EYE ALIGNMENT"
    canvas.create_text(x+12, y+17, text=title, anchor="w", fill="#64c7c0", font=("Consolas", 11, "bold"))
    canvas.create_text(x+panel_w/2, y+panel_h-15,
                       text="Keep your head and camera still. Look at the green target during sampling.",
                       fill="#90a6a4", font=("Segoe UI", 9), width=panel_w-24, justify="center")

    frame = app.last_frame
    fresh = frame is not None and 0 <= now-app.last_frame_time <= .6
    detections = (app.binocular_tracker.left, app.binocular_tracker.right)
    card_w = (panel_w-36)/2
    for index, (roi, det) in enumerate(zip(app.eye_rois, detections)):
        card_x, card_y = x+12+index*(card_w+12), y+34
        image_y, image_h = card_y+23, panel_h-92
        canvas.create_rectangle(card_x, image_y, card_x+card_w, image_y+image_h,
                                fill="#080d0e", outline="#2a393c")
        valid = fresh and roi is not None
        locked = valid and det is not None and det.quality >= .55
        status = "LOCKED" if locked else "LOW QUALITY" if valid and det is not None else "NO LOCK" if valid else "NO VIDEO" if not fresh else "SELECT REGION"
        color = "#9cff57" if locked else "#ffc77a"
        canvas.create_text(card_x, card_y+9, text=f"EYE {'AB'[index]}", anchor="w",
                           fill="#ecf2ed", font=("Consolas", 10, "bold"))
        canvas.create_text(card_x+card_w, card_y+9, text=status, anchor="e",
                           fill=color, font=("Consolas", 10, "bold"))
        if not valid:
            canvas.create_text(card_x+card_w/2, image_y+image_h/2,
                               text="Waiting for video" if not fresh else "Select eye region in the main window",
                               fill="#90a6a4", width=card_w-16, font=("Segoe UI", 10))
            continue
        h, w = frame.shape[:2]
        left, top = int(roi[0]*w), int(roi[1]*h)
        right, bottom = int(roi[2]*w), int(roi[3]*h)
        crop = frame[top:bottom, left:right]
        if not crop.size:
            continue
        scale = min(card_w/crop.shape[1], image_h/crop.shape[0])
        dw, dh = max(1, round(crop.shape[1]*scale)), max(1, round(crop.shape[0]*scale))
        ox, oy = card_x+(card_w-dw)/2, image_y+(image_h-dh)/2
        rgb = cv2.cvtColor(cv2.resize(crop, (dw, dh)), cv2.COLOR_BGR2RGB)
        photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        app.calibration_preview_photos.append(photo)
        canvas.create_image(ox, oy, anchor="nw", image=photo)
        # The crop is fixed to the selected eye region, never centered on the
        # moving pupil. This preserves visible head/camera shifts in the image.
        if det is not None:
            cx, cy = ox+(det.center[0]-left)*scale, oy+(det.center[1]-top)*scale
            bx, by, bw, bh = det.bbox
            canvas.create_rectangle(max(ox, ox+(bx-left)*scale-3), max(oy, oy+(by-top)*scale-3),
                                    min(ox+dw, ox+(bx+bw-left)*scale+3), min(oy+dh, oy+(by+bh-top)*scale+3),
                                    outline=color, width=2)
            angle = math.radians(det.angle)
            pts = []
            for t in np.linspace(0, math.tau, 40):
                ex, ey = det.axes[0]*.5*math.cos(t)*scale, det.axes[1]*.5*math.sin(t)*scale
                pts.extend((cx+ex*math.cos(angle)-ey*math.sin(angle), cy+ex*math.sin(angle)+ey*math.cos(angle)))
            canvas.create_line(*pts, fill="#ecf2ed", width=1)
            canvas.create_line(cx-5, cy, cx+5, cy, fill="#ecf2ed", width=2)
            canvas.create_line(cx, cy-5, cx, cy+5, fill="#ecf2ed", width=2)
    return x, y, panel_w, panel_h
