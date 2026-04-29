const initialStatus = JSON.parse(document.getElementById("initial-status").textContent);

const captureButton = document.getElementById("capture-button");
const refreshButton = document.getElementById("refresh-button");
const cameraSourceSelect = document.getElementById("camera-source-select");
const cameraSourceButton = document.getElementById("camera-source-button");
const networkCameraUrl = document.getElementById("network-camera-url");
const networkCameraButton = document.getElementById("network-camera-button");
const captureResolution = document.getElementById("capture-resolution");
const captureLighting = document.getElementById("capture-lighting");
const motionPollInterval = document.getElementById("motion-poll-interval");
const motionCooldown = document.getElementById("motion-cooldown");
const motionThreshold = document.getElementById("motion-threshold");
const captureBurstCount = document.getElementById("capture-burst-count");
const settingsButton = document.getElementById("settings-button");
const timerIntervalValue = document.getElementById("timer-interval-value");
const timerIntervalUnit = document.getElementById("timer-interval-unit");
const timerStartButton = document.getElementById("timer-start-button");
const timerStopButton = document.getElementById("timer-stop-button");
const rotateButton = document.getElementById("rotate-button");
const motionStartButton = document.getElementById("motion-start-button");
const motionStopButton = document.getElementById("motion-stop-button");
const message = document.getElementById("message");
const snapshotImage = document.getElementById("snapshot-image");
const snapshotEmpty = document.getElementById("snapshot-empty");
const snapshotMeta = document.getElementById("snapshot-meta");
const cameraLightingNote = document.getElementById("camera-lighting-note");
const senseHatPanel = document.getElementById("sensehat-panel");
const timerPanel = document.getElementById("timer-panel");
const motionPanel = document.getElementById("motion-panel");
const eventList = document.getElementById("event-list");
const eventsSelectButton = document.getElementById("events-select-button");
const eventsDownloadButton = document.getElementById("events-download-button");
const eventsDeleteButton = document.getElementById("events-delete-button");
let currentEvents = [];
const selectedEventFilenames = new Set();
const eventLightbox = createEventLightbox();

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
  document.getElementById("camera-available").textContent = data.available ? "Yes" : "No";
  document.getElementById("camera-source-name").textContent = data.active_source_name || "Unavailable";
  document.getElementById("camera-backend").textContent = data.backend || "Unavailable";
  document.getElementById("camera-target").textContent = data.target || "Unavailable";
  document.getElementById("camera-resolution").textContent =
    `${data.resolution.width} x ${data.resolution.height}`;
  document.getElementById("camera-burst-count").textContent = `${data.burst_count || 1}`;
  document.getElementById("camera-rotation").textContent = `${data.rotation_degrees || 0} deg`;
  document.getElementById("camera-lighting").textContent = lighting.mode || "auto";

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
  cameraLightingNote.textContent = lighting.supported
    ? "Lighting presets are active for the Pi Camera."
    : "Lighting presets are saved, but only apply when the Pi Camera is active.";
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

function renderTimer(data) {
  timerPanel.innerHTML = "";

  if (!data) {
    addDefinitionRow(timerPanel, "Available", "No");
    timerStartButton.disabled = true;
    timerStopButton.disabled = true;
    return;
  }

  addDefinitionRow(timerPanel, "Armed", data.armed ? "Yes" : "No");
  addDefinitionRow(timerPanel, "Running", data.running ? "Yes" : "No");
  addDefinitionRow(timerPanel, "Interval", `${data.interval_seconds}s`);
  addDefinitionRow(timerPanel, "Captured", `${data.capture_count}`);
  addDefinitionRow(timerPanel, "Last Capture", data.last_capture_at || "None yet");
  addDefinitionRow(timerPanel, "Timer Error", data.last_error || "None");

  const timerInputs = timerInputsFromSeconds(data.interval_seconds);
  timerIntervalValue.value = `${timerInputs.value}`;
  timerIntervalUnit.value = timerInputs.unit;
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

    const selection = document.createElement("label");
    selection.className = "event-select";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selectedEventFilenames.has(filename);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        selectedEventFilenames.add(filename);
      } else {
        selectedEventFilenames.delete(filename);
      }
      updateEventActionButtons();
    });

    const selectionLabel = document.createElement("span");
    selectionLabel.textContent = "Select";
    selection.append(checkbox, selectionLabel);

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
        ? `${event.source === "timer" ? "Timed" : "Saved"} capture`
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
  document.getElementById("host-name").textContent = status.host;
  document.getElementById("generated-at").textContent = status.generated_at;
  renderCamera(status.camera);
  renderSenseHat(status.sense_hat);
  renderTimer(status.timer);
  renderMotion(status.motion);
  motionPollInterval.disabled = !status.motion;
  motionCooldown.disabled = !status.motion;
  motionThreshold.disabled = !status.motion;
  if (status.motion) {
    motionPollInterval.value = `${status.motion.poll_interval_seconds}`;
    motionCooldown.value = `${status.motion.cooldown_seconds}`;
    motionThreshold.value = `${status.motion.motion_threshold}`;
  }
  renderSnapshot(status.snapshot);
  renderEvents(status.motion_events || []);
}

async function refreshStatus() {
  const response = await fetch("/api/status");
  const payload = await response.json();
  renderStatus(payload);
  message.textContent = "Status refreshed.";
}

async function captureSnapshot() {
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

async function setCameraSource() {
  if (!cameraSourceSelect.value) {
    return;
  }

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
  const burstCount = Number.parseInt(captureBurstCount.value, 10);
  if (Number.isNaN(burstCount)) {
    message.textContent = "Choose a burst count between 1 and 5.";
    return;
  }

  const body = {
    burst_count: burstCount,
    resolution: captureResolution.value,
    lighting_mode: captureLighting.value,
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

async function startTimer() {
  const intervalValue = Number.parseInt(timerIntervalValue.value, 10);
  if (Number.isNaN(intervalValue) || intervalValue < 1) {
    message.textContent = "Enter a timer interval of at least 1.";
    return;
  }

  const intervalSeconds =
    timerIntervalUnit.value === "minutes"
      ? intervalValue * 60
      : intervalValue;

  message.textContent = "Starting timed capture...";
  timerStartButton.disabled = true;
  const response = await fetch("/api/timer/start", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ interval_seconds: intervalSeconds }),
  });
  const payload = await response.json();
  timerStartButton.disabled = false;

  if (!response.ok) {
    message.textContent = payload.error || "Timed capture failed to start.";
    return;
  }

  renderStatus(payload.status);
  message.textContent = "Timed capture started.";
}

async function stopTimer() {
  message.textContent = "Stopping timed capture...";
  timerStopButton.disabled = true;
  const response = await fetch("/api/timer/stop", { method: "POST" });
  const payload = await response.json();
  timerStopButton.disabled = false;

  if (!response.ok) {
    message.textContent = payload.error || "Timed capture failed to stop.";
    return;
  }

  renderStatus(payload.status);
  message.textContent = "Timed capture stopped.";
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
timerStartButton.addEventListener("click", () => {
  void startTimer();
});
timerStopButton.addEventListener("click", () => {
  void stopTimer();
});

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

renderStatus(initialStatus);
window.setInterval(() => {
  void refreshStatus();
}, 15000);
