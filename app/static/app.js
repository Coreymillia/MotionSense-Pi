const initialStatus = JSON.parse(document.getElementById("initial-status").textContent);

const captureButton = document.getElementById("capture-button");
const refreshButton = document.getElementById("refresh-button");
const cameraSourceSelect = document.getElementById("camera-source-select");
const cameraSourceButton = document.getElementById("camera-source-button");
const networkCameraUrl = document.getElementById("network-camera-url");
const networkCameraButton = document.getElementById("network-camera-button");
const motionStartButton = document.getElementById("motion-start-button");
const motionStopButton = document.getElementById("motion-stop-button");
const message = document.getElementById("message");
const snapshotImage = document.getElementById("snapshot-image");
const snapshotEmpty = document.getElementById("snapshot-empty");
const snapshotMeta = document.getElementById("snapshot-meta");
const senseHatPanel = document.getElementById("sensehat-panel");
const motionPanel = document.getElementById("motion-panel");
const eventList = document.getElementById("event-list");

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
  document.getElementById("camera-available").textContent = data.available ? "Yes" : "No";
  document.getElementById("camera-source-name").textContent = data.active_source_name || "Unavailable";
  document.getElementById("camera-backend").textContent = data.backend || "Unavailable";
  document.getElementById("camera-target").textContent = data.target || "Unavailable";
  document.getElementById("camera-resolution").textContent =
    `${data.resolution.width} x ${data.resolution.height}`;

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
  networkCameraUrl.value = data.network_camera_url || "";
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

function renderEvents(events) {
  eventList.innerHTML = "";

  if (!events.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No motion events yet.";
    eventList.append(empty);
    return;
  }

  for (const event of events) {
    const card = document.createElement("article");
    card.className = "event-card";

    const img = document.createElement("img");
    img.alt = `Motion event ${event.detected_at}`;
    img.src = `${event.snapshot_url}?t=${Date.now()}`;

    const body = document.createElement("div");
    body.className = "event-card-body";

    const title = document.createElement("h3");
    title.textContent = new Date(event.detected_at).toLocaleString();

    const path = document.createElement("p");
    path.className = "subtle";
    path.textContent = event.snapshot_path;

    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = `Score ${event.score}`;

    body.append(title, path, badge);
    card.append(img, body);
    eventList.append(card);
  }
}

function renderSnapshot(snapshot) {
  if (snapshot.exists && snapshot.url) {
    snapshotImage.src = `${snapshot.url}?live=1&t=${Date.now()}`;
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
  renderMotion(status.motion);
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
  message.textContent = "Snapshot captured.";
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

captureButton.addEventListener("click", () => {
  void captureSnapshot();
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
