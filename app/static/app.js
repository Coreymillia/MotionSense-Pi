const initialStatus = JSON.parse(document.getElementById("initial-status").textContent);

const captureButton = document.getElementById("capture-button");
const refreshButton = document.getElementById("refresh-button");
const cameraSourceSelect = document.getElementById("camera-source-select");
const cameraSourceButton = document.getElementById("camera-source-button");
const networkCameraUrl = document.getElementById("network-camera-url");
const networkCameraButton = document.getElementById("network-camera-button");
const captureResolution = document.getElementById("capture-resolution");
const captureLighting = document.getElementById("capture-lighting");
const captureWhiteBalance = document.getElementById("capture-white-balance");
const captureDenoise = document.getElementById("capture-denoise");
const captureAutofocusMode = document.getElementById("capture-autofocus-mode");
const captureAutofocusRange = document.getElementById("capture-autofocus-range");
const captureLensPosition = document.getElementById("capture-lens-position");
const captureBrightness = document.getElementById("capture-brightness");
const captureContrast = document.getElementById("capture-contrast");
const captureSaturation = document.getElementById("capture-saturation");
const captureSharpness = document.getElementById("capture-sharpness");
const motionPollInterval = document.getElementById("motion-poll-interval");
const motionCooldown = document.getElementById("motion-cooldown");
const motionThreshold = document.getElementById("motion-threshold");
const captureBurstCount = document.getElementById("capture-burst-count");
const settingsButton = document.getElementById("settings-button");
const timerMode = document.getElementById("timer-mode");
const timerIntervalValue = document.getElementById("timer-interval-value");
const timerIntervalUnit = document.getElementById("timer-interval-unit");
const timerDurationValue = document.getElementById("timer-duration-value");
const timerDurationUnit = document.getElementById("timer-duration-unit");
const timerStartButton = document.getElementById("timer-start-button");
const timerStopButton = document.getElementById("timer-stop-button");
const rotateButton = document.getElementById("rotate-button");
const motionStartButton = document.getElementById("motion-start-button");
const motionStopButton = document.getElementById("motion-stop-button");
const stormwatchStartButton = document.getElementById("stormwatch-start-button");
const stormwatchStopButton = document.getElementById("stormwatch-stop-button");
const stormwatchPollInterval = document.getElementById("stormwatch-poll-interval");
const stormwatchCooldown = document.getElementById("stormwatch-cooldown");
const stormwatchScoreTrigger = document.getElementById("stormwatch-score-trigger");
const stormwatchHotPixelThreshold = document.getElementById("stormwatch-hot-pixel-threshold");
const stormwatchBufferSize = document.getElementById("stormwatch-buffer-size");
const stormwatchSettingsButton = document.getElementById("stormwatch-settings-button");
const message = document.getElementById("message");
const snapshotImage = document.getElementById("snapshot-image");
const snapshotEmpty = document.getElementById("snapshot-empty");
const snapshotMeta = document.getElementById("snapshot-meta");
const focusPreviewButton = document.getElementById("focus-preview-button");
const focusPreviewNote = document.getElementById("focus-preview-note");
const cameraLightingNote = document.getElementById("camera-lighting-note");
const cameraTuningNote = document.getElementById("camera-tuning-note");
const cameraFocusNote = document.getElementById("camera-focus-note");
const timerModeNote = document.getElementById("timer-mode-note");
const senseHatPanel = document.getElementById("sensehat-panel");
const timerPanel = document.getElementById("timer-panel");
const motionPanel = document.getElementById("motion-panel");
const stormwatchPanel = document.getElementById("stormwatch-panel");
const stormwatchNote = document.getElementById("stormwatch-note");
const eventList = document.getElementById("event-list");
const eventsSelectButton = document.getElementById("events-select-button");
const eventsDownloadButton = document.getElementById("events-download-button");
const eventsDeleteButton = document.getElementById("events-delete-button");
let latestStatus = initialStatus;
let currentEvents = [];
const selectedEventFilenames = new Set();
const eventLightbox = createEventLightbox();
let focusPreviewActive = false;
let focusPreviewRequestInFlight = false;
let focusPreviewTimerId = null;
let focusPreviewSession = 0;
let focusPreviewObjectUrl = null;
const focusPreviewIntervalMs = 900;
const focusPreviewUrl = "/snapshot.jpg?live=1&preview=1&max_w=960&max_h=720&quality=70";

function createEventLightbox() {
  const overlay = document.createElement("div");
  overlay.className = "lightbox hidden";

  const dialog = document.createElement("div");
  dialog.className = "lightbox-dialog";

  const controls = document.createElement("div");
  controls.className = "lightbox-controls";

  const previousButton = document.createElement("button");
  previousButton.type = "button";
  previousButton.textContent = "Previous";

  const nextButton = document.createElement("button");
  nextButton.type = "button";
  nextButton.textContent = "Next";

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.textContent = "Close";

  const image = document.createElement("img");
  image.className = "lightbox-image";
  image.alt = "";

  const caption = document.createElement("p");
  caption.className = "lightbox-caption";

  controls.append(previousButton, nextButton, closeButton);
  dialog.append(controls, image, caption);
  overlay.append(dialog);
  document.body.append(overlay);

  let items = [];
  let currentIndex = 0;

  function showIndex(index) {
    if (!items.length) {
      return;
    }
    currentIndex = (index + items.length) % items.length;
    const event = items[currentIndex];
    const filename = event.snapshot_url.split("/").pop() || "motion-event.jpg";
    image.src = `${event.snapshot_url}?t=${Date.now()}`;
    image.alt = `Motion event ${event.detected_at}`;
    caption.textContent = `${new Date(event.detected_at).toLocaleString()} - ${filename}`;
  }

  function close() {
    overlay.classList.add("hidden");
    image.removeAttribute("src");
    document.body.classList.remove("lightbox-open");
  }

  function open(nextItems, startIndex) {
    items = nextItems;
    overlay.classList.remove("hidden");
    document.body.classList.add("lightbox-open");
    showIndex(startIndex);
  }

  function showPrevious() {
    showIndex(currentIndex - 1);
  }

  function showNext() {
    showIndex(currentIndex + 1);
  }

  previousButton.addEventListener("click", showPrevious);
  nextButton.addEventListener("click", showNext);
  closeButton.addEventListener("click", close);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      close();
    }
  });
  window.addEventListener("keydown", (event) => {
    if (overlay.classList.contains("hidden")) {
      return;
    }
    if (event.key === "Escape") {
      close();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      showPrevious();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      showNext();
    }
  });

  return { open };
}

function addDefinitionRow(container, label, value) {
  const row = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = value;
  row.append(term, detail);
  container.append(row);
}

function clearFocusPreviewObjectUrl() {
  if (focusPreviewObjectUrl !== null) {
    window.URL.revokeObjectURL(focusPreviewObjectUrl);
    focusPreviewObjectUrl = null;
  }
}

function syncFocusPreviewControls(cameraData = latestStatus?.camera) {
  const cameraAvailable = Boolean(cameraData?.available);
  focusPreviewButton.disabled = !focusPreviewActive && !cameraAvailable;
  focusPreviewButton.textContent = focusPreviewActive
    ? "Stop Focus Preview"
    : "Start Focus Preview";
  focusPreviewButton.classList.toggle("preview-active", focusPreviewActive);
  focusPreviewNote.textContent = focusPreviewActive
    ? "Focus preview is running with fresh snapshots about every second. Motion and auto capture stay paused while you focus."
    : "Focus preview grabs fresh snapshots about every second so you can adjust manual-focus lenses like the OV5647.";
}

function stopFocusPreview({ restoreSnapshot = true } = {}) {
  focusPreviewActive = false;
  focusPreviewSession += 1;
  if (focusPreviewTimerId !== null) {
    window.clearTimeout(focusPreviewTimerId);
    focusPreviewTimerId = null;
  }
  clearFocusPreviewObjectUrl();
  focusPreviewRequestInFlight = false;
  if (restoreSnapshot && latestStatus?.snapshot) {
    renderSnapshot(latestStatus.snapshot);
  }
  syncFocusPreviewControls(latestStatus?.camera);
}

async function pauseBackgroundCaptureForFocusPreview() {
  if (latestStatus?.motion?.armed) {
    const response = await fetch("/api/motion/stop", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Focus preview could not pause motion detection.");
    }
    renderStatus(payload.status);
  }

  if (latestStatus?.stormwatch?.armed) {
    const response = await fetch("/api/stormwatch/stop", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Focus preview could not pause stormwatch.");
    }
    renderStatus(payload.status);
  }

  if (latestStatus?.timer?.armed) {
    const response = await fetch("/api/timer/stop", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Focus preview could not stop auto capture.");
    }
    renderStatus(payload.status);
  }
}

async function requestFocusPreviewFrame() {
  if (!focusPreviewActive || focusPreviewRequestInFlight) {
    return;
  }

  const session = focusPreviewSession;
  focusPreviewRequestInFlight = true;
  try {
    const response = await fetch(`${focusPreviewUrl}&t=${Date.now()}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error((await response.text()) || "Focus preview capture failed.");
    }

    const blob = await response.blob();
    if (!focusPreviewActive || session !== focusPreviewSession) {
      return;
    }

    clearFocusPreviewObjectUrl();
    focusPreviewObjectUrl = window.URL.createObjectURL(blob);
    snapshotImage.src = focusPreviewObjectUrl;
    snapshotImage.classList.remove("hidden");
    snapshotEmpty.classList.add("hidden");
    snapshotMeta.textContent = "Focus preview active. Fresh snapshots update about every second.";
  } catch (error) {
    if (session === focusPreviewSession) {
      stopFocusPreview();
      message.textContent = error.message || "Focus preview failed.";
      void refreshStatus();
    }
    return;
  } finally {
    if (session === focusPreviewSession) {
      focusPreviewRequestInFlight = false;
    }
  }

  if (focusPreviewActive && session === focusPreviewSession) {
    focusPreviewTimerId = window.setTimeout(() => {
      void requestFocusPreviewFrame();
    }, focusPreviewIntervalMs);
  }
}

async function toggleFocusPreview() {
  if (focusPreviewActive) {
    stopFocusPreview();
    message.textContent = "Focus preview stopped.";
    return;
  }

  message.textContent = "Starting focus preview...";
  try {
    await pauseBackgroundCaptureForFocusPreview();
    focusPreviewActive = true;
    focusPreviewSession += 1;
    syncFocusPreviewControls(latestStatus?.camera);
    await requestFocusPreviewFrame();
    if (focusPreviewActive) {
      message.textContent = "Focus preview running. Rotate the lens slowly until edges sharpen.";
    }
  } catch (error) {
    stopFocusPreview();
    message.textContent = error.message || "Focus preview failed to start.";
  }
}

function renderSenseHat(data) {
  senseHatPanel.innerHTML = "";
  if (!data.available) {
    addDefinitionRow(senseHatPanel, "Available", "No");
    addDefinitionRow(senseHatPanel, "Reason", data.reason || "Unavailable");
    return;
  }

  addDefinitionRow(senseHatPanel, "Available", "Yes");
  addDefinitionRow(senseHatPanel, "Temperature", `${data.temperature_f} F`);
  addDefinitionRow(senseHatPanel, "Humidity", `${data.humidity_pct} %`);
  addDefinitionRow(senseHatPanel, "Pressure", `${data.pressure_inhg} inHg`);
  addDefinitionRow(senseHatPanel, "Pitch", `${data.orientation.pitch} deg`);
  addDefinitionRow(senseHatPanel, "Roll", `${data.orientation.roll} deg`);
  addDefinitionRow(senseHatPanel, "Yaw", `${data.orientation.yaw} deg`);
}

function renderCamera(data) {
  const lighting = data.lighting || { mode: "auto", supported: false, options: [] };
  const tuning = data.tuning || {
    supported: false,
    white_balance_mode: "auto",
    brightness: 0,
    contrast: 1,
    saturation: 1,
    sharpness: 1,
    denoise_mode: "auto",
    white_balance_options: [],
    denoise_options: [],
    ranges: {},
  };
  const focus = data.focus || {
    supported: false,
    mode: "on-capture",
    range: "normal",
    lens_position: 1.0,
    mode_options: [],
    range_options: [],
    ranges: {},
  };
  const selectedFocusMode =
    (focus.mode_options || []).find((option) => option.value === focus.mode)?.label ||
    focus.mode ||
    "Unsupported";
  document.getElementById("camera-available").textContent = data.available ? "Yes" : "No";
  document.getElementById("camera-source-name").textContent = data.active_source_name || "Unavailable";
  document.getElementById("camera-backend").textContent = data.backend || "Unavailable";
  document.getElementById("camera-sensor-model").textContent =
    data.sensor_model || data.sensor_name || "N/A";
  document.getElementById("camera-index").textContent =
    Number.isInteger(data.camera_index) ? `${data.camera_index + 1}` : "N/A";
  document.getElementById("camera-target").textContent = data.target || "Unavailable";
  document.getElementById("camera-resolution").textContent =
    `${data.resolution.width} x ${data.resolution.height}`;
  document.getElementById("camera-burst-count").textContent = `${data.burst_count || 1}`;
  document.getElementById("camera-rotation").textContent = `${data.rotation_degrees || 0} deg`;
  document.getElementById("camera-lighting").textContent = lighting.mode || "auto";
  document.getElementById("camera-focus").textContent = focus.supported
    ? selectedFocusMode
    : "Unsupported";

  cameraSourceSelect.innerHTML = "";
  for (const source of data.sources || []) {
    const option = document.createElement("option");
    option.value = source.source_id;
    option.textContent = source.available ? source.label : `${source.label} (Unavailable)`;
    option.selected = Boolean(source.selected);
    option.disabled = !source.available;
    cameraSourceSelect.append(option);
  }

  cameraSourceSelect.disabled = !cameraSourceSelect.options.length;
  cameraSourceButton.disabled = cameraSourceSelect.disabled;
  rotateButton.disabled = !data.available;
  networkCameraUrl.value = data.network_camera_url || "";
  captureBurstCount.value = `${data.burst_count || 1}`;
  captureResolution.innerHTML = "";
  captureLighting.innerHTML = "";
  captureWhiteBalance.innerHTML = "";
  captureDenoise.innerHTML = "";
  captureAutofocusMode.innerHTML = "";
  captureAutofocusRange.innerHTML = "";
  for (const option of data.resolution.options || []) {
    const selectOption = document.createElement("option");
    selectOption.value = `${option.width}x${option.height}`;
    selectOption.textContent = option.label;
    selectOption.selected =
      option.width === data.resolution.width && option.height === data.resolution.height;
    captureResolution.append(selectOption);
  }
  for (const option of lighting.options || []) {
    const selectOption = document.createElement("option");
    selectOption.value = option.mode;
    selectOption.textContent = option.label;
    selectOption.selected = option.mode === lighting.mode;
    captureLighting.append(selectOption);
  }
  for (const option of tuning.white_balance_options || []) {
    const selectOption = document.createElement("option");
    selectOption.value = option.value;
    selectOption.textContent = option.label;
    selectOption.selected = option.value === tuning.white_balance_mode;
    captureWhiteBalance.append(selectOption);
  }
  for (const option of tuning.denoise_options || []) {
    const selectOption = document.createElement("option");
    selectOption.value = option.value;
    selectOption.textContent = option.label;
    selectOption.selected = option.value === tuning.denoise_mode;
    captureDenoise.append(selectOption);
  }
  for (const option of focus.mode_options || []) {
    const selectOption = document.createElement("option");
    selectOption.value = option.value;
    selectOption.textContent = option.label;
    selectOption.selected = option.value === focus.mode;
    captureAutofocusMode.append(selectOption);
  }
  for (const option of focus.range_options || []) {
    const selectOption = document.createElement("option");
    selectOption.value = option.value;
    selectOption.textContent = option.label;
    selectOption.selected = option.value === focus.range;
    captureAutofocusRange.append(selectOption);
  }
  captureLensPosition.value = `${focus.lens_position}`;
  captureBrightness.value = `${tuning.brightness}`;
  captureContrast.value = `${tuning.contrast}`;
  captureSaturation.value = `${tuning.saturation}`;
  captureSharpness.value = `${tuning.sharpness}`;
  for (const [input, range] of [
    [captureBrightness, tuning.ranges?.brightness],
    [captureContrast, tuning.ranges?.contrast],
    [captureSaturation, tuning.ranges?.saturation],
    [captureSharpness, tuning.ranges?.sharpness],
  ]) {
    if (!range) {
      continue;
    }
    input.min = `${range.min}`;
    input.max = `${range.max}`;
    input.step = `${range.step}`;
  }
  for (const control of [
    captureWhiteBalance,
    captureDenoise,
    captureBrightness,
    captureContrast,
    captureSaturation,
    captureSharpness,
  ]) {
    control.disabled = !tuning.supported;
  }
  captureAutofocusMode.disabled = !focus.supported;
  captureAutofocusRange.disabled = !focus.supported || focus.mode === "manual";
  captureLensPosition.disabled = !focus.supported || focus.mode !== "manual";
  const lensPositionRange = focus.ranges?.lens_position;
  if (lensPositionRange) {
    captureLensPosition.min = `${lensPositionRange.min}`;
    captureLensPosition.max = `${lensPositionRange.max}`;
    captureLensPosition.step = `${lensPositionRange.step}`;
  }
  cameraLightingNote.textContent = lighting.supported
    ? "Lighting presets are active for the Pi Camera."
    : "Lighting presets are saved, but only apply when the Pi Camera is active.";
  cameraTuningNote.textContent = tuning.supported
    ? "Direct Pi Camera tuning is active. Lower brightness or switch white balance when bright sunlight shifts the color."
    : "Direct Pi Camera tuning is saved, but only applies when the Pi Camera is active.";
  cameraFocusNote.textContent = focus.supported
    ? focus.mode === "manual"
      ? "Manual focus is active. Use focus preview and raise lens position to focus closer subjects."
      : "Autofocus is active for this Pi camera. Auto on Capture is the best default for still snapshots."
    : "Focus controls are saved, but only apply to autofocus-capable Pi cameras like the IMX708 Camera Module 3.";
}

function renderMotion(data) {
  motionPanel.innerHTML = "";

  if (!data) {
    addDefinitionRow(motionPanel, "Available", "No");
    return;
  }

  addDefinitionRow(motionPanel, "Armed", data.armed ? "Yes" : "No");
  addDefinitionRow(motionPanel, "Running", data.running ? "Yes" : "No");
  addDefinitionRow(motionPanel, "Poll Interval", `${data.poll_interval_seconds}s`);
  addDefinitionRow(motionPanel, "Cooldown", `${data.cooldown_seconds}s`);
  addDefinitionRow(motionPanel, "Threshold", `${data.motion_threshold}`);
  addDefinitionRow(
    motionPanel,
    "Last Score",
    data.last_score === null ? "Waiting for frames" : `${data.last_score}`,
  );
  addDefinitionRow(
    motionPanel,
    "Last Motion",
    data.last_motion_at || "No motion event yet",
  );
  addDefinitionRow(
    motionPanel,
    "Detector Error",
    data.last_error || "None",
  );

  motionStartButton.disabled = data.armed;
  motionStopButton.disabled = !data.armed;
}

function renderStormwatch(data) {
  stormwatchPanel.innerHTML = "";

  if (!data) {
    addDefinitionRow(stormwatchPanel, "Available", "No");
    stormwatchStartButton.disabled = true;
    stormwatchStopButton.disabled = true;
    stormwatchPollInterval.disabled = true;
    stormwatchCooldown.disabled = true;
    stormwatchScoreTrigger.disabled = true;
    stormwatchHotPixelThreshold.disabled = true;
    stormwatchBufferSize.disabled = true;
    stormwatchSettingsButton.disabled = true;
    return;
  }

  addDefinitionRow(stormwatchPanel, "Armed", data.armed ? "Yes" : "No");
  addDefinitionRow(stormwatchPanel, "Running", data.running ? "Yes" : "No");
  addDefinitionRow(stormwatchPanel, "Poll Interval", `${data.poll_interval_seconds}s`);
  addDefinitionRow(stormwatchPanel, "Cooldown", `${data.cooldown_seconds}s`);
  addDefinitionRow(stormwatchPanel, "Score Trigger", `${data.score_trigger ?? data.motion_threshold}`);
  addDefinitionRow(stormwatchPanel, "Hot Pixel Threshold", `${data.hot_pixel_threshold}`);
  addDefinitionRow(stormwatchPanel, "Buffer Size", `${data.buffer_size}`);
  addDefinitionRow(stormwatchPanel, "Last Score", data.last_score === null ? "Waiting for frames" : `${data.last_score}`);
  addDefinitionRow(stormwatchPanel, "Last Trigger", data.last_lightning_at || data.last_motion_at || "No trigger yet");
  addDefinitionRow(stormwatchPanel, "Detector Error", data.last_error || "None");

  stormwatchStartButton.disabled = data.armed;
  stormwatchStopButton.disabled = !data.armed;
  stormwatchPollInterval.value = `${data.poll_interval_seconds}`;
  stormwatchCooldown.value = `${data.cooldown_seconds}`;
  stormwatchScoreTrigger.value = `${data.score_trigger ?? data.motion_threshold}`;
  stormwatchHotPixelThreshold.value = `${data.hot_pixel_threshold}`;
  stormwatchBufferSize.value = `${data.buffer_size}`;
  stormwatchPollInterval.disabled = false;
  stormwatchCooldown.disabled = false;
  stormwatchScoreTrigger.disabled = false;
  stormwatchHotPixelThreshold.disabled = false;
  stormwatchBufferSize.disabled = false;
  stormwatchSettingsButton.disabled = false;
  stormwatchNote.textContent = data.armed
    ? "Stormwatch is armed and will capture bursts when lightning-like spikes are detected."
    : "Stormwatch watches for sudden frame spikes and saves a burst of captures when lightning-like changes are detected.";
}

function timerInputsFromSeconds(intervalSeconds) {
  if (intervalSeconds >= 60 && intervalSeconds % 60 === 0) {
    return {
      value: intervalSeconds / 60,
      unit: "minutes",
    };
  }
  return {
    value: intervalSeconds,
    unit: "seconds",
  };
}

function secondsFromValueUnit(value, unit) {
  return unit === "minutes" ? value * 60 : value;
}

function syncTimerModeInputs() {
  const comboMode = timerMode.value === "combo";
  timerDurationValue.disabled = !comboMode;
  timerDurationUnit.disabled = !comboMode;
  timerModeNote.textContent = comboMode
    ? "Motion + Timer waits for movement, then captures every interval for the selected duration. The interval must be at least 7 seconds."
    : "Timer captures immediately on a fixed schedule using the selected interval.";
}

function renderTimer(data) {
  timerPanel.innerHTML = "";

  if (!data) {
    addDefinitionRow(timerPanel, "Available", "No");
    timerMode.disabled = true;
    timerIntervalValue.disabled = true;
    timerIntervalUnit.disabled = true;
    timerDurationValue.disabled = true;
    timerDurationUnit.disabled = true;
    timerStartButton.disabled = true;
    timerStopButton.disabled = true;
    return;
  }

  addDefinitionRow(timerPanel, "Armed", data.armed ? "Yes" : "No");
  addDefinitionRow(timerPanel, "Running", data.running ? "Yes" : "No");
  addDefinitionRow(timerPanel, "Mode", data.mode === "combo" ? "Motion + Timer" : "Timer");
  addDefinitionRow(timerPanel, "Interval", `${data.interval_seconds}s`);
  addDefinitionRow(timerPanel, "Duration", `${data.duration_seconds}s`);
  addDefinitionRow(timerPanel, "Waiting for Motion", data.waiting_for_motion ? "Yes" : "No");
  addDefinitionRow(timerPanel, "Captured", `${data.capture_count}`);
  addDefinitionRow(timerPanel, "Last Capture", data.last_capture_at || "None yet");
  addDefinitionRow(timerPanel, "Last Trigger", data.last_motion_at || "No motion trigger yet");
  addDefinitionRow(timerPanel, "Timer Error", data.last_error || "None");

  const timerInputs = timerInputsFromSeconds(data.interval_seconds);
  timerIntervalValue.value = `${timerInputs.value}`;
  timerIntervalUnit.value = timerInputs.unit;
  const durationInputs = timerInputsFromSeconds(data.duration_seconds);
  timerDurationValue.value = `${durationInputs.value}`;
  timerDurationUnit.value = durationInputs.unit;
  timerMode.value = data.mode || "timer";
  timerMode.disabled = false;
  timerIntervalValue.disabled = false;
  timerIntervalUnit.disabled = false;
  syncTimerModeInputs();
  timerStartButton.disabled = data.armed;
  timerStopButton.disabled = !data.armed;
}

function renderEvents(events) {
  currentEvents = events;
  const eventFilenames = new Set(
    events.map((event) => event.snapshot_url.split("/").pop()).filter(Boolean),
  );
  for (const filename of Array.from(selectedEventFilenames)) {
    if (!eventFilenames.has(filename)) {
      selectedEventFilenames.delete(filename);
    }
  }

  eventList.innerHTML = "";

  if (!events.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No motion events yet.";
    eventList.append(empty);
    updateEventActionButtons();
    return;
  }

  for (const [index, event] of events.entries()) {
    const card = document.createElement("article");
    card.className = "event-card";

    const filename = event.snapshot_url.split("/").pop() || "motion-event.jpg";
    card.dataset.filename = filename;

    const selection = document.createElement("button");
    selection.className = "event-select";
    selection.type = "button";

    function syncSelectionState() {
      const isSelected = selectedEventFilenames.has(filename);
      selection.classList.toggle("selected", isSelected);
      selection.setAttribute("aria-pressed", isSelected ? "true" : "false");
      selection.textContent = isSelected ? "Selected" : "Select Photo";
      card.classList.toggle("selected", isSelected);
    }

    selection.addEventListener("click", () => {
      if (selectedEventFilenames.has(filename)) {
        selectedEventFilenames.delete(filename);
      } else {
        selectedEventFilenames.add(filename);
      }
      syncSelectionState();
      updateEventActionButtons();
    });
    syncSelectionState();

    const imageLink = document.createElement("a");
    imageLink.className = "event-image-link";
    imageLink.href = event.snapshot_url;
    imageLink.title = "Open full image";
    imageLink.addEventListener("click", (clickEvent) => {
      clickEvent.preventDefault();
      eventLightbox.open(currentEvents, index);
    });

    const img = document.createElement("img");
    img.alt = `Motion event ${event.detected_at}`;
    img.src = `${event.snapshot_url}?max_w=480&max_h=360&quality=70&t=${Date.now()}`;
    img.loading = "lazy";
    imageLink.append(img);

    const body = document.createElement("div");
    body.className = "event-card-body";

    const title = document.createElement("h3");
    title.textContent = new Date(event.detected_at).toLocaleString();

    const path = document.createElement("p");
    path.className = "subtle";
    path.textContent = filename;

    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent =
      event.score === null
        ? `${
            event.source === "timer"
              ? "Timed"
              : event.source === "combo"
                ? "Combo"
                : "Saved"
          } capture`
        : `Score ${event.score}`;

    const actions = document.createElement("div");
    actions.className = "event-card-actions";

    const download = document.createElement("a");
    download.className = "event-download";
    download.href = event.snapshot_url;
    download.download = filename;
    download.textContent = "Download JPG";

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "danger";
    removeButton.textContent = "Delete";
    removeButton.addEventListener("click", () => {
      void deleteEvents([filename]);
    });

    actions.append(download, removeButton);
    body.append(selection, title, path, badge, actions);
    card.append(imageLink, body);
    eventList.append(card);
  }

  updateEventActionButtons();
}

function renderSnapshot(snapshot) {
  if (snapshot.exists && snapshot.url) {
    snapshotImage.src = `${snapshot.url}?t=${Date.now()}`;
    snapshotImage.classList.remove("hidden");
    snapshotEmpty.classList.add("hidden");
    snapshotMeta.textContent = `Captured at ${snapshot.modified_at}`;
    return;
  }

  snapshotImage.removeAttribute("src");
  snapshotImage.classList.add("hidden");
  snapshotEmpty.classList.remove("hidden");
  snapshotMeta.textContent = "No snapshot captured yet.";
}

function renderStatus(status) {
  latestStatus = status;
  document.getElementById("host-name").textContent = status.host;
  document.getElementById("generated-at").textContent = status.generated_at;
  renderCamera(status.camera);
  renderSenseHat(status.sense_hat);
  renderTimer(status.timer);
  renderMotion(status.motion);
  renderStormwatch(status.stormwatch);
  motionPollInterval.disabled = !status.motion;
  motionCooldown.disabled = !status.motion;
  motionThreshold.disabled = !status.motion;
  if (status.motion) {
    motionPollInterval.value = `${status.motion.poll_interval_seconds}`;
    motionCooldown.value = `${status.motion.cooldown_seconds}`;
    motionThreshold.value = `${status.motion.motion_threshold}`;
  }
  stormwatchPollInterval.disabled = !status.stormwatch;
  stormwatchCooldown.disabled = !status.stormwatch;
  stormwatchScoreTrigger.disabled = !status.stormwatch;
  stormwatchHotPixelThreshold.disabled = !status.stormwatch;
  stormwatchBufferSize.disabled = !status.stormwatch;
  if (status.stormwatch) {
    stormwatchPollInterval.value = `${status.stormwatch.poll_interval_seconds}`;
    stormwatchCooldown.value = `${status.stormwatch.cooldown_seconds}`;
    stormwatchScoreTrigger.value = `${status.stormwatch.score_trigger ?? status.stormwatch.motion_threshold}`;
    stormwatchHotPixelThreshold.value = `${status.stormwatch.hot_pixel_threshold}`;
    stormwatchBufferSize.value = `${status.stormwatch.buffer_size}`;
  }
  if (!focusPreviewActive) {
    renderSnapshot(status.snapshot);
  }
  renderEvents(status.motion_events || []);
  syncFocusPreviewControls(status.camera);
}

async function refreshStatus() {
  const response = await fetch("/api/status");
  const payload = await response.json();
  renderStatus(payload);
  message.textContent = "Status refreshed.";
}

async function captureSnapshot() {
  stopFocusPreview({ restoreSnapshot: false });
  message.textContent = "Capturing snapshot...";
  const response = await fetch("/api/capture", { method: "POST" });
  const payload = await response.json();

  if (!response.ok) {
    message.textContent = payload.error || "Snapshot capture failed.";
    return;
  }

  renderStatus(payload.status);
  message.textContent = `Captured ${payload.captured_count || 1} photo${payload.captured_count === 1 ? "" : "s"}.`;
}

async function setMotionState(endpoint, successMessage) {
  stopFocusPreview({ restoreSnapshot: false });
  message.textContent = "Updating motion detector...";
  const response = await fetch(endpoint, { method: "POST" });
  const payload = await response.json();

  if (!response.ok) {
    message.textContent = payload.error || "Motion detector update failed.";
    return;
  }

  renderStatus(payload.status);
  message.textContent = successMessage;
}

async function setStormwatchState(endpoint, successMessage) {
  stopFocusPreview({ restoreSnapshot: false });
  message.textContent = "Updating stormwatch...";
  const response = await fetch(endpoint, { method: "POST" });
  const payload = await response.json();

  if (!response.ok) {
    message.textContent = payload.error || "Stormwatch update failed.";
    return;
  }

  renderStatus(payload.status);
  message.textContent = successMessage;
}

async function setCameraSource() {
  if (!cameraSourceSelect.value) {
    return;
  }

  stopFocusPreview({ restoreSnapshot: false });
  message.textContent = "Switching camera source...";
  const response = await fetch("/api/camera/source", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ source_id: cameraSourceSelect.value }),
  });
  const payload = await response.json();

  if (!response.ok) {
    message.textContent = payload.error || "Camera source update failed.";
    return;
  }

  renderStatus(payload.status);
  message.textContent = "Camera source updated.";
}

async function saveNetworkCameraUrl() {
  stopFocusPreview({ restoreSnapshot: false });
  message.textContent = "Saving ESP32-CAM URL...";
  const response = await fetch("/api/camera/network", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ url: networkCameraUrl.value }),
  });
  const payload = await response.json();

  if (!response.ok) {
    message.textContent = payload.error || "ESP32-CAM URL update failed.";
    return;
  }

  renderStatus(payload.status);
  message.textContent = "ESP32-CAM URL saved.";
}

async function rotateCamera() {
  stopFocusPreview({ restoreSnapshot: false });
  message.textContent = "Rotating camera...";
  rotateButton.disabled = true;
  const response = await fetch("/api/camera/rotate", { method: "POST" });
  const payload = await response.json();

  if (!response.ok) {
    rotateButton.disabled = false;
    message.textContent = payload.error || "Camera rotation failed.";
    return;
  }

  renderStatus(payload.status);
  message.textContent = `Camera rotated to ${payload.status.camera.rotation_degrees} degrees.`;
}

async function saveSettings() {
  stopFocusPreview({ restoreSnapshot: false });
  const burstCount = Number.parseInt(captureBurstCount.value, 10);
  if (Number.isNaN(burstCount)) {
    message.textContent = "Choose a burst count between 1 and 5.";
    return;
  }
  const brightness = Number.parseFloat(captureBrightness.value);
  const contrast = Number.parseFloat(captureContrast.value);
  const saturation = Number.parseFloat(captureSaturation.value);
  const sharpness = Number.parseFloat(captureSharpness.value);
  const lensPosition = Number.parseFloat(captureLensPosition.value);
  if (Number.isNaN(brightness)) {
    message.textContent = "Enter a brightness value in the allowed range.";
    return;
  }
  if (Number.isNaN(contrast)) {
    message.textContent = "Enter a contrast value in the allowed range.";
    return;
  }
  if (Number.isNaN(saturation)) {
    message.textContent = "Enter a saturation value in the allowed range.";
    return;
  }
  if (Number.isNaN(sharpness)) {
    message.textContent = "Enter a sharpness value in the allowed range.";
    return;
  }
  if (Number.isNaN(lensPosition)) {
    message.textContent = "Enter a manual lens position in the allowed range.";
    return;
  }

  const body = {
    burst_count: burstCount,
    resolution: captureResolution.value,
    lighting_mode: captureLighting.value,
    autofocus_mode: captureAutofocusMode.value,
    autofocus_range: captureAutofocusRange.value,
    lens_position: lensPosition,
    white_balance_mode: captureWhiteBalance.value,
    brightness,
    contrast,
    saturation,
    sharpness,
    denoise_mode: captureDenoise.value,
  };

  if (!motionPollInterval.disabled) {
    const pollInterval = Number.parseFloat(motionPollInterval.value);
    if (Number.isNaN(pollInterval)) {
      message.textContent = "Enter a poll interval between 0.5 and 30 seconds.";
      return;
    }
    const cooldown = Number.parseFloat(motionCooldown.value);
    if (Number.isNaN(cooldown)) {
      message.textContent = "Enter a cooldown between 1 and 300 seconds.";
      return;
    }
    const threshold = Number.parseFloat(motionThreshold.value);
    if (Number.isNaN(threshold)) {
      message.textContent = "Enter a threshold between 1 and 255.";
      return;
    }
    body.poll_interval_seconds = pollInterval;
    body.cooldown_seconds = cooldown;
    body.motion_threshold = threshold;
  }

  message.textContent = "Saving settings...";
  settingsButton.disabled = true;
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  settingsButton.disabled = false;

  if (!response.ok) {
    message.textContent = payload.error || "Settings update failed.";
    return;
  }

  renderStatus(payload.status);
  message.textContent = "Settings saved.";
}

async function saveStormwatchSettings() {
  stopFocusPreview({ restoreSnapshot: false });
  const pollInterval = Number.parseFloat(stormwatchPollInterval.value);
  if (Number.isNaN(pollInterval)) {
    message.textContent = "Enter a stormwatch poll interval between 0.5 and 30 seconds.";
    return;
  }
  const cooldown = Number.parseFloat(stormwatchCooldown.value);
  if (Number.isNaN(cooldown)) {
    message.textContent = "Enter a stormwatch cooldown between 1 and 300 seconds.";
    return;
  }
  const scoreTrigger = Number.parseFloat(stormwatchScoreTrigger.value);
  if (Number.isNaN(scoreTrigger)) {
    message.textContent = "Enter a stormwatch score trigger between 1 and 255.";
    return;
  }
  const hotPixelThreshold = Number.parseInt(stormwatchHotPixelThreshold.value, 10);
  if (Number.isNaN(hotPixelThreshold)) {
    message.textContent = "Enter a stormwatch hot pixel threshold between 1 and 255.";
    return;
  }
  const bufferSize = Number.parseInt(stormwatchBufferSize.value, 10);
  if (Number.isNaN(bufferSize)) {
    message.textContent = "Enter a stormwatch buffer size between 1 and 120.";
    return;
  }

  message.textContent = "Saving stormwatch settings...";
  stormwatchSettingsButton.disabled = true;
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      stormwatch_poll_interval_seconds: pollInterval,
      stormwatch_cooldown_seconds: cooldown,
      stormwatch_score_trigger: scoreTrigger,
      stormwatch_hot_pixel_threshold: hotPixelThreshold,
      stormwatch_buffer_size: bufferSize,
    }),
  });
  const payload = await response.json();
  stormwatchSettingsButton.disabled = false;

  if (!response.ok) {
    message.textContent = payload.error || "Stormwatch settings update failed.";
    return;
  }

  renderStatus(payload.status);
  message.textContent = "Stormwatch settings saved.";
}

async function startTimer() {
  stopFocusPreview({ restoreSnapshot: false });
  const intervalValue = Number.parseInt(timerIntervalValue.value, 10);
  if (Number.isNaN(intervalValue) || intervalValue < 1) {
    message.textContent = "Enter a timer interval of at least 1.";
    return;
  }
  const durationValue = Number.parseInt(timerDurationValue.value, 10);
  if (Number.isNaN(durationValue) || durationValue < 1) {
    message.textContent = "Enter an auto capture duration of at least 1.";
    return;
  }

  const intervalSeconds = secondsFromValueUnit(intervalValue, timerIntervalUnit.value);
  const durationSeconds = secondsFromValueUnit(durationValue, timerDurationUnit.value);
  if (timerMode.value === "combo" && intervalSeconds < 7) {
    message.textContent = "Motion + Timer needs an interval of at least 7 seconds.";
    return;
  }

  message.textContent = "Starting auto capture...";
  timerStartButton.disabled = true;
  const response = await fetch("/api/timer/start", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      interval_seconds: intervalSeconds,
      duration_seconds: durationSeconds,
      mode: timerMode.value,
    }),
  });
  const payload = await response.json();
  timerStartButton.disabled = false;

  if (!response.ok) {
    message.textContent = payload.error || "Auto capture failed to start.";
    return;
  }

  renderStatus(payload.status);
  message.textContent =
    timerMode.value === "combo" ? "Motion + Timer started." : "Timer capture started.";
}

async function stopTimer() {
  message.textContent = "Stopping auto capture...";
  timerStopButton.disabled = true;
  const response = await fetch("/api/timer/stop", { method: "POST" });
  const payload = await response.json();
  timerStopButton.disabled = false;

  if (!response.ok) {
    message.textContent = payload.error || "Auto capture failed to stop.";
    return;
  }

  renderStatus(payload.status);
  message.textContent = "Auto capture stopped.";
}

function updateEventActionButtons() {
  const totalEvents = currentEvents.length;
  const selectedCount = selectedEventFilenames.size;
  const hasEvents = totalEvents > 0;
  const hasSelection = selectedCount > 0;

  eventsSelectButton.disabled = !hasEvents;
  eventsDownloadButton.disabled = !hasSelection;
  eventsDeleteButton.disabled = !hasSelection;
  eventsSelectButton.textContent =
    hasEvents && selectedCount === totalEvents ? "Clear Selection" : "Select All";
}

async function downloadEvents(filenames) {
  if (!filenames.length) {
    message.textContent = "Select at least one event image.";
    return;
  }

  message.textContent = "Preparing download...";
  const response = await fetch("/api/events/download", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ filenames }),
  });

  if (!response.ok) {
    const payload = await response.json();
    message.textContent = payload.error || "Download failed.";
    return;
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  const contentDisposition = response.headers.get("Content-Disposition") || "";
  const match = contentDisposition.match(/filename="?([^"]+)"?/);
  link.href = url;
  link.download = match ? match[1] : "motionsense-events.zip";
  document.body.append(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
  message.textContent = `Downloaded ${filenames.length} photo${filenames.length === 1 ? "" : "s"}.`;
}

async function deleteEvents(filenames) {
  if (!filenames.length) {
    message.textContent = "Select at least one event image.";
    return;
  }
  if (!window.confirm(`Delete ${filenames.length} photo${filenames.length === 1 ? "" : "s"}?`)) {
    return;
  }

  message.textContent = "Deleting event photos...";
  const response = await fetch("/api/events/delete", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ filenames }),
  });
  const payload = await response.json();

  if (!response.ok) {
    message.textContent = payload.error || "Delete failed.";
    return;
  }

  for (const filename of filenames) {
    selectedEventFilenames.delete(filename);
  }
  renderStatus(payload.status);
  message.textContent = `Deleted ${payload.deleted_count} photo${payload.deleted_count === 1 ? "" : "s"}.`;
}

captureButton.addEventListener("click", () => {
  void captureSnapshot();
});
focusPreviewButton.addEventListener("click", () => {
  void toggleFocusPreview();
});
timerStartButton.addEventListener("click", () => {
  void startTimer();
});
timerStopButton.addEventListener("click", () => {
  void stopTimer();
});
timerMode.addEventListener("change", syncTimerModeInputs);

rotateButton.addEventListener("click", () => {
  void rotateCamera();
});

refreshButton.addEventListener("click", () => {
  void refreshStatus();
});

cameraSourceButton.addEventListener("click", () => {
  void setCameraSource();
});

networkCameraButton.addEventListener("click", () => {
  void saveNetworkCameraUrl();
});

settingsButton.addEventListener("click", () => {
  void saveSettings();
});

stormwatchSettingsButton.addEventListener("click", () => {
  void saveStormwatchSettings();
});

eventsSelectButton.addEventListener("click", () => {
  if (selectedEventFilenames.size === currentEvents.length) {
    selectedEventFilenames.clear();
  } else {
    for (const event of currentEvents) {
      const filename = event.snapshot_url.split("/").pop();
      if (filename) {
        selectedEventFilenames.add(filename);
      }
    }
  }
  renderEvents(currentEvents);
});

eventsDownloadButton.addEventListener("click", () => {
  void downloadEvents(Array.from(selectedEventFilenames));
});

eventsDeleteButton.addEventListener("click", () => {
  void deleteEvents(Array.from(selectedEventFilenames));
});

motionStartButton.addEventListener("click", () => {
  void setMotionState("/api/motion/start", "Motion detector armed.");
});

motionStopButton.addEventListener("click", () => {
  void setMotionState("/api/motion/stop", "Motion detector paused.");
});

stormwatchStartButton.addEventListener("click", () => {
  void setStormwatchState("/api/stormwatch/start", "Stormwatch armed.");
});

stormwatchStopButton.addEventListener("click", () => {
  void setStormwatchState("/api/stormwatch/stop", "Stormwatch paused.");
});

renderStatus(initialStatus);
window.setInterval(() => {
  void refreshStatus();
}, 15000);
