# EchoMind Pupil & Gaze Demo

A standalone Windows app for a close-up USB eye camera. It detects a dark pupil locally and displays a green pupil box, an ellipse, a center cross, movement direction, and an in-app gaze pointer.

## Real camera gaze linked to EchoMind AR

1. Open **EchoMind Camera AR** on the desktop. Keep **Live camera**, **Two eyes / one camera**, and **Link camera to AR** selected. Select your camera and connect.
2. Select eye A and eye B, then complete **9-point calibration** on the monitor where you will use AR. The eye previews remain visible while calibrating. Real AR input stays paused until calibration succeeds.
3. Press **Esc** to return from the native calibration screen. Click **Open EchoMind AR ↗** if the webpage is not open. In Live camera mode, this button keeps the camera connected and opens the real-gaze page.
4. On that same monitor, choose **Camera gaze** on the webpage and click **Start fullscreen gaze**. The camera's calibrated screen coordinates now drive the page ring. Look at a dwell-enabled AR control to focus it; the existing simulated EEG attention and dwell threshold still decide when it activates.
5. Exit fullscreen or switch the webpage to **Mouse demo** to return to mouse presentation. Uncheck **Link camera to AR** to stop sending real gaze. No Windows mouse movement or automatic system clicks are performed.

Fullscreen is required because the native calibration uses the entire screen; a resized or moved browser window would otherwise shift the target coordinates. Use the same monitor used for calibration. Eye loss, stale frames, an unavailable camera, calibration mode, background browser windows, or leaving fullscreen pauses gaze interaction. Mouse movement does not override active Camera gaze mode.

The eye position is camera-derived; **EEG attention values remain simulated**. Only normalized gaze coordinates, capture freshness, and tracking status pass through the local connection. Camera images and pupil calibration samples never enter the webpage or leave this computer. Synthetic test inputs cannot drive the real camera link.

## AR linked demo

1. Open the **EchoMind AR Eye Demo** desktop shortcut, or choose **AR linked demo** at the top of the eye app and click **Open EchoMind AR ↗**.
2. Move the mouse over the EchoMind AR webpage. Its green ring follows the exact mouse position. The native window shows the corresponding gaze point and a virtual eye looking in the same direction.
3. Hold over an AR control to demonstrate the existing virtual EEG attention/intent confirmation. The mouse link does not bypass that confirmation.
4. Leaving or hiding the AR page pauses the simulated pointer. A stationary pointer stays active while the page is open and focused.

This mode is labeled **SIMULATED** and uses mouse coordinates, not a camera or measured gaze. No calibration is needed. Camera-only controls are disabled. Select **Live camera** to return to tracking; the previous eye crop and mirror setting are kept, but personal calibration must be repeated.

## Real binocular tracking: one camera, two eyes

1. Open the **EchoMind Binocular Camera** desktop shortcut, or select **Live camera** and **Two eyes / one camera** in the app. Position the camera so both eyes and their pupils are clearly visible at the same time. Select the camera and click **Connect** if needed.
2. Click **Select eye A** and draw around one whole eye in the full camera image. Then draw around the other eye when prompted. A and B are selection labels, not anatomical left/right. The regions must not overlap. After both are selected, the preview crops to include both eyes. You can reselect either region; **Esc** keeps the previous completed selection. **Reset eyes** restores the full view.
3. Wait for **A LOCK / B LOCK** and two green pupil boxes. Run **9-point calibration**, keeping your head and camera still. Both eyes are sampled from each frame and calibrated independently. The app averages the two mapped gaze positions only after calibration. A separate validation target checks each eye and the combined result; a poor eye cannot be hidden by averaging.
   The fullscreen calibration screen shows live **EYE A / EYE B** previews with pupil outlines and separate lock status. These fixed crops help you notice camera or head shifts. The panel moves above or below the target to keep it visible. Check alignment before starting; during sampling, keep looking at the green target. Missing video clears the previews instead of displaying a frozen eye image.
4. A blink, obstruction, missing video, or loss of either pupil pauses the gaze point. The remaining pupil may still have an outline, but the app does not invent a second measurement. Recalibrate after adjusting the camera, eye regions, mirroring, or tracking mode.

Binocular tracking can combine two measurements; it does not guarantee higher accuracy. This app still uses 2D pupil positions with a fixed head/camera setup. Check actual validation error with your own camera. A broad face view with tiny or blurred pupils can perform worse than a clear single-eye close-up. There is no measured accuracy claim until real-user calibration and validation have been completed.

Keep the companion `Desktop/EchoMind-EEG-Demo/EchoMind_EEG_AR_Demo.exe` installed. **Open EchoMind AR** starts it if needed and opens the webpage in an independent window. The updated companion provides the mouse link. If the link says offline, reopen the companion and refresh the webpage. All communication stays on this computer.

## Camera tracking

1. Open `EchoMind_Pupil_Gaze_Demo.exe`. The app selects the device named exactly `USB Camera` when available. To use another camera, select it from the list and click **Connect**.
2. **Flip horizontally** is on by default to correct this USB Camera's mirrored image. The video, pupil overlay, and movement direction share the same orientation. Keep the camera still and the whole pupil clearly visible. Once the green box is steady, look at the center of the screen and click **Set center**. The pointer now shows relative pupil movement.
3. Click **9-point calibration**. Press **Space** to begin and look at each green point for about 2.3 seconds. Keep your head and camera still. A separate validation point follows. If there are not enough valid samples, the app waits for you to press Space and retry that point; blinks do not count as valid samples.
4. When calibration passes, the green pointer follows your estimated gaze in the fullscreen demo. Press **Esc** to return to the main window.

The gaze pointer belongs to this app. It does not move the Windows mouse or click automatically. Calibration lasts for the current session. Recalibrate after reopening the app, moving the camera, or changing mirroring, the crop, or detection settings. Clicking **Set center** after calibration returns to relative pupil mode.

## Crop and detection controls

- **Crop eye:** Click the button and drag a rectangle on the full camera view. Release the mouse to crop and enlarge that region while keeping its proportions. The pupil overlay stays aligned. Include the whole eye with space for pupil movement; avoid a tight crop around the pupil itself. Exclude dark borders and lashes where possible. Clicking Crop eye again temporarily restores the full frame for a new selection. Press **Esc** to cancel and keep the previous crop. Click **Reset crop** to restore the full view.
- **Flip horizontally:** Enabled by default. The image is flipped before pupil detection, so the preview and direction match. Turn it off if a different camera orientation requires it. Changing this setting also mirrors the crop coordinates and clears calibration. Set the center or calibrate again. Calibrated coordinates are not flipped a second time.
- **Auto threshold:** Enabled by default. If lighting or reflections cause incorrect detection, turn it off and adjust **Threshold**. The green box should surround the dark pupil, not the entire iris.
- **Motion gain:** Adjusts relative pupil movement before calibration. After calibration, the personal calibration determines the mapping.
- **NOT LOCKED:** Check that the pupil is fully visible, in focus, and not covered by an eyelid. The app hides the pointer when detection is lost.
- **Camera connection error:** Close the Windows camera settings preview, camera apps, or video calls using USB Camera, then reconnect. Click **Refresh** after unplugging or reconnecting the device. The app does not automatically switch to another camera.

## What the demo measures

This demo assumes a fixed camera and a clear view of one eye or two separately selected eye regions. It uses each pupil's 2D movement to estimate relative direction, then maps it to the screen after personal calibration. Head movement, camera slip, lighting changes, pupil size changes, and occlusion can cause errors. Recalibrate whenever the camera or wearing position changes.

**Quality 0-100** is a heuristic score based on contour shape, pupil brightness, and surrounding contrast. It is **not gaze accuracy or measurement precision**. Calibration validation error is a diagnostic for this session, not a guarantee of long-term accuracy. Similar dark round objects can still produce false detections; limit the eye region and check the green outline.

## Local processing and privacy

Camera frames are processed locally. The app does not upload eye video, record video, or save photographs. Frames and calibration samples stay in memory and are released on exit. No account or cloud model is needed. The linked demonstration uses local communication with the EchoMind AR demo. Installing source dependencies for the first time requires internet access to download packages. The app does not access KeyShot projects, renders, or license files.

## Algorithm and sources

The detector uses OpenCV: grayscale conversion, multiple dark-region thresholds, contour and ellipse fitting, boundary/shape/contrast checks, and display smoothing. NumPy fits an affine 2D calibration from nine sampled targets followed by an independent validation point. No trained weights or training dataset are required.

- [OpenCV thresholding](https://docs.opencv.org/4.x/d7/d4d/tutorial_py_thresholding.html)
- [OpenCV contours and ellipse fitting](https://docs.opencv.org/4.13.0/dd/d49/tutorial_py_contour_features.html)
- [Pupil Labs calibration practices](https://docs.pupil-labs.com/core/best-practices/)

## Run from source and verify

Use 64-bit Python 3.12. Install `requirements.txt`, then run `python app.py`.

Run `python -m unittest discover -s tests -v` to verify pupil detection, reflections, lashes, iris rejection, missing frames, coordinate transforms, and degenerate calibration cases.

`python app.py --synthetic` is a development test mode. It displays a clearly labeled synthetic eye and does not open a camera.

`python app.py --binocular` starts real two-eye camera mode. Add `--camera-ar --open-ar` to enable the real gaze link and open AR. `--synthetic --binocular` is a development-only two-eye fixture and is labeled synthetic throughout; its frames are blocked from the real gaze publisher.

`python app.py --ar-demo --open-ar` starts the linked presentation. `--ar-port 8878` can select a separate local test server; the normal companion uses port 8765.

To package the app, install `pyinstaller` and run `python -m PyInstaller EchoMind_Pupil_Gaze_Demo.spec`. The resulting executable includes its runtime dependencies; users do not need to install Python.
